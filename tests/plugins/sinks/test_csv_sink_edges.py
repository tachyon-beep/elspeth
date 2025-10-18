from pathlib import Path

import pandas as pd
import pytest

from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink


def _results():
    return {
        "results": [
            {"row": {"A": 1, "B": "=1+2"}, "response": {"content": "ok"}},
        ]
    }


def test_csv_write_with_sanitization_disabled(tmp_path, caplog):
    dest = tmp_path / "out.csv"
    sink = CsvResultSink(path=str(dest), sanitize_formulas=False)
    sink.write(_results(), metadata={"security_level": "OFFICIAL"})
    assert dest.exists()
    assert any("sanitization disabled" in rec.message for rec in caplog.records)


def test_csv_path_outside_allowed_base_skip(tmp_path, caplog):
    dest = tmp_path / "outside" / "file.csv"
    allowed = tmp_path / "allowed"
    sink = CsvResultSink(path=str(dest), allowed_base_path=str(allowed), on_error="skip")
    sink.write(_results(), metadata={})
    # Write should be skipped due to path containment error
    assert not dest.exists()
    assert any("CSV sink failed; skipping write" in rec.message for rec in caplog.records)
