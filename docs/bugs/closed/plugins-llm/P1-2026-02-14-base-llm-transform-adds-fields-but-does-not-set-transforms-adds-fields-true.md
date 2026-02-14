## Summary

`BaseLLMTransform` adds new output fields but does not mark itself as a schema-evolving transform, so node output contracts are never persisted during execution.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py`
- Line(s): `167-220`, `348-367`
- Function/Method: `BaseLLMTransform` (class attributes), `process`

## Evidence

`BaseLLMTransform.process()` adds fields (`<response_field>`, `_model`, `_usage`, template metadata) at `src/elspeth/plugins/llm/base.py:350-360`, and propagates a widened `SchemaContract` at `src/elspeth/plugins/llm/base.py:363-388`.

But `BaseLLMTransform` never sets `transforms_adds_fields = True` (it inherits `False` from `BaseTransform` at `src/elspeth/plugins/base.py:154`).
`TransformExecutor` only records evolved node output contracts when this flag is true (`src/elspeth/engine/executors/transform.py:332-351`).

Reproduction (read-only probe):
- With a `BaseLLMTransform` subclass as-is: `transforms_adds_fields False`, `recorder.get_node_contracts(...).output_contract is None`.
- Same subclass with `transforms_adds_fields = True`: output contract is persisted and includes LLM-added fields.

## Root Cause Hypothesis

The base class migrated to contract propagation logic in `process()` but missed the executor signaling flag that triggers node-level contract persistence.

## Suggested Fix

In `BaseLLMTransform`, set:

```python
transforms_adds_fields = True
```

Add a regression test that executes a `BaseLLMTransform` subclass through `TransformExecutor` and asserts `recorder.get_node_contracts(run_id, node_id)[1]` is non-`None` and contains LLM-added fields.

## Impact

Audit trail completeness is degraded for all `BaseLLMTransform` subclasses: node schema evolution is silently absent from `nodes.output_contract_json`, reducing explainability and contract traceability.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/base.py.md`
- Finding index in source report: 1
- Beads: pending
