## Summary

`UnicodeDecodeError` from CSV file reads is unhandled and crashes the pipeline instead of producing a parse-level quarantine/discard outcome.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/sources/csv_source.py`
- Line(s): 134, 153-157, 206-212
- Function/Method: `CSVSource.load`

## Evidence

The file is opened in text mode with explicit encoding:

```python
with open(self._path, encoding=self._encoding, newline="") as f:
    reader = csv.reader(f, delimiter=self._delimiter)
```

Decode failures are not caught anywhere in `load()`. Existing exception handling only catches `csv.Error` and `StopIteration` around `next(reader)` calls. A bad byte for the configured encoding raises `UnicodeDecodeError`, which bypasses these handlers and aborts execution.

By contrast, JSON source explicitly handles decode boundary failures (`/home/john/elspeth-rapid/src/elspeth/plugins/sources/json_source.py:226-233`), recording parse error outcomes instead of crashing.

## Root Cause Hypothesis

Error handling in `CSVSource.load()` was scoped to CSV structural errors (`csv.Error`) but omitted text decoding failures, even though decoding is part of the same external-data trust boundary.

## Suggested Fix

Add `UnicodeDecodeError` handling in `CSVSource.load()` at the file/reader boundary:
- Record parse failure via `ctx.record_validation_error(..., schema_mode="parse")`
- Yield quarantined row unless `on_validation_failure == "discard"`
- Return cleanly after file-level decode failure

Optionally mirror JSON source behavior with `errors="surrogateescape"` plus explicit invalid-byte quarantine metadata.

## Impact

A single invalid byte can crash the whole run, preventing quarantine routing and breaking expected source-boundary resilience for malformed external data.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/sources/csv_source.py.md`
- Finding index in source report: 2
- Beads: pending
