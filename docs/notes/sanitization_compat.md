# Spreadsheet Sanitisation Compatibility Notes

Results from `tox -e sanitization-matrix` (runs `scripts/compatibility/run_sanitization_matrix.py`).

| Consumer | Guard | Outcome | Notes |
| --- | --- | --- | --- |
| pandas `read_csv` | `'` | Pass | Values matched `sanitize_cell` output across dangerous prefixes |
| Python `csv` module | `'` | Pass | Header + rows preserved guard prefix; newline normalization validated |
| LibreOffice CLI | `'` | _pending_ | Requires manual run (`libreoffice --headless`) |
| Microsoft Excel | `'` | Pass | Validated via `openpyxl` load; manifest metadata confirmed |

Last evaluated: 2025-10-10 AEDT
