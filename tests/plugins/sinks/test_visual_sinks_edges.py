import json
from pathlib import Path

import pytest

from elspeth.plugins.nodes.sinks.visual_report import VisualAnalyticsSink


def _payload_empty():
    return {"results": []}


def _payload_aggregates():
    return {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "crit1": {"mean": 0.7, "pass_rate": 0.5},
                    "crit2": {"mean": 0.9},
                },
                "overall": {"mean": 0.8, "std": 0.05},
            }
        }
    }


def test_visual_sink_skips_on_no_scores(tmp_path: Path, caplog):
    sink = VisualAnalyticsSink(base_path=str(tmp_path), formats=["png"], on_error="abort")
    sink.write(_payload_empty(), metadata={})
    assert not list(tmp_path.glob("*.png"))


def test_visual_sink_write_png_and_html(tmp_path: Path):
    sink = VisualAnalyticsSink(base_path=str(tmp_path), formats=["png", "html"], on_error="abort")
    sink.write(_payload_aggregates(), metadata={"cost_summary": {"tokens": 10}})
    files = {p.name for p in tmp_path.iterdir() if p.is_file()}
    assert {"analytics_visual.png", "analytics_visual.html"}.issubset(files)
    html = (tmp_path / "analytics_visual.html").read_text(encoding="utf-8")
    assert "Cost Summary" in html
