from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.utils.logging import PluginLogger


class Dummy:
    pass


def _context(tmp: Path) -> PluginContext:
    return PluginContext(
        plugin_name="dummy",
        plugin_kind="sink",
        security_level="OFFICIAL",
        determinism_level="guaranteed",
        suite_root=tmp,
    )


def test_plugin_logger_retention_count_prunes(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    # Create 5 historical files with increasing mtimes
    base = datetime.now(timezone.utc) - timedelta(days=10)
    for i in range(5):
        p = log_dir / f"run_2024010{i}.jsonl"
        p.write_text("{}\n", encoding="utf-8")
        ts = base + timedelta(days=i)
        os.utime(p, (ts.timestamp(), ts.timestamp()))

    # Keep only the 2 newest
    monkeypatch.setenv("ELSPETH_LOG_MAX_FILES", "2")
    ctx = _context(tmp_path)
    PluginLogger(plugin_instance=Dummy(), context=ctx, log_dir=log_dir)

    remaining = sorted([p.name for p in log_dir.glob("run_*.jsonl")])
    # 2 newest + current run file
    assert len(remaining) == 3


def test_plugin_logger_retention_age_prunes(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    old = log_dir / "run_20230101.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    very_old_time = (datetime.now(timezone.utc) - timedelta(days=365)).timestamp()
    os.utime(old, (very_old_time, very_old_time))

    # Age cutoff at 30 days -> should delete the old file
    monkeypatch.setenv("ELSPETH_LOG_MAX_AGE_DAYS", "30")
    ctx = _context(tmp_path)
    PluginLogger(plugin_instance=Dummy(), context=ctx, log_dir=log_dir)

    assert not old.exists()


def test_plugin_logger_error_and_specialized_events(tmp_path: Path) -> None:
    ctx = _context(tmp_path)
    logger = PluginLogger(plugin_instance=Dummy(), context=ctx, log_dir=tmp_path / "logs")

    # datasource event with partial metrics/metadata
    logger.log_datasource_event("loaded", rows=1, columns=None, schema="S", source_path="p.csv", duration_ms=None)
    # generic event with metrics and metadata at various levels
    logger.log_event("custom", message="hello", metrics={"m": 1}, metadata={"k": "v"}, level="debug")
    # error with Exception vs. string
    logger.log_error(ValueError("bad"), context="ctx", recoverable=True)
    logger.log_error("oops", context=None, recoverable=False)

    # Ensure log file created and contains JSON lines
    run_file = next((p for p in (tmp_path / "logs").glob("run_*.jsonl")), None)
    assert run_file and run_file.read_text(encoding="utf-8").strip()


def test_plugin_logger_retention_handles_valueerror(tmp_path: Path, monkeypatch) -> None:
    """Retention should tolerate timestamp conversion errors (ValueError)."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    # Create one historical file so the retention loop runs
    p = log_dir / "run_20230101.jsonl"
    p.write_text("{}\n", encoding="utf-8")
    # Force a small age window so we attempt fromtimestamp conversion
    monkeypatch.setenv("ELSPETH_LOG_MAX_AGE_DAYS", "1")

    # Monkeypatch datetime.fromtimestamp used in retention to raise ValueError
    import elspeth.core.utils.logging as logmod

    class _FakeDT:
        @classmethod
        def now(cls, tz=None):  # noqa: D401
            from datetime import datetime as _dt

            return _dt.now(tz)

        @classmethod
        def fromtimestamp(cls, *_a, **_k):  # noqa: D401
            raise ValueError("bad ts")

    monkeypatch.setattr(logmod, "datetime", _FakeDT)

    ctx = _context(tmp_path)
    # Should not raise despite ValueError during retention
    PluginLogger(plugin_instance=Dummy(), context=ctx, log_dir=log_dir)
