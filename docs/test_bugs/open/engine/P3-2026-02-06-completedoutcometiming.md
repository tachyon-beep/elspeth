# Test Bug Report: Fix weak assertions in completed_outcome_timing

## Summary

- This is a well-structured regression test file documenting a known bug in COMPLETED outcome timing. The tests are designed to FAIL with current code (proving the bug exists) and PASS when the bug is fixed. The file serves dual purposes: documenting the contract violations and providing regression tests for the fix. However, there are structural issues with code duplication and the tests may give a misleading impression of test suite health.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_completed_outcome_timing.audit.md

## Test File

- **File:** `tests/engine/test_completed_outcome_timing`
- **Lines:** 407
- **Test count:** 3

## Findings

- See audit file for details


## Verdict Detail

**KEEP** with modifications needed. The tests serve a valuable purpose documenting a known bug and will become proper regression tests once the bug is fixed. However:
- Add `@pytest.mark.xfail(reason="BUG: COMPLETED recorded before sink write")` until the bug is fixed
- Extract duplicated plugin classes to module level
- Consider using production graph construction path for better test fidelity

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_completed_outcome_timing -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_completed_outcome_timing.audit.md`
