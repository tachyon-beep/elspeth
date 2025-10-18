from pathlib import Path

import pytest

from elspeth.plugins.nodes.sinks.excel import ExcelResultSink


def _results():
    return {
        "results": [
            {"row": {"Q": "text"}, "response": {"content": "ok"}},
        ],
        "aggregates": {"score_stats": {"overall": {"mean": 0.8, "std": 0.2}}},
        "failures": [],
    }


def test_excel_skip_on_error(monkeypatch, tmp_path, caplog):
    base = tmp_path / "excel"
    base.mkdir()

    class DummyWorkbook:
        def __init__(self):
            pass

        def save(self, path: Path):  # noqa: ARG002
            raise RuntimeError("disk full")

        @property
        def active(self):  # minimal API used by sink
            class S:
                def __init__(self):
                    self.title = "Results"

                def append(self, row):  # noqa: ARG002
                    return None

            return S()

        def create_sheet(self, name):  # noqa: ARG002
            class S:
                def append(self, row):  # noqa: ARG002
                    return None

            return S()

    # patch workbook factory to return dummy workbook that fails on save
    monkeypatch.setattr("elspeth.plugins.nodes.sinks.excel._load_workbook_dependencies", lambda: lambda: DummyWorkbook())
    sink = ExcelResultSink(base_path=base, workbook_name="wb", timestamped=False, on_error="skip", allowed_base_path=base)

    sink.write(_results(), metadata={"name": "wb"})
    assert not (base / "wb.xlsx").exists()
    assert any("Excel sink failed; skipping" in rec.message for rec in caplog.records)


def test_excel_write_success(tmp_path):
    base = tmp_path / "excel"
    base.mkdir()
    sink = ExcelResultSink(base_path=base, workbook_name="wb", timestamped=False, allowed_base_path=base, sanitize_formulas=False)
    sink.write(_results(), metadata={"name": "wb", "security_level": "OFFICIAL", "determinism_level": "low"})
    path = base / "wb.xlsx"
    assert path.exists()
