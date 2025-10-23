import pandas as pd

from elspeth.core.experiments.plugin_registry import register_aggregation_plugin, register_row_plugin
from elspeth.core.orchestrator import ExperimentOrchestrator, OrchestratorConfig


def test_orchestrator_runs(monkeypatch):
    class DummyDatasource:
        def load(self):
            return pd.DataFrame(
                [
                    {"APPID": "1", "name": "Alice"},
                    {"APPID": "2", "name": "Bob"},
                ]
            )

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"prompt": user_prompt, "meta": metadata}

    class DummySink:
        def __init__(self):
            self.calls = []
            self._elspeth_security_level = "official"

        def write(self, results, *, metadata=None):
            self.calls.append((results, metadata))

    sink = DummySink()

    orchestrator = ExperimentOrchestrator(
        datasource=DummyDatasource(),
        llm_client=DummyLLM(),
        sinks=[sink],
        config=OrchestratorConfig(
            llm_prompt={"system": "sys", "user": "Hello {name}"},
            prompt_fields=["APPID", "name"],
        ),
    )

    payload = orchestrator.run()

    assert len(payload["results"]) == 2
    assert payload["results"][0]["response"]["prompt"] == "Hello Alice"
    # Check that metadata includes row counts
    assert sink.calls and sink.calls[0][1]["processed_rows"] == 2
    assert sink.calls and sink.calls[0][1]["total_rows"] == 2


def test_orchestrator_with_criteria(monkeypatch):
    class DummyDatasource:
        def load(self):
            return pd.DataFrame(
                [
                    {"APPID": "1", "name": "Alice"},
                ]
            )

    class DummyLLM:
        def __init__(self):
            self.calls = []

        def generate(self, *, system_prompt, user_prompt, metadata=None):
            self.calls.append(metadata["criteria"])
            return {"prompt": user_prompt, "meta": metadata, "content": metadata["criteria"]}

    class DummySink:
        def __init__(self):
            self._elspeth_security_level = "official"

        def write(self, results, *, metadata=None):
            pass

    llm = DummyLLM()
    orchestrator = ExperimentOrchestrator(
        datasource=DummyDatasource(),
        llm_client=llm,
        sinks=[DummySink()],
        config=OrchestratorConfig(
            llm_prompt={"system": "sys", "user": "unused"},
            prompt_fields=["APPID"],
            criteria=[
                {"name": "a", "template": "A {APPID}"},
                {"name": "b", "template": "B {APPID}"},
            ],
        ),
    )

    payload = orchestrator.run()
    assert llm.calls == ["a", "b"]
    assert payload["results"][0]["responses"]["a"]["content"] == "a"


def test_orchestrator_single_run_executes_plugins(monkeypatch):
    row_calls = []
    agg_calls = []

    def make_row_plugin(options, context):
        class _Plugin:
            name = "single_run_row_plugin"

            def process_row(self, row, responses):
                row_calls.append((row, responses))
                return {"custom_metric": 7}

        return _Plugin()

    def make_agg_plugin(options, context):
        class _Plugin:
            name = "single_run_agg_plugin"

            def finalize(self, records):
                agg_calls.append(records)
                return {"count": len(records)}

        return _Plugin()

    register_row_plugin("single_run_row_plugin", make_row_plugin)
    register_aggregation_plugin("single_run_agg_plugin", make_agg_plugin)

    class DummyDatasource:
        def load(self):
            return pd.DataFrame([{"APPID": "1", "name": "Alice"}])

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": user_prompt, "metrics": {"score": 0.5}}

    class DummySink:
        def __init__(self):
            self.calls = []
            self._elspeth_security_level = "official"

        def write(self, results, *, metadata=None):
            self.calls.append((results, metadata))

    sink = DummySink()

    orchestrator = ExperimentOrchestrator(
        datasource=DummyDatasource(),
        llm_client=DummyLLM(),
        sinks=[sink],
        config=OrchestratorConfig(
            llm_prompt={"system": "sys", "user": "Hello {name}"},
            prompt_fields=["APPID", "name"],
            row_plugin_defs=[{"name": "single_run_row_plugin", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
            aggregator_plugin_defs=[{"name": "single_run_agg_plugin", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
        ),
    )

    payload = orchestrator.run()

    assert row_calls, "Row plugin should be invoked in single-run mode"
    assert agg_calls, "Aggregator plugin should finalize in single-run mode"
    assert payload["results"][0]["metrics"]["custom_metric"] == 7
    assert payload["aggregates"]["single_run_agg_plugin"]["count"] == 1
    assert sink.calls, "Sink should receive payload"
    sink_metadata = sink.calls[0][1]
    assert sink_metadata["aggregates"]["single_run_agg_plugin"]["count"] == 1


def test_orchestrator_resolves_determinism_from_components():
    class DeterministicDatasource:
        security_level = "OFFICIAL"
        determinism_level = "guaranteed"

        def load(self):
            return pd.DataFrame([{"APPID": "1"}])

    class LowDeterminismLLM:
        security_level = "OFFICIAL"
        determinism_level = "low"

        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": user_prompt}

    class HighSink:
        def __init__(self):
            self.calls = []
            self._elspeth_security_level = "OFFICIAL"
            self._elspeth_determinism_level = "high"
            self.determinism_level = "high"

        def write(self, results, *, metadata=None):
            self.calls.append(metadata)

    sink = HighSink()
    orchestrator = ExperimentOrchestrator(
        datasource=DeterministicDatasource(),
        llm_client=LowDeterminismLLM(),
        sinks=[sink],
        config=OrchestratorConfig(
            llm_prompt={"system": "sys", "user": "Hi {APPID}"},
            prompt_fields=["APPID"],
        ),
    )

    payload = orchestrator.run()

    assert payload["metadata"]["determinism_level"] == "low"
    assert sink.calls and sink.calls[0]["determinism_level"] == "low"
    assert orchestrator.experiment_runner.determinism_level == "low"
