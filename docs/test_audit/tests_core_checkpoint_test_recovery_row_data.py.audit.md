# Test Audit: tests/core/checkpoint/test_recovery_row_data.py

**Lines:** 297
**Test count:** 3 test methods
**Audit status:** PASS

## Summary

This test file focuses on the `get_unprocessed_row_data()` method of RecoveryManager. The tests verify correct row data retrieval with actual payloads, empty results when all rows are processed, and error handling for missing/purged payloads. The tests use real database operations and a real FilesystemPayloadStore rather than mocks, providing good integration coverage.

## Findings

### 🔵 Info

1. **Lines 24-62: Core functionality test** - `test_get_unprocessed_row_data_returns_row_dicts` validates the return structure (list of tuples), correct row indices, string row_ids, and proper row data content. Good comprehensive assertions.

2. **Lines 64-171: Empty result test** - `test_get_unprocessed_row_data_empty_when_all_processed` creates a complete scenario with token outcomes to verify that fully processed runs return empty lists.

3. **Lines 173-297: Missing payload test** - `test_get_unprocessed_row_data_raises_on_missing_payload` validates the error path when payloads have been purged.

4. **Lines 33-36, 165-168, 291-294: Schema requirement** - Tests correctly use `_create_dynamic_schema` to satisfy the required schema parameter (Bug #4 fix).

5. **Lines 137-149, 244-256: Token outcomes usage** - Tests correctly create terminal token outcomes, reflecting the P1-2026-01-22 fix where get_unprocessed_rows uses token_outcomes rather than row_index.

### 🟡 Warning

1. **Lines 154-156, 280-282: External fixture dependency** - Tests import `_create_test_graph` from `conftest.py`. This is fine but means understanding these tests requires reading the conftest.

2. **Missing fixtures in file** - The test class uses fixtures (`recovery_manager`, `payload_store`, `db`, `checkpoint_manager`, `run_with_checkpoint_and_payloads`) that are not defined in this file. They must be in conftest.py. This is normal pytest practice but worth noting.

## Verdict

**KEEP** - This is a well-designed integration test file for row data recovery. The tests use real database and filesystem operations, verify correct data structures, and cover important error paths. The three tests are comprehensive and complementary.
