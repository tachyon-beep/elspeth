## Summary

`propagate_contract()` and `narrow_contract_to_output()` silently drop new fields when `normalize_type_for_contract()` raises `TypeError`, causing row data and schema contract to diverge (and making those fields inaccessible in `FIXED` mode).

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/contract_propagation.py`
- Line(s): `53-59`, `150-163`
- Function/Method: `propagate_contract`, `narrow_contract_to_output`

## Evidence

`contract_propagation.py` skips unsupported new-field types instead of preserving them or failing:

```python
# propagate_contract
except TypeError:
    if type(value) in (dict, list):
        python_type = object
    else:
        continue
```

```python
# narrow_contract_to_output
except TypeError as e:
    if type(value) in (dict, list):
        python_type = object
    else:
        skipped_fields.append(name)
        ...
        continue
```

Supporting integration behavior:

- `normalize_type_for_contract()` rejects many non-primitive types (e.g., `Decimal`, tuples, custom objects) (`/home/john/elspeth-rapid/src/elspeth/contracts/type_normalization.py:24-36`, `91-99`).
- Canonical hashing accepts some of those values (e.g., `Decimal`, tuples), so runs can continue while contract metadata is missing (`/home/john/elspeth-rapid/src/elspeth/core/canonical.py:115-118`, `147-148`).
- `PipelineRow` denies access to fields not in contract under `FIXED` mode (`/home/john/elspeth-rapid/src/elspeth/contracts/schema_contract.py:552-560`), turning this into runtime breakage.
- Tests explicitly codify the skip behavior (`/home/john/elspeth-rapid/tests/unit/contracts/test_contract_propagation.py:529-548`, `/home/john/elspeth-rapid/tests/unit/contracts/test_contract_narrowing.py:126-144`).

Reproduced in repo with `.venv/bin/python`:
- `output_row` contained `price: Decimal("12.34")`
- resulting contract fields were only `['id']`
- `PipelineRow(output_row, contract).to_dict()` still had `price`
- `row['price']` raised `KeyError` in `FIXED` mode

## Root Cause Hypothesis

The implementation special-cases only exact `dict`/`list` types as `object` and silently skips all other `TypeError` cases, which hides contract propagation failures instead of preserving field lineage or failing fast.

## Suggested Fix

In this file, remove silent skip behavior for new fields:

- On `TypeError` from `normalize_type_for_contract()`, either:
  - map all unsupported-but-present new fields to `python_type=object`, or
  - raise a clear exception (preferred if enforcing strict plugin contract correctness).
- Do not `continue` silently for unsupported new field types.
- Keep behavior consistent between `propagate_contract()` and `narrow_contract_to_output()`.

Example direction:

```python
except TypeError:
    python_type = object  # preserve field in contract, avoid silent drop
```

(If strict policy is preferred, replace with `raise` plus actionable context.)

## Impact

- Contract/audit metadata can claim a field does not exist while row data contains it.
- In `FIXED` mode, downstream `row["field"]` and membership checks fail for those dropped fields.
- Original-name/header lineage for dropped fields is lost in sink header resolution.
- Violates auditability expectations by silently omitting schema evolution for actual emitted data.
