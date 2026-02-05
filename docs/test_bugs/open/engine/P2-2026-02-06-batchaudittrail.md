# Test Bug Report: Fix weak assertions in batch_audit_trail

## Summary

- This test file verifies audit trail recording for batch transforms, focusing on node state and external call records. The tests are valuable and test real audit trail behavior (unlike some other tests that mock `record_call`). However, there are coverage gaps - only success and error paths are tested, with no tests for partial failures, retries, or batch-specific scenarios despite the file claiming to test "batch transforms."

## Severity

- Severity: trivial
- Priority: P2
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_batch_audit_trail.audit.md

## Test File

- **File:** `tests/engine/test_batch_audit_trail`
- **Lines:** 411
- **Test count:** 2

## Findings

- **Lines 1-17 vs actual tests**: The docstring mentions "batch transforms" and "BatchTransformMixin uses worker threads" but the actual tests only verify single-row LLM transform execution. There are no tests that actually process multiple rows through the batch adapter or verify batch-specific audit trail behavior (e.g., batch_id correlation, multiple rows in single batch).
- **Line count vs test count**: 411 lines for only 2 test functions suggests either excessive boilerplate or tests that were planned but not implemented. The helper functions (lines 70-184) are well-designed but underutilized.
- **Lines 192-206**: The fixture correctly uses a temp file database instead of in-memory SQLite to handle multi-threaded access, with clear documentation of why this is necessary.
- **Lines 224-311**: `test_success_records_node_state_and_call` is a thorough test that verifies both node state and call records with appropriate assertions on all key fields (status, hashes, call type).
- **Lines 322-411**: `test_error_records_failed_node_state_and_error_call` properly tests the error path and verifies the error call has appropriate fields set (error_json populated, response_hash None).
- **Lines 180-184**: The `mock_azure_openai` context manager is well-implemented with proper mock response structure.


## Verdict Detail

**KEEP** - The existing tests are valuable and correctly verify audit trail recording for single-row success and error cases. However, the file should be expanded to include actual batch processing scenarios to match its documented purpose. Consider adding tests for batch-specific audit behavior.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_batch_audit_trail -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_batch_audit_trail.audit.md`
