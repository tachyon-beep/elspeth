from __future__ import annotations

import csv
from pathlib import Path

import pytest

from elspeth.plugins.nodes.sources.csv_local import CSVDataSource


def _write_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name"])
        writer.writerow([1, "a"])


def test_csv_allowed_base_positive(tmp_path: Path) -> None:
    base = tmp_path / "allowed"
    data = base / "data" / "file.csv"
    _write_csv(data)

    ds = CSVDataSource(path=str(data), allowed_base_path=str(base), retain_local=False)
    df = ds.load()
    assert not df.empty
    assert set(df.columns) == {"id", "name"}


def test_csv_allowed_base_negative(tmp_path: Path) -> None:
    base = tmp_path / "allowed"
    data = tmp_path / "outside" / "file.csv"
    _write_csv(data)

    with pytest.raises(ValueError):
        _ = CSVDataSource(path=str(data), allowed_base_path=str(base), retain_local=False)
