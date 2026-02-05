# Test Bug Report: Rewrite weak assertions in orchestrator_lifecycle

## Summary

- This file tests plugin lifecycle hooks (on_start, on_complete, close) in the Orchestrator. The tests verify correct call ordering and error resilience. However, there is significant overmocking - particularly of sources and sinks - which creates test fragility and may hide integration issues. The manual graph construction also bypasses production validation.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **REWRITE**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_orchestrator_lifecycle.audit.md

## Test File

- **File:** `tests/engine/test_orchestrator_lifecycle`
- **Lines:** 548
- **Test count:** 6

## Findings

- See audit file for details


## Verdict Detail

**REWRITE** - The manual graph construction violates CLAUDE.md's "Test Path Integrity" policy. These tests should:
1. Use `ExecutionGraph.from_plugin_instances()` instead of manual construction
2. Use test fixtures (like `_TestSourceBase`, `_TestSinkBase`) consistently instead of MagicMock
3. Follow the pattern in `test_source_lifecycle_hooks_called` which uses real `TrackedSource`

The lifecycle hook behavior being tested is valuable, but the test implementation creates maintenance burden and may hide production bugs.

## Proposed Fix

- [ ] Tests have specific, non-permissive assertions
- [ ] Each test verifies the exact expected behavior
- [ ] No "or 'error' in output" fallback patterns
- [ ] Tests fail when actual behavior differs from expected

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_orchestrator_lifecycle -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_orchestrator_lifecycle.audit.md`
