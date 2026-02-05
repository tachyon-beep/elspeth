# Test Bug Report: Fix weak assertions in coalesce_pipeline_row

## Summary

- This test file verifies CoalesceExecutor's handling of PipelineRow objects and contract merging. The tests cover important scenarios including contract merging across branches, crash behavior for missing contracts, and merge policy variations. However, the tests rely heavily on mocks which reduces confidence in integration with real components.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_coalesce_pipeline_row.py.audit.md

## Test File

- **File:** `tests/engine/test_coalesce_pipeline_row.py`
- **Lines:** 396
- **Test count:** 6

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - The tests provide useful unit-level coverage of CoalesceExecutor's contract merging logic and error handling. However, consider:
1. Adding integration tests with real components for the specific scenarios tested here (some already exist in `test_coalesce_executor_audit_gaps.py`)
2. The heavy mocking means these tests verify implementation details rather than behavior - they should be considered documentation of expected call patterns rather than strong correctness assurance
3. The overlap with `test_coalesce_executor_audit_gaps.py` (which uses real components) suggests these mock-based tests may be candidates for consolidation

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_coalesce_pipeline_row.py -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_coalesce_pipeline_row.py.audit.md`
