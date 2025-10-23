from types import SimpleNamespace

from elspeth.plugins.nodes.transforms.llm.middleware_azure import AzureEnvironmentMiddleware


class _DummyRun:
    def __init__(self):
        self.rows = []
        self.tables = []
        self.metrics = []

    def log_row(self, name, **payload):
        self.rows.append((name, payload))

    def log_table(self, name, payload):
        self.tables.append((name, payload))

    def log(self, name, value):
        self.metrics.append((name, value))


def test_azure_env_suite_lifecycle_with_run():
    mw = AzureEnvironmentMiddleware(enable_run_logging=False)
    mw._run = _DummyRun()  # inject dummy run context

    experiments = [
        {"name": "e1"},
        {"name": "e2"},
    ]
    mw.on_suite_loaded(experiments, preflight={"ok": True})
    mw.on_experiment_start("e1", {"k": 1})
    payload = {
        "results": [{}, {}],
        "failures": [{}],
        "aggregates": {"m": 1},
        "cost_summary": {"usd": 0.1},
    }
    mw.on_experiment_complete("e1", payload, metadata={"x": 1})
    mw.on_baseline_comparison("e1", {"p": {"delta": 1}})
    mw.on_suite_complete()

    # Rows, tables, and metrics are recorded to dummy run
    assert any(name == "experiment_start" for name, _ in mw._run.rows)
    assert any(name.startswith("baseline_") for name, _ in mw._run.tables)
    assert any(name == "experiment_count" for name, _ in mw._run.metrics)
