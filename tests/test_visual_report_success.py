from __future__ import annotations

from pathlib import Path

from elspeth.plugins.nodes.sinks.visual_report import VisualAnalyticsSink


def test_visual_report_png_success(tmp_path: Path) -> None:
    sink = VisualAnalyticsSink(base_path=str(tmp_path), formats=["png"], seaborn_style=None)
    results = {
        "results": [
            {"metrics": {"scores": {"alpha": 0.7, "beta": 0.4}}},
            {"metrics": {"scores": {"alpha": 0.9, "beta": 0.6}}},
        ]
    }
    sink.write(results, metadata={"experiment": "e"})
    assert (tmp_path / "analytics_visual.png").exists()

