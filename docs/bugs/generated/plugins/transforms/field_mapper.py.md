## Summary

`FieldMapper` publishes the input schema as its `_output_schema_config`, so DAG validation still treats renamed or dropped input fields as guaranteed output fields.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [src/elspeth/plugins/transforms/field_mapper.py](/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py)
- Line(s): 101, 106, 169, 173
- Function/Method: `FieldMapper.__init__`, `FieldMapper.process`

## Evidence

In [field_mapper.py](/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py#L101), the plugin builds a dynamic `output_schema`, but in [field_mapper.py](/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py#L106) it sets `_output_schema_config` by copying the input schema config:

```python
self.input_schema, self.output_schema = self._create_schemas(
    cfg.schema_config,
    "FieldMapper",
    adds_fields=True,
)
self._output_schema_config = self._build_output_schema_config(cfg.schema_config)
```

`_build_output_schema_config()` in [base.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/base.py#L251) preserves `schema_config.fields` from the input schema and only unions in `declared_output_fields`:

```python
return SchemaConfig(
    mode=schema_config.mode,
    fields=schema_config.fields,
    guaranteed_fields=tuple(set(base_guaranteed) | self.declared_output_fields),
    ...
)
```

Then DAG validation in [graph.py](/home/john/elspeth/src/elspeth/core/dag/graph.py#L1429) and [schema.py](/home/john/elspeth/src/elspeth/contracts/schema.py#L460) treats required declared fields as implicitly guaranteed output fields. That means a config like `schema: {mode: fixed, fields: ["old_name: str"]}` plus `mapping: {"old_name": "new_name"}` still advertises `old_name` as guaranteed downstream, even though `process()` explicitly deletes it in [field_mapper.py](/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py#L148) and narrows the runtime contract to the actual output in [field_mapper.py](/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py#L170).

Existing tests already prove the runtime row/contract remove old fields:
- [test_field_mapper.py](/home/john/elspeth/tests/unit/plugins/transforms/test_field_mapper.py#L459) asserts `new_field` is present and `old_field` is absent from the output contract.
- [test_field_mapper.py](/home/john/elspeth/tests/unit/plugins/transforms/test_field_mapper.py#L482) asserts `select_only=True` leaves only `{"kept"}` in the output contract.

So the bug is not in runtime row shaping; it is the stale DAG metadata published by `field_mapper.py`.

## Root Cause Hypothesis

`FieldMapper` reuses the generic `_build_output_schema_config()` helper even though this transform removes and renames fields. That helper is safe for field-adding transforms, but `FieldMapper` is shape-changing in both directions, so copying the input `SchemaConfig.fields` into output metadata leaves upstream-required fields attached to the output contract.

## Suggested Fix

Build a `SchemaConfig` that reflects the mapped output shape instead of reusing the input schema config verbatim.

For `select_only=True`, output `fields` should contain only mapped targets.
For renames, the old source field should be removed from `fields` and replaced with the target field.
For non-renamed passthrough fields, keep them only when `select_only=False`.

Also add a DAG-level test showing that a downstream transform requiring a renamed-away field is rejected.

## Impact

Downstream `required_input_fields` checks can pass when they should fail, because the graph claims `FieldMapper` still guarantees fields it deleted or renamed. That creates schema-contract drift between build-time validation and runtime behavior, so a pipeline can be accepted even though downstream nodes will later fail on missing fields.
---
## Summary

`FieldMapper` defaults `validate_input` to `False`, so it silently forwards Tier 2 type-contract violations instead of crashing on upstream plugin bugs.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [src/elspeth/plugins/transforms/field_mapper.py](/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py)
- Line(s): 34, 91
- Function/Method: `FieldMapperConfig`, `FieldMapper.__init__`

## Evidence

In [field_mapper.py](/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py#L34), `validate_input` defaults to `False`, and [field_mapper.py](/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py#L91) copies that directly onto the transform instance.

The executor only validates input schemas when that flag is true, as shown in [transform.py](/home/john/elspeth/src/elspeth/engine/executors/transform.py#L228):

```python
if transform.validate_input:
    transform.input_schema.model_validate(input_dict)
```

The current unit test suite explicitly demonstrates the bad behavior in [test_field_mapper.py](/home/john/elspeth/tests/unit/plugins/transforms/test_field_mapper.py#L265): a schema declaring `count: int` still allows `"not_an_int"` to pass through successfully when `validate_input=False`.

That conflicts with the contract stated in `CLAUDE.md`: transforms receive Tier 2 pipeline data and must not tolerate wrong types from upstream plugins; wrong types are upstream bugs that should crash, not be passed through.

## Root Cause Hypothesis

`FieldMapper` kept an opt-in validation switch for backward compatibility instead of enforcing transform input contracts unconditionally. Because this transform usually just copies/renames fields, it often performs no value-level operation that would naturally fail, so bad upstream types can travel through unnoticed unless schema validation is forced on.

## Suggested Fix

Make input validation mandatory for `FieldMapper`.

Practical options:
- Change `FieldMapperConfig.validate_input` to default `True` and remove the ability to disable it.
- Or ignore the config flag entirely in this plugin and always set `self.validate_input = True`.

Add a test that asserts a fixed-schema `FieldMapper` raises `PluginContractViolation` when given a row whose field type violates the declared input schema.

## Impact

A misbehaving source or upstream transform can emit schema-invalid data, and `FieldMapper` will still record a successful transform step while forwarding the bad value downstream. That breaks the Tier 2 contract, hides system-owned plugin bugs, and lets audit records claim successful processing of data that did not conform to the transform’s declared schema.
