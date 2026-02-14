## Summary

`TypeMismatchViolation.to_error_reason()` serializes raw offending values into transform error payloads, contradicting its own non-exposure guarantee and allowing sensitive/unbounded data into persistent audit records.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/contracts/errors.py
- Line(s): 740-754 (and contradictory contract text at 695-700)
- Function/Method: `TypeMismatchViolation.to_error_reason`

## Evidence

`TypeMismatchViolation` explicitly says `actual_value` should not be exposed in logs/audit/error reports (`src/elspeth/contracts/errors.py:695-700`), but `to_error_reason()` does this:

```python
base.update(
    {
        "expected": self.expected_type.__name__,
        "actual": self.actual_type.__name__,
        "value": repr(self.actual_value),
    }
)
```

(`src/elspeth/contracts/errors.py:748-754`)

This helper is documented as producing payloads for `TransformResult.error()` (`src/elspeth/contracts/errors.py:653-658`), and those payloads are persisted in Landscape:

- `src/elspeth/core/landscape/_error_recording.py:133-169` (`error_details_json=canonical_json(error_details)`)

Tests currently enforce the leaking behavior (`tests/unit/contracts/test_contract_violation_error.py:157-183`).

## Root Cause Hypothesis

A debugging-oriented implementation (`repr(actual_value)`) was added to `to_error_reason()` without reconciling the security/privacy contract documented in the same class.

## Suggested Fix

In `src/elspeth/contracts/errors.py`, remove raw value emission from `TypeMismatchViolation.to_error_reason()` (or replace with bounded/redacted metadata such as hash + length). Keep `expected`/`actual` type details.

Example direction:

```python
base.update(
    {
        "expected": self.expected_type.__name__,
        "actual": self.actual_type.__name__,
        # no raw value
    }
)
```

Also update the `TransformErrorReason` docs/type comments to match the chosen policy.

## Impact

Sensitive row content and very large values can be permanently written into Tier-1 audit records, violating stated audit/privacy intent and increasing storage/serialization risk on error-heavy runs.
