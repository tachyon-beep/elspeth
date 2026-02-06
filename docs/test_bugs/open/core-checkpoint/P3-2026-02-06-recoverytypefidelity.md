# Test Bug Report: Fix weak assertions in recovery_type_fidelity

## Summary

- This test file validates an important bug fix (Bug #4): type fidelity preservation when restoring row data from canonical JSON during resume. The test creates rows with datetime and Decimal fields, stores them via canonical_json(), then verifies that get_unprocessed_row_data() correctly restores the original types using the provided schema. While the test is valuable and comprehensive, there are structural issues to note.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_core_checkpoint_test_recovery_type_fidelity.py.audit.md

## Test File

- **File:** `tests/core/checkpoint/test_recovery_type_fidelity.py`
- **Lines:** 224
- **Test count:** 1

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - The test validates an important type fidelity bug fix. However, consider adding additional tests for edge cases (schema mismatch, different types, missing schema parameter enforcement). The single test is comprehensive for the happy path but leaves some scenarios uncovered.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/core/checkpoint/test_recovery_type_fidelity.py -v`

## Notes

- Source audit: `docs/test_audit/tests_core_checkpoint_test_recovery_type_fidelity.py.audit.md`
