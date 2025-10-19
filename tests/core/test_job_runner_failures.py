from __future__ import annotations

import pandas as pd

from elspeth.core.experiments import job_runner


class _FakeDatasource:
    def load(self):
        return pd.DataFrame({"a": [1]})


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

    def fake_ds_create(name, options, parent_context=None):
        return _FakeDatasource()

    def fake_sink_create(name, options, parent_context=None):
        if name == "good":
            return _GoodSink(calls)
        if name == "bad":
            return _BadSink()
        raise AssertionError(f"unexpected sink name {name}")

    monkeypatch.setattr(job_runner, "datasource_registry", type("R", (), {"create": staticmethod(fake_ds_create)})())
    monkeypatch.setattr(job_runner, "sink_registry", type("R", (), {"create": staticmethod(fake_sink_create)})())

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

