from __future__ import annotations

from pathlib import Path

import openpyxl  # type: ignore[import-untyped]
import pytest

from elspeth.plugins.nodes.sinks.excel import ExcelResultSink


def _results(n: int = 3) -> dict:
    return {
        "results": [
            {"row": {"a": i, "b": f"v{i}"}, "response": {"content": "ok"}} for i in range(n)
        ]
    }


def test_excel_sink_writes_under_allowed_base(tmp_path: Path) -> None:
    base = tmp_path / "outputs"
    base.mkdir()
    sink = ExcelResultSink(base_path=base, workbook_name="testbook", timestamped=False)
    sink._allowed_base = base.resolve()  # type: ignore[attr-defined]
    sink.write(_results(), metadata={"experiment": "e"})
    target = base / "testbook.xlsx"
    assert target.exists()
    wb = openpyxl.load_workbook(target)
    assert wb.active.max_row >= 1


def test_excel_sink_rejects_escape_outside_base(tmp_path: Path) -> None:
    base = tmp_path / "somewhere"
    base.mkdir()
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    sink = ExcelResultSink(base_path=base, workbook_name="x", timestamped=False)
    sink._allowed_base = outputs.resolve()  # type: ignore[attr-defined]
    with pytest.raises(ValueError):
        sink.write(_results(), metadata={"experiment": "e"})

