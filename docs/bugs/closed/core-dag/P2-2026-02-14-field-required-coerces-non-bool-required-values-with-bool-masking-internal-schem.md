## Summary

`_field_required()` coerces non-bool `required` values with `bool(...)`, masking internal schema corruption instead of failing fast.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P2 during triage — bool() coercion violates fail-fast, but input path never produces non-bool values; no realistic trigger)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/dag/builder.py`
- Line(s): `81-84`, usage at `831`
- Function/Method: `_field_required` (used during coalesce union schema merge)

## Evidence

Current logic:

```python
if "required" in field_spec:
    return bool(field_spec["required"])
```

This silently coerces invalid Tier-1/internal values. Repro (executed):

```text
'false' -> True
'0' -> True
0 -> False
```

So malformed internal data can be reinterpreted instead of crashing. `_field_required()` is used in union merge optionality logic at `/home/john/elspeth-rapid/src/elspeth/core/dag/builder.py:831`, so coercion can produce incorrect merged field optionality.

## Root Cause Hypothesis

Defensive/coercive conversion (`bool(...)`) was used where strict internal contract validation is required. This violates the project’s fail-fast rule for system-owned data.

## Suggested Fix

In `_field_required()`:

- Require `type(field_spec["required"]) is bool`.
- Raise `GraphValidationError` (or `TypeError`) when it is not exactly bool.
- Do not coerce.

Example behavior: invalid `required` types should crash during DAG build.

## Impact

- Incorrect coalesce merged schema optionality.
- Potential false contract validation outcomes downstream.
- Internal data corruption can be hidden instead of surfaced immediately.

## Triage

- Status: open (downgraded P2 → P3)
- Source report: `docs/bugs/generated/core/dag/builder.py.md`
- Finding index in source report: 2
- Beads: pending
- Triage note: Input path to `_field_required` always provides proper bools from Pydantic-validated sources. The `bool()` coercion is a Tier 1 violation but has no realistic trigger. Fix when convenient.
