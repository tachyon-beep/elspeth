# Test Bug Report: Fix weak assertions in azure_content_safety_contract

## Summary

- This file sets up contract tests for AzureContentSafety by inheriting from BatchTransformContractTestBase. However, the file itself contains zero actual test methods - all tests come from the base class. While this is a valid testing pattern, it means the audit cannot verify what tests actually run without reading the base class file. The fixtures are properly configured with HTTP mocking.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_contracts_transform_contracts_test_azure_content_safety_contract.audit.md

## Test File

- **File:** `tests/contracts/transform_contracts/test_azure_content_safety_contract`
- **Lines:** 92
- **Test count:** 0

## Findings

- **Line 54-92:**: The test class `TestAzureContentSafetyBatchContract` defines only fixtures and inherits all tests from `BatchTransformContractTestBase`. This creates a risk that if the base class is modified or deleted, this file silently provides no test coverage. Consider adding at least one explicit test method to verify the base class tests are running.
- **Line 45-51:**: `_make_mock_context()` is defined but never used in this file. It may be used by the inherited tests but this is not verifiable without reading the base class.
- **Lines 23-42:**: Helper functions `_make_safe_response()` and `_create_mock_http_response()` are well-structured for creating test fixtures.


## Verdict Detail

KEEP - The file serves its purpose of parameterizing the base contract tests for AzureContentSafety. However, the reliance on inherited tests means coverage depends entirely on the base class. Adding one explicit sanity test would improve confidence.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/contracts/transform_contracts/test_azure_content_safety_contract -v`

## Notes

- Source audit: `docs/test_audit/tests_contracts_transform_contracts_test_azure_content_safety_contract.audit.md`
