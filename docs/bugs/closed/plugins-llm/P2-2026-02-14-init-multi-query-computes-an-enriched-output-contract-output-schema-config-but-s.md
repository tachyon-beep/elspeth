## Summary

`_init_multi_query()` computes an enriched output contract (`_output_schema_config`) but still sets `output_schema` to the original input schema, creating schema-contract drift for multi-query transforms.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base_multi_query.py`
- Line(s): `103-122`, `125-131`, `347-355`
- Function/Method: `_init_multi_query`, `_process_single_row_internal`

## Evidence

The file computes generated output fields into `_output_schema_config`:

```python
self._output_schema_config = SchemaConfig(
    ...
    guaranteed_fields=tuple(set(base_guaranteed) | all_guaranteed),
    audit_fields=tuple(set(base_audit) | all_audit),
)
```

But then `input_schema` and `output_schema` are both created from the original `schema_config`:

```python
schema = create_schema_from_config(schema_config, ...)
self.input_schema = schema
self.output_schema = schema
```

At runtime, the transform emits additional fields per query spec:

```python
all_fields_added = [
    f"{spec.output_prefix}_{field_config.suffix}" ...
]
output.update(result.row)
```

DAG type validation uses `output_schema` (not `_output_schema_config`) for producer type compatibility:
- `src/elspeth/core/dag/graph.py:1066-1068`
- `src/elspeth/core/dag/graph.py:1040`
- `src/elspeth/contracts/data.py:173-176`

So the declared output schema class can diverge from actual emitted row shape.

## Root Cause Hypothesis

Initialization mixes two schema systems but only one is used for runtime type schema (`output_schema`). The enriched multi-query output contract is computed for DAG metadata, but not reflected in the actual output schema class.

## Suggested Fix

Create distinct input/output schemas in `_init_multi_query()`:
- Keep `input_schema` from original `schema_config`.
- Build `output_schema` from an output schema config that includes generated multi-query fields (and their types) for fixed/flexible modes.
- Keep `_output_schema_config` aligned with the same output definition.

Also add an integration test where a downstream transform has explicit input schema requiring a generated multi-query field and ensure DAG validation/type checks pass correctly.

## Impact

Schema contract drift can cause incorrect DAG compatibility behavior and weakens protocol guarantees (`output_schema` no longer reliably describes emitted rows), especially for explicit-schema pipelines and downstream typed transforms.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/base_multi_query.py.md`
- Finding index in source report: 2
- Beads: pending
