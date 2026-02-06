# Test Bug Report: Fix weak assertions in keyword_filter_contract

## Summary

- This file provides concrete implementations of two test base classes for the KeywordFilter transform. It correctly provides fixtures for both property-based contract tests and error contract tests. However, there are some concerns about accessing private attributes in assertions.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_contracts_transform_contracts_test_keyword_filter_contract.audit.md

## Test File

- **File:** `tests/contracts/transform_contracts/test_keyword_filter_contract`
- **Lines:** 59
- **Test count:** 0

## Findings

- **Line 30:**: `assert t._on_error is not None` accesses a private attribute (`_on_error`) in the fixture. This is a code smell - tests should not depend on private implementation details. If verifying error handling configuration is necessary, it should be done through public interface or the assertion should be removed.
- **Line 49:**: Same issue - `assert t._on_error is not None` accesses private attribute.
- **Line 19-31:**: The test class structure is good - it correctly inherits from `TransformContractPropertyTestBase` to get property-based testing.
- **Line 38-58:**: The error contract test class provides appropriate `error_input` fixture with content that triggers the keyword filter.


## Verdict Detail

KEEP - The overall structure is correct and the inherited tests provide strong coverage. The private attribute access is a minor violation that should be addressed but does not invalidate the tests.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/contracts/transform_contracts/test_keyword_filter_contract -v`

## Notes

- Source audit: `docs/test_audit/tests_contracts_transform_contracts_test_keyword_filter_contract.audit.md`
