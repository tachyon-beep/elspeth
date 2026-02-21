## Summary

`checkpoint_loads()` can silently corrupt valid user row data (or crash resume) by treating any dict shaped like `{"__datetime__": "<str>"}` as an internal datetime type-tag.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/checkpoint/serialization.py`
- Line(s): 124-125 (decode), 55 (encode tag shape)
- Function/Method: `_restore_types`, `CheckpointEncoder.default`

## Evidence

`_restore_types` decodes by shape only:

```python
# serialization.py
if "__datetime__" in obj and len(obj) == 1 and isinstance(obj["__datetime__"], str):
    return datetime.fromisoformat(obj["__datetime__"])
```

That collides with legitimate user object payloads because aggregation checkpoints persist raw `row_data` dicts:

- `src/elspeth/engine/executors/aggregation.py:627` stores `t.row_data.to_dict()`
- `src/elspeth/contracts/schema_contract.py:236` and `src/elspeth/contracts/schema_contract.py:259` show `object` fields accept arbitrary nested structures
- `tests/integration/pipeline/test_resume_comprehensive.py:1083` and `tests/integration/pipeline/test_resume_comprehensive.py:1093` demonstrate nested object fields are a real resume scenario

Repro (executed in repo):

- `checkpoint_loads(checkpoint_dumps({"row_data":{"metadata":{"__datetime__":"2024-01-01T00:00:00+00:00"}}}))`
  returns `datetime` instead of original dict
- same shape with non-ISO string raises `ValueError` (`Invalid isoformat string...`), breaking resume for valid user data that merely uses that key

Test suite also hints at this blind spot: property generator explicitly excludes `"__datetime__"` keys (`tests/property/core/test_checkpoint_serialization_properties.py:77`), so this collision is not protected.

## Root Cause Hypothesis

The datetime tagging scheme is not collision-safe: it reuses a normal user-data shape as an internal marker and does not escape user dicts before serialization. Decoding is therefore non-bijective for object fields.

## Suggested Fix

Use a collision-safe, reversible encoding in this file:

- Replace shape-based tag `{"__datetime__": ...}` with an explicit envelope (e.g., type discriminator + value) handled via recursive pre-encode/post-decode functions.
- Add escaping for user dicts that match reserved envelope keys so decode is fully invertible.
- Add regression tests for:
  - exact-shape user dict `{"__datetime__": "..."}` round-trip unchanged
  - non-ISO string in that shape does not crash unless it was truly encoder-produced tag
  - nested object fields under aggregation checkpoint state

## Impact

- Resume can fail on valid pipeline data (false corruption signal).
- Resume can silently change user payload types/values, violating round-trip fidelity and audit correctness.
- Affects checkpointed aggregation state where `row_data` contains nested object values, undermining trust guarantees in crash recovery.
