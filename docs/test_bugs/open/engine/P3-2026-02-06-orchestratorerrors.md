# Test Bug Report: Fix weak assertions in orchestrator_errors

## Summary

- This file tests orchestrator error handling, quarantine functionality, and validation of invalid destinations. The tests are thorough and well-documented with clear bug references (P1/P2 tickets). However, there is significant boilerplate duplication across test classes, and some tests knowingly exercise bug behavior with `xfail`-style assertions that should be marked as such.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_orchestrator_errors.audit.md

## Test File

- **File:** `tests/engine/test_orchestrator_errors`
- **Lines:** 797
- **Test count:** 9

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - Tests are valuable and cover critical error handling paths. Recommend:
1. Extract common `CollectSink`/source classes to reduce duplication
2. Add `@pytest.mark.xfail` decorators for tests documenting known bugs
3. Clarify which tests verify current behavior vs desired behavior

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_orchestrator_errors -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_orchestrator_errors.audit.md`
