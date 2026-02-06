# Test Bug Report: Rewrite weak assertions in orchestrator_recovery

## Summary

- This file contains tests for orchestrator crash recovery via the resume() method. The file has extensive fixture setup (200+ lines) for a single test. The test itself verifies batch retry behavior after simulated crash, but the fixture-heavy approach and manual graph construction patterns raise concerns.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **REWRITE**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_orchestrator_recovery.audit.md

## Test File

- **File:** `tests/engine/test_orchestrator_recovery`
- **Lines:** 324
- **Test count:** 1

## Findings

- See audit file for details


## Verdict Detail

**REWRITE** - The critical issue is manual graph construction bypassing production paths. The single test provides inadequate coverage for crash recovery, which is a critical feature. The 130-line fixture makes the test hard to understand and maintain. Recommended:
1. Use `ExecutionGraph.from_plugin_instances()` or proper test helpers
2. Split the fixture into smaller, focused fixtures
3. Add tests for recovery edge cases
4. Strengthen the final status assertion to verify recovery success

## Proposed Fix

- [ ] Tests have specific, non-permissive assertions
- [ ] Each test verifies the exact expected behavior
- [ ] No "or 'error' in output" fallback patterns
- [ ] Tests fail when actual behavior differs from expected

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_orchestrator_recovery -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_orchestrator_recovery.audit.md`
