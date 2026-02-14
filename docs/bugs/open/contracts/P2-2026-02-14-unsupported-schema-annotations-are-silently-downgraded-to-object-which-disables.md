## Summary

Unsupported schema annotations are silently downgraded to `object`, which disables type enforcement and allows invalid outputs to pass validation.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/transform_contract.py`
- Line(s): 40, 66-68
- Function/Method: `_get_python_type`

## Evidence

The function explicitly maps unknown annotations to `object`:

```python
# transform_contract.py:65-68
if unwrapped in ALLOWED_CONTRACT_TYPES:
    return cast(type, unwrapped)
return object
```

`SchemaContract.validate()` skips type checks for `object` fields (`src/elspeth/contracts/schema_contract.py:257-260`), so declared field types are not enforced.

Reproduced behavior from this repo:

- Schema `tags: list[str]` produces contract field `python_type=object`.
- `validate_output_against_contract({"tags": 123}, contract)` returns no violations.

That means a field declared as list accepts an int without error.

## Root Cause Hypothesis

`_get_python_type()` treats all unsupported annotations as “any”, conflating intentional `Any` with unsupported concrete types (like `list[str]`, `dict[...]`, custom models). This silently widens contracts.

## Suggested Fix

In `transform_contract.py`:

- Map only explicit `Any` to `object`.
- For unsupported annotations, raise a clear error during contract creation instead of widening.
- Add tests for `list[str]`/`dict[str, Any]` to ensure unsupported types fail fast (or are intentionally modeled).

## Impact

Schema mismatch bugs can pass undetected, allowing invalid transform output to be recorded as contract-compliant. This weakens contract enforcement and can hide plugin defects in audit trails.

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/transform_contract.py.md`
- Finding index in source report: 2
- Beads: pending
