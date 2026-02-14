## Summary

`skip_rows` can silently drop all remaining CSV data without any quarantine/audit record when a malformed skipped record causes parser state corruption.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 -- trigger requires specific preamble malformation with unmatched quotes causing multi-line csv consumption; Python 3.13 csv rarely raises csv.Error so suppress has minimal effect; narrow real-world scenario)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/sources/csv_source.py`
- Line(s): 143-146, 153-156
- Function/Method: `CSVSource.load`

## Evidence

`CSVSource.load()` suppresses parse errors during skipped preamble rows:

```python
for _ in range(self._skip_rows):
    with contextlib.suppress(csv.Error):
        next(reader, None)
```

Then it reads the header and returns immediately on EOF:

```python
try:
    raw_headers = next(reader)
except StopIteration:
    return
```

If a malformed skipped row contains an unmatched quote, Python `csv.reader` can consume subsequent lines into one logical row (often without raising in non-strict mode), leaving the reader at EOF. In that case, this code returns with:
- no `ctx.record_validation_error(...)`
- no `SourceRow.quarantined(...)`
- no indication rows were lost

Supporting repo evidence that this path is fragile:
- `tests/unit/plugins/sources/test_csv_source.py:463-465` notes Python 3.13 csv is very lenient and rarely raises `csv.Error`.
- `tests/unit/plugins/sources/test_csv_source.py:500-501` test injector explicitly consumes the real row to keep file position aligned before raising, confirming skip-path advancement side effects.

## Root Cause Hypothesis

The implementation assumes skip-time parse failures are safe to ignore because rows are intentionally skipped. That assumption breaks when parser state advancement during malformed preamble handling consumes non-skipped data; suppression hides the failure and creates an unrecorded data-loss path.

## Suggested Fix

Replace silent suppression with explicit handling that records a parse-level validation error and terminates file processing (quarantine/discard policy respected). Example shape:

- In skip loop, catch `csv.Error` explicitly.
- Call `ctx.record_validation_error(..., schema_mode="parse", destination=...)`.
- Yield `SourceRow.quarantined(...)` unless destination is `discard`.
- `return` after this failure (don't continue with potentially corrupted parser state).

## Impact

This violates auditability guarantees: rows can disappear with no terminal quarantine/error record. It creates silent data loss at the source boundary, directly conflicting with "if it's not recorded, it didn't happen."
