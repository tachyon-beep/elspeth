from __future__ import annotations

import pandas as pd

from elspeth.core.experiments import job_runner
from elspeth.core.registry import central_registry
from elspeth.core.security import SecureDataFrame
from elspeth.core.base.types import SecurityLevel


class _FakeDatasource:
    def load(self):
        df = pd.DataFrame({"a": [1]})
        return SecureDataFrame.create_from_datasource(df, SecurityLevel.UNOFFICIAL)


class _GoodSink:
    def __init__(self, calls):
        self._calls = calls

    def write(self, payload, *, metadata=None):
        self._calls.append(("good", payload))


class _BadSink:
    def write(self, payload, *, metadata=None):
        raise ValueError("boom")


def test_job_runner_accumulates_sink_failures(monkeypatch):
    calls: list[tuple[str, dict]] = []

    # ADR-002-B: Mock registry.create() signature includes require_security/require_determinism
    def fake_ds_create(name, options, parent_context=None, require_security=True, require_determinism=True):
        return _FakeDatasource()

    def fake_sink_create(name, options, parent_context=None, require_security=True, require_determinism=True):
        if name == "good":
            return _GoodSink(calls)
        if name == "bad":
            return _BadSink()
        raise AssertionError(f"unexpected sink name {name}")

    # Mock the central_registry.get_registry() to return fake registries
    fake_datasource_registry = type("R", (), {"create": staticmethod(fake_ds_create)})()
    fake_sink_registry = type("R", (), {"create": staticmethod(fake_sink_create)})()

    original_get_registry = central_registry.get_registry
    def mock_get_registry(plugin_type):
        if plugin_type == "datasource":
            return fake_datasource_registry
        elif plugin_type == "sink":
            return fake_sink_registry
        return original_get_registry(plugin_type)

    monkeypatch.setattr(central_registry, "get_registry", mock_get_registry)

    job = {
        "datasource": {"plugin": "csv_local", "options": {"path": "irrelevant.csv", "retain_local": True}},
        "sinks": [
            {"plugin": "bad", "options": {}},
            {"plugin": "good", "options": {}},
        ],
    }

    payload = job_runner.run_job_config(job)

    # One failure recorded, and good sink still executed
    assert "failures" in payload and len(payload["failures"]) == 1
    assert payload["failures"][0]["sink"].lower().endswith("badsink")
    assert calls and calls[0][0] == "good"
