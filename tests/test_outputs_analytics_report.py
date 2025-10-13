"""Expanded coverage for analytics report sink."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elspeth.plugins.outputs.analytics_report import AnalyticsReportSink


def _sample_payload() -> dict[str, object]:
    return {
        "results": [
            {
                "row": {"APPID": "1"},
                "metrics": {"score": 0.8},
                "retry": {"attempts": 1, "history": [{"status": "success"}]},
            }
        ],
        "failures": [{"row": {"APPID": "2"}, "error": "boom"}],
        "aggregates": {
            "score_stats": {
                "overall": {"mean": 0.8, "std": 0.05},
                "criteria": {"analysis": {"mean": 0.8}},
            }
        },
        "baseline_comparison": {"score_significance": {"p_value": 0.04}},
        "score_cliffs_delta": {"analysis": {"delta": 0.6}},
        "metadata": {"retry_summary": {"total_requests": 2}, "security_level": "OFFICIAL", "determinism_level": "guaranteed"},
    }


def test_analytics_report_sink_generates_files_and_artifacts(tmp_path: Path) -> None:
    sink = AnalyticsReportSink(
        base_path=tmp_path / "reports",
        file_stem="summary",
        formats=["json", "markdown"],
    )

    sink.write(_sample_payload(), metadata={"security_level": "OFFICIAL", "determinism_level": "guaranteed"})

    json_path = tmp_path / "reports" / "summary.json"
    md_path = tmp_path / "reports" / "summary.md"
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["rows"] == 1
    assert data["failures"] == 1
    assert data["metadata"]["security_level"] == "OFFICIAL"
    assert data["metadata"]["determinism_level"] == "guaranteed"
    assert data["aggregates"]["score_stats"]["overall"]["mean"] == 0.8
    assert "analytics" in data and "score_cliffs_delta" in data["analytics"]

    markdown = md_path.read_text(encoding="utf-8")
    assert "Analytics Report" in markdown
    assert "Baseline Comparison" in markdown
    assert "Failure Examples" in markdown

    artifacts = sink.collect_artifacts()
    assert "summary.json" in artifacts
    assert "summary.md" in artifacts
    json_artifact = artifacts["summary.json"]
    assert json_artifact.persist is True
    assert json_artifact.security_level == "OFFICIAL"
    assert json_artifact.determinism_level == "guaranteed"


def test_analytics_report_sink_skip_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sink = AnalyticsReportSink(
        base_path=tmp_path / "reports",
        file_stem="broken",
        formats=["json", "md"],
        on_error="skip",
    )

    original_write_text = Path.write_text

    def patched_write_text(self, text, *args, **kwargs):
        if self.suffix == ".md":
            raise OSError("markdown failure")
        return original_write_text(self, text, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", patched_write_text)

    sink.write({"results": []}, metadata={"security_level": "OFFICIAL", "determinism_level": "guaranteed"})

    # JSON file should exist even though markdown write failed.
    json_path = tmp_path / "reports" / "broken.json"
    assert json_path.exists()
    artifacts = sink.collect_artifacts()
    assert artifacts == {}
