## Summary

`JSONExplode` silently overwrites an existing non-array field when `output_field` collides, causing silent data loss and a stale/misleading schema contract.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/transforms/json_explode.py
- Line(s): 161, 176-177, 199-217
- Function/Method: `JSONExplode.process`

## Evidence

`base` keeps all non-array fields, then `output_field` is assigned unconditionally:

```python
# json_explode.py
base = {k: v for k, v in row_data.items() if k != normalized_array_field}
output = copy.deepcopy(base)
output[self._output_field] = item
```

If `self._output_field` already exists in `base`, the original value is overwritten with no error/quarantine.

Then contract propagation preserves old metadata for existing names (from `narrow_contract_to_output`), and JSONExplode only patches if field is missing:

- `/home/john/elspeth-rapid/src/elspeth/contracts/contract_propagation.py:110-114`
- `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/json_explode.py:203-217`

Runtime repro (executed): input had `item: str`, array exploded into dict elements with `output_field="item"`. Result was `status=success`, but contract `item` type remained `str` while actual `item` value was `dict`.

## Root Cause Hypothesis

The transform assumes `output_field` is always a new field and does not guard against collisions with existing row fields. Contract repair logic only handles "missing output field," not "colliding output field with changed semantics/type."

## Suggested Fix

Fail fast on collision in `process` before assignment:

```python
if self._output_field in base:
    raise ValueError(
        f"output_field '{self._output_field}' collides with existing field; "
        "choose a unique output_field to avoid data loss."
    )
```

Also add a unit test where input already has `output_field` and assert explicit failure.

## Impact

- Silent loss of original field value (audit-relevant data disappears without terminal error state).
- Contract/type metadata becomes incorrect for emitted rows.
- Downstream plugins may make wrong assumptions or crash based on stale contract types.
