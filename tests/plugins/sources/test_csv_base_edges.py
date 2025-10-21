from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from elspeth.plugins.nodes.sources.csv_local import CSVDataSource


class _Recorder:
    def __init__(self) -> None:
        self.errors: list[tuple[object, dict]] = []
        self.events: list[tuple[str, dict]] = []

    def log_error(self, exc: object, *, context: str | None = None, recoverable: bool | None = None) -> None:  # noqa: D401
        self.errors.append((exc, {"context": context, "recoverable": recoverable}))

    def log_datasource_event(self, name: str, **kwargs) -> None:  # noqa: D401
        self.events.append((name, kwargs))

    def log_event(self, name: str, **kwargs) -> None:  # noqa: D401
        self.events.append((name, kwargs))


def test_allowed_base_path_enforced_for_absolute(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    # Create file outside allowed
    csv_path = outside / "data.csv"
    pd.DataFrame({"a": [1]}).to_csv(csv_path, index=False)

    # Using absolute path outside allowed must raise
    with pytest.raises(ValueError):
        CSVDataSource(path=csv_path, allowed_base_path=allowed, retain_local=False)

    # Inside allowed should pass
    ok_path = allowed / "ok.csv"
    pd.DataFrame({"a": [1]}).to_csv(ok_path, index=False)
    ds = CSVDataSource(path=ok_path, allowed_base_path=allowed, retain_local=False)
    assert ds.load().shape[0] == 1


def test_base_path_and_env_resolution_and_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "inputs"
    base.mkdir()
    p = base / "file.csv"
    pd.DataFrame({"x": [1, 2]}).to_csv(p, index=False)

    # Resolve via base_path
    ds = CSVDataSource(path="file.csv", base_path=base, allowed_base_path=base, retain_local=False)
    assert ds.load().shape == (2, 1)

    # Resolve via ELSPETH_INPUTS_DIR when base_path omitted
    monkeypatch.setenv("ELSPETH_INPUTS_DIR", str(base))
    ds2 = CSVDataSource(path="file.csv", allowed_base_path=base, retain_local=False)
    assert ds2.load().shape == (2, 1)


def test_missing_file_logs_to_plugin_logger_when_skip(tmp_path: Path) -> None:
    rec = _Recorder()
    ds = CSVDataSource(path=tmp_path / "missing.csv", on_error="skip", retain_local=False)
    # Attach a plugin_logger-like object
    setattr(ds, "plugin_logger", rec)
    df = ds.load()
    assert df.empty
    assert rec.errors and rec.errors[-1][1]["recoverable"] is True


def test_missing_file_abort_logs_and_raises(tmp_path: Path) -> None:
    rec = _Recorder()
    ds = CSVDataSource(path=tmp_path / "missing.csv", on_error="abort", retain_local=False)
    setattr(ds, "plugin_logger", rec)
    with pytest.raises(FileNotFoundError):
        ds.load()
    # Last logged error should be non-recoverable
    assert rec.errors and rec.errors[-1][1]["recoverable"] is False


def test_load_error_logs_and_returns_empty_on_skip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("not,csv\n\x00\x00", encoding="utf-8")
    ds = CSVDataSource(path=csv_path, on_error="skip", retain_local=False)
    rec = _Recorder()
    setattr(ds, "plugin_logger", rec)

    monkeypatch.setattr("pandas.read_csv", lambda *a, **k: (_ for _ in ()).throw(pd.errors.ParserError("bad")))
    df = ds.load()
    assert df.empty
    # output_schema() should have returned None when inference fails
    assert df.attrs.get("schema") is None
    assert rec.errors, "expected plugin_logger.log_error to be called"


def test_output_schema_inference_failure_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    ds = CSVDataSource(path=csv_path, infer_schema=True, retain_local=False)
    # Force read failure during inference code path
    monkeypatch.setattr("pandas.read_csv", lambda *a, **k: (_ for _ in ()).throw(pd.errors.ParserError("boom")))
    assert ds.output_schema() is None


def test_retain_local_copy_failure_yields_empty_when_skip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    pd.DataFrame({"a": [1]}).to_csv(csv_path, index=False)
    ds = CSVDataSource(path=csv_path, retain_local=True, on_error="skip")

    # After a successful read, copying to audit location should fail
    def _copy_oom(*_args, **_kwargs):  # noqa: D401
        raise OSError("disk full")

    monkeypatch.setattr("shutil.copy2", _copy_oom)
    df = ds.load()
    assert df.empty


def test_retain_local_copy_success_sets_attr(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    pd.DataFrame({"a": [1]}).to_csv(csv_path, index=False)
    dest_dir = tmp_path / "audit"
    ds = CSVDataSource(path=csv_path, retain_local=True, retain_local_path=str(dest_dir / "snap.csv"))
    df = ds.load()
    assert df.attrs.get("retained_local_path") == str(dest_dir / "snap.csv")
