## Summary

`RuntimeRetryConfig.from_policy()` can raise raw `OverflowError`/non-actionable `ValueError` for non-finite `max_attempts`, violating its own “clear field-specific validation error” contract.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/config/runtime.py`
- Line(s): 53-87 (especially 75-76)
- Function/Method: `_validate_int_field`

## Evidence

`_validate_int_field` does:

- float branch: `return int(value)` (`src/elspeth/contracts/config/runtime.py:75-76`)
- no finite check and no exception normalization for float conversion.

Observed behavior from local repro:
- `RuntimeRetryConfig.from_policy({'max_attempts': float('nan')})` -> `ValueError: cannot convert float NaN to integer`
- `... float('inf')` -> `OverflowError: cannot convert float infinity to integer`

This bypasses the intended boundary error style used elsewhere in file (`Invalid retry policy: <field> ...`).

## Root Cause Hypothesis

Float-to-int conversion for `max_attempts` was implemented as direct coercion without guarding non-finite values or wrapping conversion exceptions into the module’s standardized validation error format.

## Suggested Fix

In `_validate_int_field`:

- Check `math.isfinite(value)` in the float branch.
- Wrap conversion errors and always raise `ValueError` with field name/context (`Invalid retry policy: max_attempts ...`).
- Add tests for `max_attempts` with `nan`, `inf`, `-inf`.

## Impact

Malformed retry policy input at this trust boundary produces inconsistent exception types/messages, reducing diagnosability and violating the contract of clear, actionable validation errors.

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/config/runtime.py.md`
- Finding index in source report: 2
- Beads: pending
