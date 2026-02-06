# Test Bug Report: Rewrite weak assertions in orchestrator_audit

## Summary

- Comprehensive integration test suite for orchestrator audit trail functionality. Tests cover core audit recording, landscape export (with/without signing), config recording, and node metadata inheritance. The tests use real LandscapeDB instances and properly exercise production code paths. However, there is significant code duplication that could be reduced, and some tests manually construct ExecutionGraph instead of using production factories.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **REWRITE**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_orchestrator_audit.audit.md

## Test File

- **File:** `tests/engine/test_orchestrator_audit`
- **Lines:** 1424
- **Test count:** 12

## Findings

- See audit file for details


## Verdict Detail

**REWRITE** - The tests are valuable and should be kept, but the file needs refactoring:
1. Extract common test plugin classes (`ListSource`, `CollectSink`, `ValueSchema`) to module level or a shared test utilities module
2. Fix tests that manually construct `ExecutionGraph` to use `from_plugin_instances`
3. Consider splitting into multiple files by feature (audit_trail, export, metadata) given the 1400+ line size

The core test logic is sound; the issues are structural and maintainability-related.

## Proposed Fix

- [ ] Tests have specific, non-permissive assertions
- [ ] Each test verifies the exact expected behavior
- [ ] No "or 'error' in output" fallback patterns
- [ ] Tests fail when actual behavior differs from expected

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_orchestrator_audit -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_orchestrator_audit.audit.md`
