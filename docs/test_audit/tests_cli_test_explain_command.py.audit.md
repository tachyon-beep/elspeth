# Test Audit: tests/cli/test_explain_command.py

**Lines:** 294
**Test count:** 14
**Audit status:** PASS

## Summary

This test file provides comprehensive coverage of the `elspeth explain` CLI command across JSON mode and text mode. Tests use real database instances through fixtures, verify round-trip consistency with the backend API, and cover both success and error paths including edge cases like ambiguous row lookups and empty databases. The test structure is clean and well-documented.

## Findings

### 🔵 Info (minor suggestions or observations)
- **Lines 43-75, 242-274:** The `db_with_run` fixture is duplicated in both `TestExplainJsonMode` and `TestExplainTextMode` classes. Consider moving this to a module-level fixture or conftest.py to reduce code duplication.
- **Lines 77-119:** The `db_with_forked_row` fixture is well-designed for testing the ambiguous row case.
- **Lines 185-202:** `test_json_output_matches_backend_explain` is an excellent round-trip test that verifies CLI output matches the backend `explain()` function directly. This catches serialization bugs and ensures the CLI is a faithful representation of the underlying API.
- **Lines 181-183:** The assertion `assert "terminal tokens" in error_lower or "sink" in error_lower or "multiple" in error_lower` in `test_json_output_ambiguous_row_without_sink` is somewhat permissive but acceptable for error message testing where the exact wording may evolve. The alternatives are all semantically related to the expected error condition.

## Verdict
**KEEP** - This is a well-written test file with strong coverage of the explain command. The tests use real database instances, verify actual command output, and include an excellent round-trip consistency test. The minor duplication of the `db_with_run` fixture is a small code smell but doesn't affect test quality. No critical issues found.
