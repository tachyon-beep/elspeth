# Bug Report: Schema Config Errors Escape Validator Instead of Returning Structured Errors

## Summary

- Schema validation errors raise exceptions instead of returning structured error objects, breaking error handling contract.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Branch Bug Scan
- Date: 2026-01-25
- Related run/issue ID: BUG-SCHEMA-01

## Evidence

- `src/elspeth/core/landscape/schema.py` - Validation raises instead of returning errors

## Impact

- Error handling: Cannot programmatically handle validation errors

## Proposed Fix

- Return structured ValidationError objects instead of raising:
  ```python
  def validate(data):
      try:
          return ValidatedData(data)
      except Exception as e:
          return ValidationError(reason=str(e), data=data)
  ```

## Acceptance Criteria

- Validation returns error objects, doesn't raise

## Tests

- New tests required: yes, error handling test
