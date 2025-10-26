from __future__ import annotations

import types
from types import SimpleNamespace

import pytest

from elspeth.core.registries.sink import sink_registry


def test_csv_factory_uses_preloaded_module(monkeypatch, tmp_path):
    """When the csv_file module is preloaded, the factory should use it."""
    # Create a dummy module with a distinct CsvResultSink for identification
    dummy_mod = types.ModuleType("elspeth.plugins.nodes.sinks.csv_file")

    class DummyCsvSink:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.marker = "dummy"

        def produces(self):
            return []

        def consumes(self):
            return []

        def write(self, payload, *, metadata=None):
            pass

    dummy_mod.CsvResultSink = DummyCsvSink  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "elspeth.plugins.nodes.sinks.csv_file", dummy_mod)

    sink = sink_registry.create(
        name="csv",
        options={"path": str(tmp_path / "out.csv")},
        require_security=False,
        require_determinism=False,
    )

    assert getattr(sink, "marker", None) == "dummy"


def test_csv_factory_fallback_to_export(monkeypatch, tmp_path):
    """When the module isn't in sys.modules, fall back to package export class."""
    import elspeth.core.registries.sink as sink_mod

    # Replace the modules mapping used by the factory to simulate missing entry
    class _FakeModules(dict):
        def get(self, key, default=None):  # ensure only our key returns None
            if key == "elspeth.plugins.nodes.sinks.csv_file":
                return None
            return super().get(key, default)

    monkeypatch.setattr(sink_mod, "_modules", _FakeModules(), raising=True)

    sink = sink_registry.create(
        name="csv",
        options={"path": str(tmp_path / "out.csv")},
        require_security=False,
        require_determinism=False,
    )

    # The real CsvResultSink does not define the "marker" attribute
    assert not hasattr(sink, "marker")
