# Test Bug Report: Fix weak assertions in gate_executor

## Summary

- This test file provides thorough integration testing for the GateExecutor with both plugin-based and config-driven gates. Tests verify audit trail recording (routing events, node states, calls), error handling for missing edges and token managers, and fork/continue/route behaviors. However, there is significant code duplication between the plugin and config gate test classes, and the tests rely heavily on real infrastructure (LandscapeDB, LandscapeRecorder) which is appropriate for integration tests but makes them verbose.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_gate_executor.audit.md

## Test File

- **File:** `tests/engine/test_gate_executor`
- **Lines:** 1452
- **Test count:** 20

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - The tests are functionally correct and provide good coverage of gate executor behavior including audit trail integration. However, consider refactoring to reduce duplication between plugin and config gate test classes. A shared test harness or pytest fixtures could reduce the ~1000 lines of duplicate setup code to ~200 lines while maintaining the same coverage.

Recommended improvements (not blocking):
- Extract common setup into fixtures (db, recorder, run, basic nodes)
- Create parameterized tests for behaviors common to both gate types
- Move inline mock gate classes to a shared test utilities module

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_gate_executor -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_gate_executor.audit.md`
