# Test Bug Report: Fix weak assertions in contract_violation_error

## Summary

- This file tests the `to_error_reason()` methods on contract violation exception types and the `violations_to_error_reason()` helper function. The tests are straightforward and cover the API surface well. However, there is significant repetition across test classes that could be parameterized, and some individual tests are overly granular.

## Severity

- Severity: trivial
- Priority: P2
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_contracts_test_contract_violation_error.py.audit.md

## Test File

- **File:** `tests/contracts/test_contract_violation_error.py`
- **Lines:** 326
- **Test count:** 22

## Findings

- **Lines 20-60 (TestContractViolationToErrorReason):**: Five separate tests each create identical `ContractViolation` objects and call `to_error_reason()` to assert one key at a time. This is excessive granularity - could be a single test with multiple assertions or parameterized test checking all keys.
- **Lines 62-96 (TestMissingFieldViolationToErrorReason):**: Same pattern - four tests each creating the same `MissingFieldViolation` and checking one property. This is duplicate setup that should be consolidated.
- **Lines 186-212 (TestExtraFieldViolationToErrorReason):**: Same pattern again - three tests with identical setup.
- **Lines 248-278:**: Tests `test_multiple_violations_has_count`, `test_multiple_violations_has_violations_list`, and `test_multiple_violations_list_contains_error_reasons` all create nearly identical violation lists and could be one test.
- **Lines 303-325 (test_three_violations_has_correct_count):**: Tests the same behavior as lines 248-261 but with three violations instead of two. This is redundant - if two violations work, three will work.
- **Lines 17-60:**: Imports are inside each test method rather than at module level. While this is a valid pattern for isolation, it creates significant duplication.
- **Line 326:**: File ends without blank line (minor formatting).


## Verdict Detail

**KEEP** - The tests are correct and provide coverage for the `to_error_reason()` API. The inefficiency is real but not critical enough to warrant rewrite. The tests serve their purpose of verifying the contract violation to error reason conversion works.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/contracts/test_contract_violation_error.py -v`

## Notes

- Source audit: `docs/test_audit/tests_contracts_test_contract_violation_error.py.audit.md`
