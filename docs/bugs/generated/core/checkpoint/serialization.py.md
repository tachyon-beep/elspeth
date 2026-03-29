## Summary

Checkpoint serialization silently converts tuple-valued row fields into lists on resume, which changes Tier 2 data semantics and can hide upstream bugs that downstream transforms are supposed to catch.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/checkpoint/serialization.py
- Line(s): 51-74, 103-130, 156, 159-193
- Function/Method: `CheckpointEncoder.default`, `_escape_reserved_keys`, `checkpoint_dumps`, `_restore_types`

## Evidence

`serialization.py` claims “type-preserving JSON serialization” for checkpoint state, including values allowed by `SchemaContract` (`object` fields are explicitly allowed) (`serialization.py:1-25`). In practice it only preserves `datetime`:

```python
# serialization.py:64-74
if isinstance(obj, datetime):
    ...
    return {
        _ENVELOPE_TYPE_KEY: "datetime",
        _ENVELOPE_VALUE_KEY: obj.isoformat(),
    }
return super().default(obj)
```

Everything else falls through to plain `json.dumps(...)` (`serialization.py:156`), which converts tuples to JSON arrays. `_restore_types()` only restores tagged dicts and lists, never tuples (`serialization.py:176-193`).

That matters because checkpointing persists full buffered row payloads and restores them directly into `PipelineRow` during resume:

```python
# engine/executors/aggregation.py:645-655
AggregationTokenCheckpoint(
    ...
    row_data=t.row_data.to_dict(),
    ...
)

# engine/executors/aggregation.py:744-748
row_data = PipelineRow(deep_thaw(t.row_data), restored_contract)
```

The coalesce path does the same (`engine/coalesce_executor.py:201-212`, `engine/coalesce_executor.py:273-275`).

Tuple-valued row fields are a real supported engine state for `object`/`any` fields:
- `SchemaContract` explicitly allows `python_type=object` and skips type validation for those fields (`contracts/schema_contract.py:42`, `236-260`).
- The standard test helper intentionally builds `PipelineRow` rows with every field typed as `object` (`testing/__init__.py:162-189`).
- Downstream behavior can depend on tuple staying a tuple: `JSONExplode` has an explicit regression test asserting tuple input is an upstream bug and must raise `TypeError`, not be treated like a list (`tests/unit/plugins/transforms/test_json_explode.py:300-319`).

So a row buffered in a checkpoint as:

```python
{"items": ("a", "b", "c")}
```

will resume as:

```python
{"items": ["a", "b", "c"]}
```

That changes behavior from “crash on upstream bug” to “process successfully,” which violates the trust-model rule against sink/transform-side coercion and hides evidence of the original bad data shape.

The current tests miss this because checkpoint-serialization property tests only generate JSON primitives, lists, and dicts, not tuple/object payloads (`tests/property/core/test_checkpoint_serialization_properties.py:68-91`; `tests/strategies/json.py:13-37`).

## Root Cause Hypothesis

The module was updated to preserve `datetime`, but it still relies on vanilla JSON semantics for every other non-JSON-native Python container. That works for JSON-shaped payloads, but checkpoint row data is not restricted to JSON types when a field contract is `object`. As a result, tuple container type information is lost across checkpoint round-trips.

## Suggested Fix

Teach checkpoint serialization to envelope non-JSON-native containers that can legitimately appear inside `object` fields, at minimum tuples. A safe pattern is to add explicit tagged handling for tuple values in both dump and load paths, and recurse through tuples in `_reject_nan_infinity()` and `_escape_reserved_keys()`.

Example shape:

```python
{"__elspeth_type__": "tuple", "__elspeth_value__": [...]}
```

Then restore with:

```python
if envelope_type == "tuple" and isinstance(envelope_value, list):
    return tuple(_restore_types(v) for v in envelope_value)
```

Add integration coverage proving:
1. `checkpoint_loads(checkpoint_dumps({"items": ("a", "b")}))` returns a tuple.
2. A checkpointed row with tuple data still causes `JSONExplode` to raise after resume.

## Impact

Buffered aggregation/coalesce rows can resume with different payload types than the ones originally recorded. That can:
- Change transform behavior after crash recovery.
- Hide upstream contract violations that should have crashed.
- Break audit fidelity by making resumed processing observe a different row shape than the pre-crash pipeline saw.
---
## Summary

The deserializer silently accepts unknown `__elspeth_type__` envelopes instead of crashing on Tier 1 checkpoint corruption, which lets malformed or tampered checkpoint data pass through as ordinary dicts.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/core/checkpoint/serialization.py
- Line(s): 176-190, 196-212
- Function/Method: `_restore_types`, `checkpoint_loads`

## Evidence

`serialization.py` reserves `__elspeth_type__` / `__elspeth_value__` for system-owned envelopes and escapes user dicts containing those keys before serialization (`serialization.py:35-39`, `103-130`). On load, `_restore_types()` treats a two-key dict with those reserved keys as an envelope:

```python
# serialization.py:176-180
if _ENVELOPE_TYPE_KEY in obj and _ENVELOPE_VALUE_KEY in obj and len(obj) == 2:
    envelope_type = obj[_ENVELOPE_TYPE_KEY]
    envelope_value = obj[_ENVELOPE_VALUE_KEY]
```

But it only handles `"datetime"` and `"escaped_dict"` explicitly:

```python
# serialization.py:182-187
if envelope_type == "datetime" and isinstance(envelope_value, str):
    return datetime.fromisoformat(envelope_value)

if envelope_type == "escaped_dict" and isinstance(envelope_value, dict):
    return {k: _restore_types(v) for k, v in envelope_value.items()}
```

Any other reserved envelope shape falls through and is returned as a plain dict (`serialization.py:189-190`) instead of raising.

That violates the project’s Tier 1 rule for checkpoint data:
- CLAUDE.md says checkpoints are “our data” and must “crash on any anomaly.”
- The mandatory tier-model guidance says checkpoint/deserialized audit JSON is Tier 1 and missing/invalid structure must crash immediately.

The recovery path trusts `checkpoint_loads()` output as checkpoint truth:

```python
# core/checkpoint/recovery.py:169-177
raw = checkpoint_loads(checkpoint.aggregation_state_json)
agg_state = AggregationCheckpointState.from_dict(raw)

raw = checkpoint_loads(checkpoint.coalesce_state_json)
coalesce_state = CoalesceCheckpointState.from_dict(raw)
```

If a malformed checkpoint contains, for example,

```json
{"__elspeth_type__":"datetim","__elspeth_value__":"2026-02-08T10:15:30+00:00"}
```

inside `row_data`, the loader will not reject it. It will silently return that dict, and the checkpoint restore path will accept it as ordinary row payload.

There is test coverage for invalid datetime payload strings raising (`tests/property/core/test_checkpoint_serialization_properties.py:292-301`), but no coverage for unknown envelope types being rejected.

## Root Cause Hypothesis

The deserializer is written as a permissive “best effort” decoder for reserved envelopes, likely to avoid false positives on ordinary dicts. But because the serializer already escapes legitimate user dicts containing reserved keys, any exact two-key reserved envelope that is not one of ELSPETH’s known types should be treated as checkpoint corruption, not user data.

## Suggested Fix

Make `_restore_types()` fail closed for reserved envelopes:
- If a dict has exactly `__elspeth_type__` and `__elspeth_value__`, and the type is not a recognized ELSPETH envelope, raise `ValueError` (or a checkpoint-specific corruption error upstream).
- Likewise, reject wrong value shapes for known envelope types rather than silently returning the dict.

Example logic:

```python
if envelope_type == "datetime":
    if not isinstance(envelope_value, str):
        raise ValueError(...)
    return datetime.fromisoformat(envelope_value)

if envelope_type == "escaped_dict":
    if not isinstance(envelope_value, dict):
        raise ValueError(...)
    return {k: _restore_types(v) for k, v in envelope_value.items()}

raise ValueError(f"Unknown checkpoint envelope type: {envelope_type!r}")
```

Add tests for:
1. Unknown envelope type.
2. Known envelope type with wrong payload shape.
3. Corrupted envelope nested inside checkpoint row data.

## Impact

Malformed or tampered checkpoint JSON can be accepted as if it were legitimate user payload, which weakens audit integrity and violates the “crash on corruption” rule for Tier 1 data. Instead of surfacing checkpoint corruption immediately, the system can resume with silently altered row contents.
