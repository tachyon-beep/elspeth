## Summary

`record_transform_error()` crashes on non-canonical values inside `error_details` (e.g., `NaN` in external API payload), so legitimate transform errors can fail to be recorded and escalate to run failure.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_error_recording.py`
- Line(s): `166-169`
- Function/Method: `record_transform_error`

## Evidence

The method unconditionally canonicalizes `error_details`:

```python
# _error_recording.py:166-169
row_hash=stable_hash(row_data),
row_data_json=canonical_json(row_data),
error_details_json=canonical_json(error_details),
```

`canonical_json()` rejects non-finite floats (`core/canonical.py:59-63`, `166-168`).

Transforms explicitly include external response blobs in `TransformResult.error(...)`, e.g. OpenRouter:

- `/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter.py:593-609`
- `/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter_multi_query.py:266-287`

I reproduced the failure by calling `record_transform_error(..., error_details={"reason":"test_error","response":{"score": float("nan")}})` ; it raises `ValueError: Cannot canonicalize non-finite float: nan`.

## Root Cause Hypothesis

`record_transform_error()` assumes `TransformErrorReason` is always canonical JSON-safe, but those details can contain unsanitized Tier-3 external values.

## Suggested Fix

Handle canonicalization failure for `error_details` similarly to validation-error fallback:

- Wrap `canonical_json(error_details)` in `try/except (ValueError, TypeError)`.
- Store structured fallback metadata (repr/type/error) instead of crashing.
- Log a warning with bounded preview for observability.

## Impact

A row-scoped transform failure can become a pipeline-level exception, breaking audit completeness (`transform_errors` row missing) and violating expected quarantine/error-routing behavior.
