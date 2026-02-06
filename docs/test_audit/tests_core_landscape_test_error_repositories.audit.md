# Test Audit: tests/core/landscape/test_error_repositories.py

**Lines:** 262
**Test count:** 10
**Audit status:** ISSUES_FOUND

## Summary

This file tests the `load()` methods of `ValidationErrorRepository`, `TransformErrorRepository`, and `TokenOutcomeRepository`. The tests verify field mapping from database rows to domain objects, including enum conversion for `RowOutcome`. Like `test_artifact_repository.py`, all tests use MagicMock objects for both the database and row data.

## Findings

### 🟡 Warning

1. **Overmocking (throughout file)**: Every test uses `MagicMock` for both the repository's database connection and the row data being loaded. This means:
   - No actual database interaction is tested
   - No verification that repositories can handle real SQLAlchemy row objects
   - The tests only verify Python object attribute copying, not repository functionality

2. **No query method tests**: These repositories presumably have `find_*` methods for querying errors by run_id, token_id, etc. Only `load()` is tested.

3. **No persistence tests**: There are no tests for recording/saving error records through these repositories.

### 🔵 Info

1. **Good enum conversion test (lines 239-262)**: `test_load_token_outcome_all_outcome_types` iterates through all `RowOutcome` enum values, ensuring the string-to-enum conversion works for every case. This is thorough.

2. **Edge case coverage is good**: Tests cover NULL optionals (`node_id`, `row_data_json`, `error_details_json`), non-terminal outcomes (`BUFFERED`), and various outcome types (`COMPLETED`, `FORKED`, `FAILED`).

3. **Clear test naming**: Test names clearly describe what's being verified.

4. **Correct domain object types asserted (lines 44, 97, 154)**: Tests verify that `load()` returns the correct dataclass type (`ValidationErrorRecord`, `TransformErrorRecord`, `TokenOutcome`).

## Verdict

**KEEP** - The tests serve their purpose of verifying field mapping and enum conversion, which is important for audit record integrity. However, the overmocking means these tests provide limited confidence that the repositories work correctly with real databases. Consider adding integration tests with the `landscape_db` fixture used elsewhere.
