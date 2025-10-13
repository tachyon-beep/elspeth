from __future__ import annotations

from pathlib import Path

import pandas as pd

from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.plugins.experiments.metrics import ScoreExtractorPlugin, ScoreStatsAggregator
from elspeth.plugins.llms.static import StaticLLMClient
from elspeth.plugins.outputs.analytics_report import AnalyticsReportSink
from elspeth.plugins.outputs.visual_report import VisualAnalyticsSink


def _make_test_dataframe() -> pd.DataFrame:
    data = pd.DataFrame(
        {
            "APPID": ["row-1", "row-2", "row-3"],
            "colour": ["red", "blue", "green"],
        }
    )
    data.attrs["security_level"] = "official"
    return data


def _build_runner(tmp_path: Path) -> ExperimentRunner:
    analytics_sink = AnalyticsReportSink(base_path=str(tmp_path / "analytics"), formats=["json"])
    visual_sink = VisualAnalyticsSink(
        base_path=str(tmp_path / "visual"),
        formats=["png", "html"],
        chart_title="Test Mean Scores",
    )
    setattr(analytics_sink, "_elspeth_security_level", "official")
    setattr(analytics_sink, "_elspeth_plugin_name", "analytics_report")
    setattr(
        analytics_sink,
        "_elspeth_artifact_config",
        {
            "produces": [
                {
                    "name": "analytics_report",
                    "type": "file/json",
                    "persist": True,
                    "alias": "analytics",
                }
            ]
        },
    )
    analytics_sink.produces = lambda: []  # type: ignore[assignment]
    setattr(visual_sink, "_elspeth_security_level", "official")
    setattr(visual_sink, "_elspeth_plugin_name", "analytics_visual")
    setattr(
        visual_sink,
        "_elspeth_artifact_config",
        {
            "produces": [
                {"name": "analytics_visual_png", "type": "file/png", "persist": True},
                {"name": "analytics_visual_html", "type": "file/html", "persist": True},
            ]
        },
    )
    visual_sink.produces = lambda: []  # type: ignore[assignment]
    llm = StaticLLMClient(content="Static completion", score=0.85)

    return ExperimentRunner(
        llm_client=llm,
        sinks=[analytics_sink, visual_sink],
        prompt_system="You are colour evaluator",
        prompt_template="Evaluate colour {{ colour }}",
        prompt_fields=["colour"],
        criteria=None,
        row_plugins=[ScoreExtractorPlugin()],
        aggregator_plugins=[ScoreStatsAggregator()],
        validation_plugins=None,
        rate_limiter=None,
        cost_tracker=None,
        experiment_name="visual_suite",
        security_level="official",
        determinism_level="guaranteed",
    )


def test_integration_visual_and_analytics_sinks(tmp_path: Path) -> None:
    runner = _build_runner(tmp_path)
    df = _make_test_dataframe()

    payload = runner.run(df)

    # Validate metrics and aggregates populated by score plugins
    assert payload["metadata"]["rows"] == 3
    assert payload["aggregates"]["score_stats"]["overall"]["mean"] == 0.85

    # Validate analytics report artifact
    analytics_path = tmp_path / "analytics" / "analytics_report.json"
    assert analytics_path.exists()
    analytics_data = analytics_path.read_text(encoding="utf-8")
    assert "score_stats" in analytics_data

    # Validate visual artifacts
    png_path = tmp_path / "visual" / "analytics_visual.png"
    html_path = tmp_path / "visual" / "analytics_visual.html"
    assert png_path.exists()
    assert html_path.exists()
    html_content = html_path.read_text(encoding="utf-8")
    assert "data:image/png;base64" in html_content

    # Validate security level propagation
    assert payload["metadata"]["security_level"] == "OFFICIAL"
    assert payload["metadata"]["determinism_level"] == "guaranteed"
