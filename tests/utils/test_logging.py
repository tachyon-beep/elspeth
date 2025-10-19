from __future__ import annotations

import builtins
import inspect as _inspect
import os
import time
from pathlib import Path

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.utils.logging import PluginLogger, attach_plugin_logger


class DummyPlugin:
    pass


def _make_context(tmp_path: Path) -> PluginContext:
    return PluginContext(
        plugin_name="dummy",
        plugin_kind="sink",
        security_level="OFFICIAL",
        determinism_level="high",
        provenance=("test",),
        suite_root=tmp_path,
    )


def test_retention_age_and_count_pruning(monkeypatch, tmp_path: Path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    # Create three files: one old (>1 day), two fresh
    old = logs_dir / "run_20000101T000000Z.jsonl"
    fresh1 = logs_dir / "run_30000101T000000Z.jsonl"
    fresh2 = logs_dir / "run_30000101T010000Z.jsonl"
    for p in (old, fresh1, fresh2):
        p.write_text("{}\n", encoding="utf-8")

    # Make 'old' older than 2 days
    two_days_ago = time.time() - 2 * 24 * 3600
    os.utime(old, (two_days_ago, two_days_ago))

    monkeypatch.setenv("ELSPETH_LOG_MAX_AGE_DAYS", "1")
    monkeypatch.setenv("ELSPETH_LOG_MAX_FILES", "1")

    # Force inspect.getsource to fail to exercise fallback code path
    monkeypatch.setattr("inspect.getsource", lambda *_args, **_kw: (_ for _ in ()).throw(OSError("nope")))

    # Create logger - triggers retention and initialization
    ctx = _make_context(tmp_path)
    logger = PluginLogger(plugin_instance=DummyPlugin(), context=ctx)
    # 'old' should be pruned by age. After age prune, count-prune should reduce fresh files to 1.
    remaining = sorted(p.name for p in logs_dir.glob("run_*.jsonl"))
    assert len(remaining) <= 2  # includes the new run file from this logger


def test_event_apis_and_fallback_open(monkeypatch, tmp_path: Path):
    ctx = _make_context(tmp_path)
    plugin = DummyPlugin()
    attach_plugin_logger(plugin, ctx)
    plog = getattr(plugin, "plugin_logger")

    # Exercise event methods
    plog.log_event("custom", message="hello", metrics={"x": 1}, metadata={"y": "z"})
    plog.log_datasource_event("loaded", rows=10, columns=3, schema="S", source_path="/p")
    plog.log_llm_event("response", model="m", prompt_tokens=1, completion_tokens=2, total_tokens=3, duration_ms=4.5, temperature=0.1)
    plog.log_sink_event("write", output_path="/o", rows_written=2, bytes_written=10, duration_ms=1.2)
    plog.log_error(ValueError("oops"), context="ctx", recoverable=True)
    plog.log_error("string", context="ctx2", recoverable=False)

    # Patch open to raise to exercise _write_log_entry fallback
    def _boom(*_args, **_kwargs):  # noqa: D401
        raise OSError("disk full")

    monkeypatch.setattr(builtins, "open", _boom)
    # Should not raise
    plog.log_event("another", message="should fallback", metrics=None, metadata=None)

