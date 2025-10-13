import pandas as pd

from elspeth.cli import _result_to_row
from elspeth.core.experiments.plugin_registry import create_early_stop_plugin, create_row_plugin
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.plugins.llms.mock import MockLLMClient


class DummySink:
    def __init__(self):
        self._elspeth_security_level = "official"

    def write(self, results, *, metadata=None):
        pass


def _build_runner():
    return ExperimentRunner(
        llm_client=MockLLMClient(seed=123),
        sinks=[DummySink()],
        prompt_system="You are a tester.",
        prompt_template="Summarise {{ APPID }}.",
        prompt_fields=["APPID"],
        criteria=[
            {"name": "analysis", "template": "Give analysis for {{ APPID }}."},
            {"name": "prioritization", "template": "Prioritise {{ APPID }}."},
        ],
        row_plugins=[create_row_plugin({"name": "score_extractor", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})],
    )


def test_metrics_schema_contains_scalar_and_nested_fields():
    runner = _build_runner()
    df = pd.DataFrame({"APPID": ["APP-001"]})
    payload = runner.run(df)
    record = payload["results"][0]
    metrics = record["metrics"]

    assert "score" in metrics and isinstance(metrics["score"], float)
    assert "scores" in metrics and set(metrics["scores"].keys()) == {"analysis", "prioritization"}
    assert all(isinstance(value, float) for value in metrics["scores"].values())

    flattened = _result_to_row(record)
    assert flattened["metric_scores_analysis"] == metrics["scores"]["analysis"]
    assert flattened["metric_scores_prioritization"] == metrics["scores"]["prioritization"]


def test_early_stop_plugins_can_reference_nested_metrics():
    runner = _build_runner()
    df = pd.DataFrame({"APPID": ["APP-XYZ", "APP-ABC"]})
    payload = runner.run(df)
    first = payload["results"][0]
    second = payload["results"][1]

    analysis_plugin = create_early_stop_plugin(
        {
            "name": "threshold",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {
                "metric": "scores.analysis",
                "threshold": first["metrics"]["scores"]["analysis"] - 0.01,
            },
        }
    )
    reason = analysis_plugin.check(first, metadata={"row_index": 0})
    assert reason and reason["value"] == first["metrics"]["scores"]["analysis"]

    score_plugin = create_early_stop_plugin(
        {
            "name": "threshold",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {
                "metric": "score",
                "threshold": max(first["metrics"]["score"], second["metrics"]["score"]) - 0.01,
                "min_rows": 2,
            },
        }
    )
    # First row alone should not trigger because min_rows=2
    assert score_plugin.check(first) is None
    assert score_plugin.check(second, metadata={"row_index": 1}) is not None
