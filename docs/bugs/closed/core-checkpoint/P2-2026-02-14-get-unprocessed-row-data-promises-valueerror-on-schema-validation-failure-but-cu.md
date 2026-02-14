## Summary

`get_unprocessed_row_data()` promises `ValueError` on schema validation failure but currently leaks raw `pydantic.ValidationError` without row context.

**CLOSED — False positive.** `pydantic.ValidationError` inherits from `ValueError` (`ValidationError.__mro__` = `ValidationError → ValueError → Exception → BaseException → object`). The docstring contract is satisfied. See triage notes.

## Severity

- Severity: not a bug (false positive)
- Priority: CLOSED

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py`
- Line(s): 204-207, 250-251
- Function/Method: `RecoveryManager.get_unprocessed_row_data`

## Evidence

Docstring contract:

```python
# recovery.py:204-207
Raises:
    ValueError: ... or if schema validation fails
```

Implementation does not wrap schema errors:

```python
# recovery.py:250-251
validated = source_schema_class.model_validate(degraded_data)
row_data = validated.to_row()
```

A strict schema validation failure raises `ValidationError` directly (verified via in-memory run), not `ValueError`, and the message lacks `row_id` context.

## Root Cause Hypothesis

Schema-fidelity enforcement was added, but exception normalization/error-context wrapping was not updated to match the method’s documented contract.

## Suggested Fix

Wrap `model_validate()` in `try/except ValidationError` and raise a `ValueError` including `run_id`/`row_id` and failing fields, e.g. `Resume failed for row <row_id>: schema validation failed ...`.

## Impact

Operational debugging is harder (no row-scoped context), and the function violates its own error contract, which can break callers/tests expecting `ValueError` semantics.

## Triage

- Status: closed (false positive)
- Closed reason: `pydantic.ValidationError` IS a `ValueError` subclass — the contract is not violated. The missing `row_id` context is a P4 improvement opportunity at best.
- Source report: `docs/bugs/generated/core/checkpoint/recovery.py.md`
- Finding index in source report: 2
