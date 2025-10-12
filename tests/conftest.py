import csv
import sys
from pathlib import Path
from typing import Callable

import pytest

from elspeth.plugins.outputs._sanitize import DANGEROUS_PREFIXES

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


_SANITIZATION_PREFIXES = tuple(prefix for prefix in DANGEROUS_PREFIXES if prefix != "'")
_BOM = "\ufeff"

try:  # pragma: no cover - optional dependency for Excel checks
    from openpyxl import load_workbook  # type: ignore
except Exception:  # pragma: no cover
    load_workbook = None


@pytest.fixture
def assert_sanitized_artifact() -> Callable[[str | Path], None]:
    """Assert that a CSV/Excel artifact contains no unguarded dangerous prefixes."""

    def _check_value(raw: str, *, context: str) -> None:
        value = raw.lstrip(_BOM)
        if not value:
            return
        if value[0] in _SANITIZATION_PREFIXES:
            raise AssertionError(f"Unsanitized spreadsheet value {raw!r} in {context}")

    def _assert(path: str | Path, *, guard: str = "'") -> None:  # guard kept for future extension
        artifact_path = Path(path)
        suffix = artifact_path.suffix.lower()
        if suffix == ".csv":
            with artifact_path.open(encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                for row_index, row in enumerate(reader):
                    for column_index, cell in enumerate(row):
                        _check_value(
                            cell,
                            context=f"{artifact_path.name}:{row_index}:{column_index}",
                        )
        elif suffix in {".xlsx", ".xlsm"}:
            if load_workbook is None:
                raise AssertionError("openpyxl is required to validate Excel artifacts")
            workbook = load_workbook(artifact_path, data_only=False)
            for sheet in workbook.worksheets:
                for row_index, row in enumerate(sheet.iter_rows(values_only=True)):
                    for column_index, cell in enumerate(row):
                        if isinstance(cell, str):
                            _check_value(
                                cell,
                                context=f"{artifact_path.name}:{sheet.title}:{row_index}:{column_index}",
                            )
        else:
            raise AssertionError(f"Unsupported artifact type for sanitization check: {artifact_path}")

    return _assert
