## Summary

`_get_python_type()` collapses union annotations to a single type, so valid outputs for nullable/union fields are incorrectly flagged as contract violations.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/transform_contract.py`
- Line(s): 50-63, 117
- Function/Method: `_get_python_type`, `create_output_contract_from_schema`

## Evidence

`_get_python_type()` takes the first non-`None` union member:

```python
# transform_contract.py:50-60
if _is_union_type(unwrapped):
    args = get_args(unwrapped)
    for arg in args:
        if arg is not type(None):
            resolved = _get_python_type(arg)
            if resolved is not object:
                return resolved
```

`create_output_contract_from_schema()` then sets `required = field_info.is_required()` (line 117).
`SchemaContract.validate()` only allows `None` when `required == False` (`src/elspeth/contracts/schema_contract.py:264-267`).

Reproduced behavior from this repo:

- Schema `score: float | None` (required nullable) creates contract field `required=True, python_type=float`.
- `validate_output_against_contract({"score": None}, contract)` returns `TypeMismatchViolation`.
- Pydantic accepts that payload (`model_validate` passes).

Also reproduced:

- Schema `value: int | float` creates `python_type=int`.
- `{"value": 1.25}` is rejected by contract validation even though schema allows it.

## Root Cause Hypothesis

The transform contract model stores only one `python_type` and one `required` flag, but union/nullability semantics need richer representation. The current fallback of “pick first non-None type” loses schema meaning.

## Suggested Fix

In `transform_contract.py`, stop silently flattening unsupported unions.

- Parse annotation and detect:
  - required nullable (`T | None` with no default)
  - unions with multiple concrete non-`None` members
- For these cases, fail fast during contract creation with a clear exception (or extend contract model to represent nullable/union explicitly).
- Add tests in `tests/unit/contracts/test_transform_contract.py` for:
  - required nullable field accepting `None`
  - multi-type unions (`int | float`) accepting both members.

## Impact

If this helper is used for runtime output validation, valid rows can be falsely rejected/quarantined, violating schema-contract correctness and audit trace reliability. (Current in-repo usage appears limited, but exported API behavior is incorrect.)

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/transform_contract.py.md`
- Finding index in source report: 1
- Beads: pending
