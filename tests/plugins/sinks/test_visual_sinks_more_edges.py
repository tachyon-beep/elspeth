from __future__ import annotations

from pathlib import Path

import pytest

from elspeth.plugins.nodes.sinks.visual_report import VisualAnalyticsSink


def _payload_with_aggregates() -> dict:
    return {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "c1": {"mean": 0.5, "pass_rate": 0.4},
                    "c2": {"mean": 0.8, "pass_rate": 0.7},
                },
                "overall": {"mean": 0.65},
            }
        }
    }


def test_visual_sink_html_metadata_includes_early_stop_and_retry(tmp_path: Path) -> None:
    sink = VisualAnalyticsSink(base_path=str(tmp_path), formats=["html"], file_stem="vv")
    payload = _payload_with_aggregates()
    metadata = {
        "retry_summary": {"total_requests": 3, "total_retries": 1},
        "cost_summary": {"usd": 0.12},
        "early_stop": {"reason": "threshold"},
    }
    sink.write(payload, metadata=metadata)
    html = (tmp_path / "vv.html").read_text(encoding="utf-8")
    assert "Retry Summary" in html
    assert "Cost Summary" in html
    assert "Early Stop" in html


def test_visual_sink_seaborn_style_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure artifacts are still created when seaborn.set_theme raises
    sink = VisualAnalyticsSink(base_path=str(tmp_path), formats=["png"], seaborn_style="nonexistent")

    try:
        import seaborn as _sns  # type: ignore
    except Exception:
        pytest.skip("seaborn not available in environment")

    def _boom_set_theme(*args, **kwargs):  # noqa: D401
        raise ValueError("style not available")

    monkeypatch.setattr(_sns, "set_theme", _boom_set_theme)

    sink.write(_payload_with_aggregates(), metadata={})
    assert (tmp_path / "analytics_visual.png").exists()
