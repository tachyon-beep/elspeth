# Test Bug Report: Fix weak assertions in contract_violations

## Summary

- This file tests schema contract violation exception types (ContractViolation, MissingFieldViolation, TypeMismatchViolation, ExtraFieldViolation, ContractMergeError). Tests verify that exception classes store attributes correctly and produce meaningful error messages. Coverage is reasonable but the tests exhibit significant granularity problems.

## Severity

- Severity: trivial
- Priority: P2
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_contracts_test_contract_violations.py.audit.md

## Test File

- **File:** `tests/contracts/test_contract_violations.py`
- **Lines:** 244
- **Test count:** 21

## Findings

- **Lines 16-47 (TestContractViolationBase):**: Four tests to verify a dataclass stores two attributes and has a message. Tests `test_contract_violation_stores_normalized_name` and `test_contract_violation_stores_original_name` could be combined into one test.
- **Lines 49-83 (TestMissingFieldViolation):**: Four tests where three of them (`test_missing_field_stores_names`, `test_missing_field_message_contains_required`, `test_missing_field_message_shows_original_normalized_format`) could be combined. All create identical exception objects.
- **Lines 85-162 (TestTypeMismatchViolation):**: Six tests all creating the same `TypeMismatchViolation` with identical arguments. Tests for `stores_expected_type`, `stores_actual_type`, `stores_actual_value` could be a single test.
- **Lines 164-196 (TestExtraFieldViolation):**: Four tests all creating identical exceptions to check one property each.
- **Lines 198-243 (TestContractMergeError):**: Six tests, all creating identical `ContractMergeError` objects. Tests for `stores_field`, `stores_type_a`, `stores_type_b` should be one test.
- **Lines 66-72 (test_missing_field_message_contains_required):**: The test uses `or` assertion (`assert "required" in msg or "missing" in msg`) which is flexible but could mask a regression if the message format changes unexpectedly.
- **Lines 189-195 (test_extra_field_message_mentions_fixed_mode):**: Converting message to uppercase with `.upper()` and checking for "FIXED" is unusual - this checks case-insensitively but could pass if "fixed" appears anywhere in the message by coincidence.


## Verdict Detail

**KEEP** - Tests are correct and verify the exception classes work as intended. The excessive granularity is a code quality issue, not a correctness issue. These tests would benefit from consolidation but are not actively harmful.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/contracts/test_contract_violations.py -v`

## Notes

- Source audit: `docs/test_audit/tests_contracts_test_contract_violations.py.audit.md`
