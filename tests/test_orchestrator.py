import pandas as pd

from dmp.core.orchestrator import ExperimentOrchestrator, OrchestratorConfig
from dmp.core.experiments.plugin_registry import register_row_plugin, register_aggregation_plugin


def test_orchestrator_runs(monkeypatch):
    class DummyDatasource:
        def load(self):
            return pd.DataFrame([
                {"APPID": "1", "name": "Alice"},
                {"APPID": "2", "name": "Bob"},
            ])

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"prompt": user_prompt, "meta": metadata}

    class DummySink:
        def __init__(self):
            self.calls = []

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
    assert sink.calls and sink.calls[0][1]["row_count"] == 2


def test_orchestrator_with_criteria(monkeypatch):
    class DummyDatasource:
        def load(self):
            return pd.DataFrame([
                {"APPID": "1", "name": "Alice"},
            ])

    class DummyLLM:
        def __init__(self):
            self.calls = []

        def generate(self, *, system_prompt, user_prompt, metadata=None):
            self.calls.append(metadata["criteria"])
            return {"prompt": user_prompt, "meta": metadata, "content": metadata["criteria"]}

    class DummySink:
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

    def make_row_plugin(options):
        class _Plugin:
            name = "single_run_row_plugin"

            def process_row(self, row, responses):
                row_calls.append((row, responses))
                return {"custom_metric": 7}

        return _Plugin()

    def make_agg_plugin(options):
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
            row_plugin_defs=[{"name": "single_run_row_plugin"}],
            aggregator_plugin_defs=[{"name": "single_run_agg_plugin"}],
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
