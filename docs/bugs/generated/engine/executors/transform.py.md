## Summary

TransformExecutor records the wrong transform output contract in Landscape, and for `success_multi()` it records no transform output contract at all.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/executors/transform.py
- Line(s): 381-397
- Function/Method: `TransformExecutor.execute_transform`

## Evidence

`TransformExecutor` only persists schema evolution when `result.row is not None`, and it recomputes that contract from the output dict instead of using the `PipelineRow.contract` the plugin already returned:

```python
if result.row is not None and transform.declared_output_fields:
    from elspeth.contracts.contract_propagation import propagate_contract

    input_contract = token.row_data.contract
    evolved_contract = propagate_contract(
        input_contract=input_contract,
        output_row=result.row.to_dict(),
        transform_adds_fields=True,
    )
    self._recorder.update_node_output_contract(...)
```

Source: [transform.py](/home/john/elspeth/src/elspeth/engine/executors/transform.py#L381)

That is incompatible with how several transforms actually construct their output contracts:

```python
output_contract = narrow_contract_to_output(
    input_contract=row.contract,
    output_row=output,
    renamed_fields=applied_mappings,
)
return TransformResult.success(PipelineRow(output, output_contract), ...)
```

Source: [field_mapper.py](/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py#L169)

`narrow_contract_to_output()` explicitly preserves removals and rename lineage, while `propagate_contract()` only appends new fields to the input contract and keeps removed fields alive:

```python
def propagate_contract(...):
    existing_names = {f.normalized_name for f in input_contract.fields}
    ...
    return SchemaContract(
        mode=input_contract.mode,
        fields=input_contract.fields + tuple(new_fields),
        locked=True,
    )
```

Source: [contract_propagation.py](/home/john/elspeth/src/elspeth/contracts/contract_propagation.py#L21)

For multi-row transforms the executor never calls `update_node_output_contract()` at all, even though those transforms return a real shared contract:

```python
return TransformResult.success_multi(
    [PipelineRow(r, output_contract) for r in output_rows],
    ...
)
```

Source: [json_explode.py](/home/john/elspeth/src/elspeth/plugins/transforms/json_explode.py#L255)

Landscape node registration does not pre-populate transform `output_contract`; only the source gets one at registration time:

```python
output_contract = None
if node_id == source_id:
    output_contract = config.source.get_schema_contract()
recorder.register_node(..., output_contract=output_contract)
```

Source: [core.py](/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L1323)

So today:
- single-row transforms with renames/removals record a degraded contract
- multi-row transforms with declared output fields leave `nodes.output_contract_json` unset

## Root Cause Hypothesis

The executor treats contract auditing as “recompute schema evolution from row dict” instead of “persist the contract the plugin actually emitted.” That assumption only holds for the simplest add-field case. It breaks for transforms whose contract logic is richer than `propagate_contract()` and completely misses `success_multi()` paths.

## Suggested Fix

Use the contract already attached to the transform result and persist it for both single-row and multi-row success paths.

Suggested shape:

```python
output_contract = None
if result.row is not None:
    output_contract = result.row.contract
elif result.rows is not None:
    output_contract = result.rows[0].contract

if output_contract is not None and transform.declared_output_fields:
    self._recorder.update_node_output_contract(
        run_id=ctx.run_id,
        node_id=transform.node_id,
        contract=output_contract,
    )
```

Also remove the local `propagate_contract()` recomputation from the executor; contract construction belongs in the plugin/result object that already knows about renames, removals, and heterogeneous-field typing.

## Impact

Landscape’s node-level schema lineage is incomplete or wrong for transform outputs. In an audit-focused system, that means the legal record can say a transform still guarantees removed fields, lose original-name lineage on renamed fields, or say nothing at all for multi-row/deaggregation transforms. That weakens explainability and violates the project’s “if it’s not recorded, it didn’t happen” audit standard.
