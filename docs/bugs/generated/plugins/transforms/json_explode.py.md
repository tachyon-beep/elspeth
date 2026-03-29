## Summary

`JSONExplode` publishes a stale DAG output contract that still guarantees the deleted `array_field`, so downstream nodes can validate against fields that `json_explode` has already removed.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/json_explode.py
- Line(s): 130-135
- Function/Method: `JSONExplode.__init__`

## Evidence

`JSONExplode` removes the array field from each emitted row:

```python
base = {k: v for k, v in row_data.items() if k != normalized_array_field}
...
success_reason={"fields_removed": [self._array_field]}
```

Evidence:
- `/home/john/elspeth/src/elspeth/plugins/transforms/json_explode.py:170`
- `/home/john/elspeth/src/elspeth/plugins/transforms/json_explode.py:260`

But its DAG contract is built with the generic helper that preserves the input schema fields and only unions in added fields:

```python
self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

Evidence:
- `/home/john/elspeth/src/elspeth/plugins/transforms/json_explode.py:135`
- `/home/john/elspeth/src/elspeth/plugins/infrastructure/base.py:251-258`

That is wrong for a shape-changing transform. The contract layer explicitly documents that `JSONExplode` removes `array_field`:
- `/home/john/elspeth/src/elspeth/contracts/contract_propagation.py:87-92`

And the DAG validator trusts `output_schema_config` as the producer contract:
- `/home/john/elspeth/src/elspeth/core/dag/graph.py:1375-1398`
- `/home/john/elspeth/src/elspeth/core/dag/graph.py:1055-1075`

For fixed/flexible schemas this is worse than just `guaranteed_fields`: required declared fields are implicitly guaranteed, so leaving the original `fields` list in place still advertises the removed array field:
- `/home/john/elspeth/src/elspeth/contracts/schema.py:460-478`

What the code does:
- Says the output still has the input schema plus `output_field`/`item_index`.

What it should do:
- Publish an output schema/config that removes `array_field` and adds only the actual emitted fields.

## Root Cause Hypothesis

`JSONExplode` is using the generic “add fields” helper even though it is not additive; it both removes and adds fields. The runtime row contract is narrowed correctly in `process()`, but the build-time DAG contract is left in pre-explode shape.

## Suggested Fix

Build a custom `_output_schema_config` in `JSONExplode.__init__` instead of calling the generic helper. It should:

- Remove `array_field` from `fields`
- Remove `array_field` from `guaranteed_fields`
- Add `output_field`
- Add `item_index` when enabled

Also add a DAG test where a downstream transform declares `required_input_fields: ["items"]` after `json_explode`; graph construction should fail.

## Impact

Broken pipelines can pass DAG validation and then fail later when a downstream transform accesses the supposedly guaranteed array field. In audit terms, the plugin advertises a contract the emitted rows do not satisfy, undermining schema-based routing and contract validation.
---
## Summary

`JSONExplode` allows `output_field="item_index"` while `include_index=True`, which overwrites the exploded item with the index and silently loses data.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/json_explode.py
- Line(s): 63-67, 184-188
- Function/Method: `JSONExplodeConfig._reject_field_collision`, `JSONExplode.process`

## Evidence

The config validator only rejects `output_field == array_field`:

```python
if self.output_field == self.array_field:
    raise ValueError(...)
```

Evidence:
- `/home/john/elspeth/src/elspeth/plugins/transforms/json_explode.py:63-67`

But the row-building logic writes both `output_field` and `item_index` into the same dict:

```python
output[self._output_field] = item
if self._include_index:
    output["item_index"] = i
```

Evidence:
- `/home/john/elspeth/src/elspeth/plugins/transforms/json_explode.py:184-188`

So with:

```yaml
output_field: item_index
include_index: true
```

the second assignment overwrites the exploded item. The emitted row becomes `{"item_index": 0}` instead of containing both the item and index. No exception is raised, and the audit trail records a successful transform.

There is test coverage for the normal `item` + `item_index` path, but no test guarding this collision case:
- `/home/john/elspeth/tests/unit/plugins/transforms/test_json_explode.py:55-58`
- `/home/john/elspeth/tests/unit/plugins/transforms/test_json_explode.py:793-806`

## Root Cause Hypothesis

Validation only considered collisions with the input array field, not with the transform’s own optional synthetic field. Because `item_index` is added later in `process()`, the overwrite happens inside the target file and is never caught by executor-level collision checks.

## Suggested Fix

Reject this configuration in `JSONExplodeConfig._reject_field_collision`, e.g. fail when `include_index` is true and `output_field == "item_index"`.

Add a unit test asserting that:

- `JSONExplode({"output_field": "item_index", "include_index": True, ...})`
- raises `PluginConfigError` or validation `ValueError`

## Impact

This is silent data loss. The transform reports success while dropping the exploded payload and replacing it with the ordinal, so downstream sinks and the audit record contain incorrect transformed data.
