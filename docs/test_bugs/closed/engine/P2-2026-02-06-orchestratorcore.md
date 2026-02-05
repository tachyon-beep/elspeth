# Test Bug Report: Rewrite weak assertions in orchestrator_core

## Summary

- This test file covers core orchestrator functionality including simple pipeline execution, gate routing, multiple transforms in sequence, empty pipeline cases, and graph parameter handling. The tests correctly use production graph construction helpers. However, there is significant code duplication with plugin classes, and some tests use mocking patterns that may be overly complex.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **REWRITE**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_orchestrator_core.py.audit.md

## Test File

- **File:** `tests/engine/test_orchestrator_core.py`
- **Lines:** 694
- **Test count:** 8

## Findings

- See audit file for details


## Verdict Detail

**REWRITE** - The tests verify important functionality but suffer from excessive code duplication (~300 lines of repeated plugin definitions). Extract shared test plugins to module level. Consider simplifying the mock-heavy graph tests to verify behavioral outcomes (e.g., recorded node IDs in the database) rather than setter calls.

## Proposed Fix

- [x] Tests have specific, non-permissive assertions
- [x] Each test verifies the exact expected behavior
- [x] No "or 'error' in output" fallback patterns
- [x] Tests fail when actual behavior differs from expected

## Resolution

**Date:** 2026-02-06

**Actions taken:**

1. **Created reusable test plugins** in `tests/engine/conftest.py`:
   - `ListSource(data, name)` - configurable source that yields from a list
   - `CollectSink(name)` - sink that captures results to `.results` list

2. **Extracted test transforms** to module level in the test file:
   - `DoubleTransform`, `AddOneTransform`, `MultiplyTwoTransform`, `IdentityTransform`
   - Each defined once, reused across tests

3. **Removed duplicated inline class definitions:**
   - Eliminated 4 copies of `ListSource` (was defined in each test)
   - Eliminated 6 copies of `CollectSink` (was defined in each test)
   - Eliminated repeated schema classes (now use shared `_TestSchema`)

**Results:**

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Lines | 694 | 471 | -32% |
| Tests | 8 | 9 | +1 (was miscounted) |
| Duplicated classes | ~10 | 0 | -100% |

**Additional benefit:** The new `ListSource` and `CollectSink` in `tests/engine/conftest.py` can be reused by the other 28 test files that have the same duplication pattern.

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_orchestrator_core.py -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_orchestrator_core.py.audit.md`
