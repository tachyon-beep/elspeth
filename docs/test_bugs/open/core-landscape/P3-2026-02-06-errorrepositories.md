# Test Bug Report: Fix weak assertions in error_repositories

## Summary

- This file tests the `load()` methods of `ValidationErrorRepository`, `TransformErrorRepository`, and `TokenOutcomeRepository`. The tests verify field mapping from database rows to domain objects, including enum conversion for `RowOutcome`. Like `test_artifact_repository.py`, all tests use MagicMock objects for both the database and row data.

## Severity

- Severity: trivial
- Priority: P3
- Verdict: **KEEP**

## Reporter

- Name or handle: Test Audit
- Date: 2026-02-06
- Audit file: docs/test_audit/tests_core_landscape_test_error_repositories.audit.md

## Test File

- **File:** `tests/core/landscape/test_error_repositories`
- **Lines:** 262
- **Test count:** 10

## Findings

- See audit file for details


## Verdict Detail

**KEEP** - The tests serve their purpose of verifying field mapping and enum conversion, which is important for audit record integrity. However, the overmocking means these tests provide limited confidence that the repositories work correctly with real databases. Consider adding integration tests with the `landscape_db` fixture used elsewhere.

## Proposed Fix

- [ ] Weak assertions strengthened
- [ ] Redundant tests consolidated
- [ ] Test intent clearly expressed in assertions

## Tests

- Run after fix: `.venv/bin/python -m pytest tests/core/landscape/test_error_repositories -v`

## Notes

- Source audit: `docs/test_audit/tests_core_landscape_test_error_repositories.audit.md`
