from __future__ import annotations

from pathlib import Path

import zipfile
import pytest

from elspeth.plugins.nodes.sinks.zip_bundle import ZipResultSink


def _results(n: int = 2) -> dict:
    return {
        "results": [
            {"row": {"a": i}, "response": {"content": "ok"}} for i in range(n)
        ]
    }


def test_zip_sink_writes_under_allowed_base(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    sink = ZipResultSink(base_path=base, bundle_name="bundle", timestamped=False, include_results=True, include_manifest=True, include_csv=True)
    sink._allowed_base = base.resolve()  # type: ignore[attr-defined]
    sink.write(_results(), metadata={"experiment": "e"})
    archive = base / "bundle.zip"
    assert archive.exists()
    with zipfile.ZipFile(archive, "r") as zf:
        names = set(zf.namelist())
        assert {"manifest.json", "results.json", "results.csv"}.issubset(names)


def test_zip_sink_rejects_escape_outside_base(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    allowed = tmp_path / "outputs"
    allowed.mkdir()
    sink = ZipResultSink(base_path=base, bundle_name="bundle", timestamped=False)
    # No direct hook to override allowed base like CSV; rely on default 'outputs' enforced in resolver
    with pytest.raises(ValueError):
        sink.write(_results(), metadata={"experiment": "e"})
