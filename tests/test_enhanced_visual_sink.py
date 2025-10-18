from __future__ import annotations

from pathlib import Path

from elspeth.plugins.nodes.sinks.enhanced_visual_report import EnhancedVisualAnalyticsSink


def _results_with_scores() -> dict:
    return {
        "results": [
            {"metrics": {"scores": {"critA": 0.7, "critB": 0.5}}},
            {"metrics": {"scores": {"critA": 0.9, "critB": 0.6}}},
        ]
    }


def test_enhanced_visual_violin_png(tmp_path: Path) -> None:
    sink = EnhancedVisualAnalyticsSink(base_path=str(tmp_path), formats=["png"], chart_types=["violin"], seaborn_style=None)
    sink.write(_results_with_scores(), metadata={"experiment": "e"})
    assert (tmp_path / "enhanced_visual_violin.png").exists()


def test_enhanced_visual_heatmap_skips_on_one_criterion(tmp_path: Path) -> None:
    sink = EnhancedVisualAnalyticsSink(base_path=str(tmp_path), formats=["png"], chart_types=["heatmap"], seaborn_style=None)
    sink.write({"results": [{"metrics": {"scores": {"critA": 0.5}}}]}, metadata={"experiment": "e"})
    # No heatmap generated with only one criterion; ensure no file
    assert not (tmp_path / "enhanced_visual_heatmap.png").exists()

