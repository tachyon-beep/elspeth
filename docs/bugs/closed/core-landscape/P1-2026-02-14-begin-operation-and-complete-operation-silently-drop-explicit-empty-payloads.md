## Summary

`begin_operation()` and `complete_operation()` silently drop explicit empty payloads (`{}`), so operation input/output hashes and refs are not recorded even when data was provided.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_call_recording.py`
- Line(s): 218, 265, 289
- Function/Method: `begin_operation`, `complete_operation`

## Evidence

`begin_operation` only records input when payload is truthy:

```python
if input_data:
    input_hash = stable_hash(input_data)
```

`complete_operation` does the same for output:

```python
output_hash = stable_hash(output_data) if output_data else None
...
if output_data and self._payload_store is not None:
    ...
```

An explicit empty object `{}` is valid canonical JSON and should be auditable, but these checks treat it as "no data provided." That collapses two distinct states:

- `None` (not provided)
- `{}` (provided and empty)

This violates auditability expectations ("no inference; if it's not recorded, it didn't happen") and loses hash lineage for an actually supplied payload.

## Root Cause Hypothesis

Truthiness checks were used as a shortcut for optionality. In Python, `{}` is falsy, so presence/absence semantics are conflated.

## Suggested Fix

Use `is not None` checks for optional payloads, not truthiness:

```python
if input_data is not None:
    input_hash = stable_hash(input_data)
    ...

output_hash = stable_hash(output_data) if output_data is not None else None

if output_data is not None and self._payload_store is not None:
    ...
```

Add tests for `input_data={}` and `output_data={}` asserting hash/ref behavior matches "provided payload" semantics.

## Impact

Operation audit records can lose payload lineage for legitimate empty payloads, reducing forensic clarity and weakening integrity guarantees for source/sink operation tracking and replay/verification workflows.
---
## Closure
- Status: closed
- Reason: false_positive
- Closed: 2026-02-14
- Reviewer: Claude Code (Opus 4.6)

The code referenced in this finding does not match the actual source. At line 218 of `_call_recording.py`, `begin_operation()` already uses `if input_data is not None:` (not `if input_data:`). Similarly, `complete_operation()` at line 265 uses `if output_data is not None` and at line 289 uses `if output_data is not None and self._payload_store is not None`. The truthiness-based checks described in the finding are not present in the current codebase. The bug was either already fixed or the finding was generated from stale code.
