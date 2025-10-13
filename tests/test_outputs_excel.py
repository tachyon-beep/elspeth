"""Tests for ExcelResultSink behaviour with stub workbook."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elspeth.core.interfaces import Artifact
from elspeth.plugins.outputs.excel import ExcelResultSink


class StubSheet:
    def __init__(self, title: str = "Sheet") -> None:
        self.title = title
        self.rows: list[list[object]] = []

    def append(self, row) -> None:
        self.rows.append(list(row))


class StubWorkbook:
    def __init__(self) -> None:
        self.active = StubSheet()
        self._sheets = [self.active]

    def create_sheet(self, title: str) -> StubSheet:
        sheet = StubSheet(title)
        self._sheets.append(sheet)
        return sheet

    def save(self, path: str | Path) -> None:
        payload = {sheet.title: sheet.rows for sheet in self._sheets}
        Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_excel_result_sink_generates_workbook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("elspeth.plugins.outputs.excel._load_workbook_dependencies", lambda: StubWorkbook)

    sink = ExcelResultSink(
        base_path=tmp_path,
        workbook_name="suite_report",
        timestamped=False,
    )

    payload = {
        "results": [
            {
                "row": {"APPID": "1", "danger": "=SUM(A1:A2)"},
                "response": {"content": "ok"},
            }
        ],
        "aggregates": {"score_stats": {"overall": {"mean": 0.75}}},
        "failures": [],
    }
    sink.prepare_artifacts(
        {
            "excel": [
                Artifact(
                    id="extra",
                    type="file/xlsx",
                    payload={"note": "prepared"},
                )
            ]
        }
    )

    sink.write(payload, metadata={"experiment": "suite", "security_level": "SECRET", "determinism_level": "guaranteed"})

    workbook_path = tmp_path / "suite_report.xlsx"
    assert workbook_path.exists()
    data = json.loads(workbook_path.read_text(encoding="utf-8"))
    assert "Results" in data
    # Sanitisation should guard dangerous value.
    assert "'=SUM(A1:A2)" in sum((row for row in data["Results"]), [])  # flatten rows
    assert data["Manifest"][0] == ["key", "value"]
    assert any("sanitization" in row[0] for row in data["Manifest"])

    artifacts = sink.collect_artifacts()
    assert "excel" in artifacts
    assert artifacts["excel"].security_level == "SECRET"
    assert artifacts["excel"].determinism_level == "guaranteed"
    assert artifacts["excel"].metadata["sanitization"]["enabled"] is True
    # Collecting a second time returns nothing (state reset).
    assert sink.collect_artifacts() == {}


def test_excel_result_sink_skip_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingWorkbook(StubWorkbook):
        def save(self, path):
            raise RuntimeError("cannot save")

    monkeypatch.setattr("elspeth.plugins.outputs.excel._load_workbook_dependencies", lambda: FailingWorkbook)

    sink = ExcelResultSink(base_path=tmp_path, workbook_name="failing", timestamped=False, on_error="skip")
    sink.write({"results": []}, metadata={"experiment": "suite"})
    assert not (tmp_path / "failing.xlsx").exists()
