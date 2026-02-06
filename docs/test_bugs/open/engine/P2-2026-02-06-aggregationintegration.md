# Test Bug Report: Split monolithic test file aggregation_integration

## Summary

- This is a comprehensive integration test suite for aggregation timeout behavior, END_OF_SOURCE flushing, error handling, and expected output count enforcement. The tests are well-documented with explicit bug references (P1-2026-01-22, P2-2026-01-28, etc.) and exercise complex DAG execution scenarios. However, the file suffers from significant code duplication, with nearly identical boilerplate classes defined inline in each test method.

## Severity

- Severity: minor
- Priority: P2
- Verdict: **SPLIT**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_engine_test_aggregation_integration.audit.md

## Test File

- **File:** `tests/engine/test_aggregation_integration`
- **Lines:** 3228
- **Test count:** 24

## Findings

- See audit file for details


## Verdict Detail

**SPLIT** - The test coverage is valuable and thorough, but the file should be refactored:

1. Extract common test helpers (reusable Source, Sink, Transform base implementations) into a shared module or conftest fixtures
2. Consider splitting into multiple files by test class (e.g., `test_aggregation_timeout.py`, `test_aggregation_end_of_source.py`, `test_aggregation_error_handling.py`)
3. Change the module-scoped `landscape_db` fixture to function-scoped, or ensure proper cleanup
4. Clarify the status of the documented bugs - if fixed, update comments; if not fixed, tests should be marked `xfail`

The underlying test logic is sound and provides valuable coverage for a complex subsystem. The issue is maintainability due to the extreme code duplication.

## Proposed Fix

- [ ] Large test file split into focused modules
- [ ] Each module has a single responsibility
- [ ] Shared fixtures extracted to conftest.py
- [ ] All original test coverage preserved

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/engine/test_aggregation_integration -v`

## Notes

- Source audit: `docs/test_audit/tests_engine_test_aggregation_integration.audit.md`
