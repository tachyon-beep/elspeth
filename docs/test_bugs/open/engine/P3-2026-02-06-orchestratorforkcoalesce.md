# Test Bug Report: Fix weak assertions in orchestrator_fork_coalesce

## Summary

- This file tests orchestrator fork and coalesce functionality. While it has good coverage of coalesce wiring, several tests rely heavily on mocking internal components (RowProcessor, CoalesceExecutor, SinkExecutor) which tests implementation details rather than behavior. The file contains extensive inline documentation explaining the mock cascades, which is good, but the mocking approach may hide integration bugs.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_orchestrator_fork_coalesce.audit.md

## Test File

- **File:** `tests/engine/test_orchestrator_fork_coalesce`
- **Lines:** 866
- **Test count:** 9

## Findings

- See audit file for details


## Verdict Detail

**KEEP with improvements** - The file provides necessary coverage for coalesce wiring, but several tests are too tightly coupled to implementation details. Recommend:
1. Follow through on the "Phase 5" TODO to replace mock-heavy tests with behavior tests
2. Consider if some tests can use the direct method testing approach (like lines 757, 851)
3. The extensive inline documentation about mock cascades is valuable - keep it

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_orchestrator_fork_coalesce -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_orchestrator_fork_coalesce.audit.md`
