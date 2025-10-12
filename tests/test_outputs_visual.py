from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("matplotlib")  # Skip entire module if matplotlib is unavailable

from elspeth.plugins.outputs.visual_report import VisualAnalyticsSink


def _sample_payload() -> dict:
    return {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "analysis": {"mean": 0.82, "pass_rate": 0.75},
                    "safety": {"mean": 0.64, "pass_rate": 0.55},
                },
                "overall": {"mean": 0.73},
            }
        },
        "results": [],
    }


def test_visual_sink_creates_artifacts(tmp_path: Path) -> None:
    sink = VisualAnalyticsSink(
        base_path=str(tmp_path),
        file_stem="visual",
        formats=["png", "html"],
        dpi=120,
    )
    payload = _sample_payload()
    metadata = {
        "security_level": "official",
        "retry_summary": {"total_requests": 10, "total_retries": 2},
        "cost_summary": {"total_cost": 1.23},
    }

    sink.write(payload, metadata=metadata)
    artifacts = sink.collect_artifacts()

    assert (tmp_path / "visual.png").exists()
    assert (tmp_path / "visual.html").exists()
    assert {"analytics_visual_png", "analytics_visual_html"}.issubset(artifacts.keys())
    assert artifacts["analytics_visual"].path.endswith("visual.png")
    png_artifact = artifacts["analytics_visual_png"]
    html_artifact = artifacts["analytics_visual_html"]
    assert png_artifact.metadata["chart_data"]["analysis"] == pytest.approx(0.82)
    assert "pass_rates" in html_artifact.metadata
    assert png_artifact.security_level == "official"


def test_visual_sink_skip_when_backend_missing(monkeypatch, tmp_path: Path) -> None:
    sink = VisualAnalyticsSink(base_path=str(tmp_path), on_error="skip")

    def _fail():
        raise RuntimeError("matplotlib missing")

    monkeypatch.setattr(sink, "_load_plot_modules", _fail)
    sink.write(_sample_payload(), metadata={})

    assert not list(tmp_path.iterdir())
    assert sink.collect_artifacts() == {}
