## Summary

`RowErrorEntry.error` is typed as `str`, but production code stores structured objects there, creating a schema/contract mismatch for persisted transform error payloads.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/contracts/errors.py
- Line(s): 148
- Function/Method: `RowErrorEntry` TypedDict schema

## Evidence

Contract says:

```python
class RowErrorEntry(TypedDict):
    row_index: int
    reason: str
    error: NotRequired[str]
```

(`src/elspeth/contracts/errors.py:143-149`)

But Azure batch flow can place dict/object error payloads into that field:

- `error_body` can be a structured object (`src/elspeth/plugins/llm/azure_batch.py:1065-1077`)
- appended directly into `row_errors` (`src/elspeth/plugins/llm/azure_batch.py:1160`)
- then emitted as `TransformResult.error(..., {"row_errors": row_errors})` (`src/elspeth/plugins/llm/azure_batch.py:1270-1274`)
- persisted via `error_details_json` (`src/elspeth/core/landscape/_error_recording.py:168`)

So actual runtime shape is wider than the contract in `errors.py`.

## Root Cause Hypothesis

`RowErrorEntry` was initially modeled for string-only summaries, but batch plugins evolved to propagate structured per-row error objects without the contract being updated.

## Suggested Fix

Broaden `RowErrorEntry.error` in `src/elspeth/contracts/errors.py` to match real payloads (for example `NotRequired[str | dict[str, Any]]`), and update docstrings accordingly.

## Impact

Typed contract consumers can make wrong assumptions about `row_errors` shape, causing downstream validation/display/export bugs and weakening schema reliability for audit tooling.

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/errors.py.md`
- Finding index in source report: 2
- Beads: pending
