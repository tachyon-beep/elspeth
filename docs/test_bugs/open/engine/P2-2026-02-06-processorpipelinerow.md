# Test Bug Report: Rewrite weak assertions in processor_pipeline_row

## Summary

- This file tests the PipelineRow support in RowProcessor (Task 6 of some migration). While the tests verify the API contract, they rely heavily on mock objects which reduces their integration value. The tests are focused but thin - they verify that the correct methods are called but don't verify the data flows correctly through the system.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **REWRITE**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_processor_pipeline_row.audit.md

## Test File

- **File:** `tests/engine/test_processor_pipeline_row`
- **Lines:** 182
- **Test count:** 5

## Findings

- See audit file for details


## Verdict Detail

**REWRITE** - The tests verify API contracts exist but use excessive mocking that hides integration issues. These tests should be rewritten to use real `LandscapeDB.in_memory()` instances like other processor tests. The contract enforcement test (lines 112-141) is the only test that provides genuine value without mocking concerns.

## Proposed Fix

- [ ] Tests have specific, non-permissive assertions
- [ ] Each test verifies the exact expected behavior
- [ ] No "or 'error' in output" fallback patterns
- [ ] Tests fail when actual behavior differs from expected

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_processor_pipeline_row -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_processor_pipeline_row.audit.md`
