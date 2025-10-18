from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink


def _results_with_rows(n: int = 3) -> dict:
    return {
        "results": [
            {"row": {"a": i, "b": f"v{i}"}, "response": {"content": "ok"}} for i in range(n)
        ]
    }


def test_csv_sink_writes_under_allowed_base(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    target = base / "sub" / "out.csv"

    sink = CsvResultSink(path=str(target), overwrite=True)
    # Inject allowed base to our tmp outputs for isolation
    sink._allowed_base = base.resolve()  # type: ignore[attr-defined]
    sink.write(_results_with_rows(), metadata={"experiment": "e"})

    assert target.exists()
    df = pd.read_csv(target)
    assert len(df) == 3


def test_csv_sink_rejects_escape_outside_base(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    outside = tmp_path / "escape.csv"

    sink = CsvResultSink(path=str(outside), overwrite=True)
    sink._allowed_base = base.resolve()  # type: ignore[attr-defined]

    with pytest.raises(ValueError):
        sink.write(_results_with_rows(), metadata={"experiment": "e"})


def test_csv_sink_rejects_symlink_destination(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    real = base / "real.csv"
    real.write_text("a,b\n1,x\n", encoding="utf-8")
    link = base / "link.csv"
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported by platform/user")

    sink = CsvResultSink(path=str(link), overwrite=True)
    sink._allowed_base = base.resolve()  # type: ignore[attr-defined]

    with pytest.raises(ValueError):
        sink.write(_results_with_rows(), metadata={"experiment": "e"})

