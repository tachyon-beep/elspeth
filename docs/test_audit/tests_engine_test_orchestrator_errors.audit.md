# Test Audit: tests/engine/test_orchestrator_errors.py

**Lines:** 797
**Test count:** 9
**Audit status:** ISSUES_FOUND

## Summary

This file tests orchestrator error handling, quarantine functionality, and validation of invalid destinations. The tests are thorough and well-documented with clear bug references (P1/P2 tickets). However, there is significant boilerplate duplication across test classes, and some tests knowingly exercise bug behavior with `xfail`-style assertions that should be marked as such.

## Findings

### 🟡 Warning

1. **Lines 340-446, 447-551: Tests document known bugs without `pytest.mark.xfail`**
   - `test_source_quarantine_records_quarantined_token_outcome` and `test_quarantine_outcome_not_recorded_if_sink_fails` document bugs P1-2026-01-31 but don't use `@pytest.mark.xfail`. If these bugs are fixed, the tests will pass; if not, they document expected current behavior. The comment on line 545-550 says "BUG: Currently this FAILS" which suggests the test is expected to fail.
   - Impact: Tests may be passing/failing unexpectedly depending on bug fix state.

2. **Lines 40-89, 143-192, 240-293, etc.: Heavy boilerplate duplication**
   - Each test defines its own `ListSource`, `CollectSink`, and schema classes. While isolation is good, 6+ near-identical `CollectSink` implementations create maintenance burden.
   - Impact: Maintainability - changes to sink protocol require updating multiple places.

3. **Lines 566-683, 685-797: Tests expect exceptions but may be testing unfixed bugs**
   - `test_invalid_quarantine_destination_at_runtime_crashes` and `test_none_quarantine_destination_at_runtime_crashes` use generic `Exception` catch and comments like "Currently BUGS: silently skips the row".
   - Impact: These tests may be documenting desired behavior vs actual behavior without clarity.

### 🔵 Info

1. **Lines 1-27: Well-structured imports and documentation**
   - Clear docstring explaining why plugins inherit from base classes. Good practice.

2. **Lines 117-216: Good validation testing**
   - `test_invalid_source_quarantine_destination_fails_at_init` properly tests fail-fast validation with `RouteValidationError`.

3. **Lines 219-324: Well-designed quarantine metrics test**
   - Clear setup with 3 rows (good, bad, good), verifies counts and sink contents.

4. **Lines 327-551: Comprehensive audit trail testing**
   - Tests verify `token_outcomes` table is populated correctly with SQL queries - appropriate for audit trail verification.

## Verdict

**KEEP** - Tests are valuable and cover critical error handling paths. Recommend:
1. Extract common `CollectSink`/source classes to reduce duplication
2. Add `@pytest.mark.xfail` decorators for tests documenting known bugs
3. Clarify which tests verify current behavior vs desired behavior
