## Summary

JSONL decode failures raise `ValueError` and abort the run instead of quarantining/recording a parse-level validation error.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py
- Line(s): 669-674
- Function/Method: `AzureBlobSource._load_jsonl`

## Evidence

Current behavior:

```python
try:
    text_data = blob_data.decode(encoding)
except UnicodeDecodeError as e:
    raise ValueError(f"Failed to decode blob as {encoding}: {e}") from e
```

Source: `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py:669`

In the same file, JSON array decode errors are quarantined and recorded (`schema_mode="parse"`):
- `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py:620`
- `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py:623`

Baseline JSON source also treats JSONL decode issues as parse failures with quarantine instead of crashing:
- `/home/john/elspeth-rapid/src/elspeth/plugins/sources/json_source.py:226`

Repository trust model explicitly says source-boundary trash should be quarantined/recorded rather than crash:
- `/home/john/elspeth-rapid/CLAUDE.md:64`
- `/home/john/elspeth-rapid/CLAUDE.md:66`
- `/home/john/elspeth-rapid/CLAUDE.md:69`

## Root Cause Hypothesis

`_load_jsonl` kept a legacy "raise on decode error" path while `_load_json_array` and `JSONSource` were updated to quarantine-at-boundary behavior.

## Suggested Fix

Handle `UnicodeDecodeError` like other parse boundary errors in this source:

- record via `ctx.record_validation_error(..., schema_mode="parse", ...)`
- yield `SourceRow.quarantined(...)` unless discard
- `return` instead of raising

## Impact

A single malformed-encoding JSONL blob can fail the entire run and skip quarantine/audit recording for that parse failure, reducing audit completeness and causing avoidable pipeline interruption.
