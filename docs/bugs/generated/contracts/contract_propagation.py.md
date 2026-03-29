## Summary

`propagate_contract()` and `narrow_contract_to_output()` infer a newly added field with value `None` as hard `NoneType`, which makes node output contracts order-dependent and can later trigger false contract conflicts for transforms like RAG that legitimately emit `None` on some rows and `float`/`str` on others.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/contract_propagation.py`
- Line(s): 48-68, 125-175
- Function/Method: `propagate_contract`, `narrow_contract_to_output`

## Evidence

`propagate_contract()` infers new field types directly from the first observed value:

```python
for name, value in output_row.items():
    if name not in existing_names:
        python_type = normalize_type_for_contract(value)
        new_fields.append(
            FieldContract(
                normalized_name=name,
                original_name=name,
                python_type=python_type,
                required=False,
                source="inferred",
            )
        )
```

[`/home/john/elspeth/src/elspeth/contracts/contract_propagation.py#L48`](#/home/john/elspeth/src/elspeth/contracts/contract_propagation.py#L48)

`normalize_type_for_contract(None)` returns `type(None)`:

```python
if value is None:
    return type(None)
```

[`/home/john/elspeth/src/elspeth/contracts/type_normalization.py#L54`](#/home/john/elspeth/src/elspeth/contracts/type_normalization.py#L54)

The same pattern exists in `narrow_contract_to_output()` for inferred fields:

[`/home/john/elspeth/src/elspeth/contracts/contract_propagation.py#L148`](#/home/john/elspeth/src/elspeth/contracts/contract_propagation.py#L148)

This is not theoretical. The RAG transform emits the same added field as `None` when no retrieval results are found:

```python
output[self._field_score] = None
```

[`/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L229`](#/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L229)

and as `float` when results are found:

```python
best_score = chunks[0].score
output[self._field_score] = best_score
```

[`/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L249`](#/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L249)

The engine records the transform’s evolved output contract on every successful row, with no output-schema validation step beforehand:

- input validation only: [`/home/john/elspeth/src/elspeth/engine/executors/transform.py#L225`](#/home/john/elspeth/src/elspeth/engine/executors/transform.py#L225)
- per-row contract update: [`/home/john/elspeth/src/elspeth/engine/executors/transform.py#L377`](#/home/john/elspeth/src/elspeth/engine/executors/transform.py#L377)

and `update_node_output_contract()` simply overwrites the node contract:

```python
.values(output_contract_json=output_contract_json)
```

[`/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L1219`](#/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py#L1219)

So a mixed RAG run can record `rag_score` as `NoneType` or `float` depending on which row updated the node last.

If those per-row contracts are later merged, ELSPETH treats `NoneType` vs `float` as a hard conflict:

```python
if self_fc.python_type != other_fc.python_type:
    raise ContractMergeError(...)
```

[`/home/john/elspeth/src/elspeth/contracts/schema_contract.py#L462`](#/home/john/elspeth/src/elspeth/contracts/schema_contract.py#L462)

There is also an existing unit test that codifies the problematic behavior instead of guarding against it:

[`/home/john/elspeth/tests/unit/contracts/test_contract_propagation.py#L492`](#/home/john/elspeth/tests/unit/contracts/test_contract_propagation.py#L492)

What the code does:
- Treats first-observed `None` as the field’s real type.

What it should do:
- Treat `None` as absence for a newly inferred field, not as proof that the field’s only valid type is `NoneType`.

## Root Cause Hypothesis

The propagation helpers are using single-row value inspection as if it were sufficient to determine the stable schema of newly added fields. That works for concrete non-null values, but it fails for optional fields where the first observed value is `None`. In ELSPETH, `None` is often a truthful “no value” sentinel, not a schema declaration.

Because these helpers freeze the contract immediately, they turn an observation about one row into a hard type claim for the whole node.

## Suggested Fix

Change inference for newly added `None` values in this file so they do not become hard `NoneType` fields.

A safe fix in this module would be to special-case `None` before `normalize_type_for_contract()` and emit a widened contract entry, for example:

- `python_type=object`, `nullable=True`, `source="inferred"`

for newly inferred fields whose current value is `None`.

That avoids:
- order-dependent node contracts
- false `ContractMergeError` on later `float`/`str` observations
- misrepresenting optional fields as “must be None”

If ELSPETH wants stronger typing later, add an explicit widening rule in this module rather than freezing `NoneType` from first observation.

## Impact

This can corrupt the reported output schema for a transform node in the audit trail, making it depend on row order instead of actual transform semantics. It also creates false type conflicts when contracts are merged later, even though the underlying behavior is valid optional output.

Affected data:
- any transform that adds optional fields and can emit `None` before a concrete value
- confirmed reachable with RAG’s `*_rag_score` field

Audit guarantees violated:
- node output contracts can become nondeterministic across identical runs with different row ordering
- the recorded contract can claim a field is `NoneType` when the same transform legitimately emits `float` later
