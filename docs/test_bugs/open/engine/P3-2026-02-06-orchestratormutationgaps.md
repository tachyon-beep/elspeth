# Test Bug Report: Fix weak assertions in orchestrator_mutation_gaps

## Summary

- This file contains mutation-testing targeted tests designed to kill surviving mutants in orchestrator.py. The tests are well-structured with clear documentation linking each test to specific line numbers. However, several tests have structural issues including direct access to internal orchestrator state and one test that manually builds execution graphs instead of using production paths.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_orchestrator_mutation_gaps.audit.md

## Test File

- **File:** `tests/engine/test_orchestrator_mutation_gaps`
- **Lines:** 565
- **Test count:** 17

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - The tests serve their documented purpose of killing mutation survivors. The warnings about internal state access are acceptable in context since these are specifically targeting internal implementation details that mutation testing revealed as undertested. The manual graph construction is borderline but acceptable for checkpoint-specific testing that doesn't depend on graph construction logic.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_orchestrator_mutation_gaps -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_orchestrator_mutation_gaps.audit.md`
