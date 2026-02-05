# Test Audit: tests/core/landscape/test_recorder_errors.py

**Lines:** 336
**Test count:** 11 test functions across 2 test classes
**Audit status:** PASS

## Summary

This test file covers two areas: transform error recording and export status enum coercion. The tests are well-written integration tests that exercise real database operations. The helper method for creating FK dependencies is a practical solution for testing error recording while respecting referential integrity constraints.

## Findings

### 🔵 Info

1. **Good practice: FK constraint compliance (lines 21-73)**
   The `_create_token_with_dependencies()` helper method properly sets up all required foreign key relationships before recording errors. This exercises the real FK constraints rather than bypassing them, which is critical for audit trail integrity.

2. **Good practice: Direct database verification (lines 126-138, 169-174, 201-206)**
   Tests verify stored data by querying the database directly, not just through the recorder's methods. This ensures the audit trail is actually persisted.

3. **Good practice: Hash verification (lines 157-174)**
   The `test_record_transform_error_stores_row_hash()` test verifies that the computed hash matches what's stored, which is essential for audit integrity.

4. **Good practice: Regression test documentation (lines 209-214)**
   The `TestExportStatusEnumCoercion` class explicitly documents that it's a regression test for a specific bug (P2-2026-01-19). This provides traceability and context for why these tests exist.

5. **Good practice: Type enforcement testing (lines 256-275)**
   The `test_set_export_status_rejects_non_enum()` test verifies that strings are rejected where ExportStatus enums are expected. This enforces the strict typing policy documented in CLAUDE.md.

6. **Good practice: State transition testing (lines 277-318)**
   Tests verify that export_error is properly cleared when transitioning from FAILED to COMPLETED or PENDING states. This prevents stale error messages from persisting.

7. **Good practice: No overmocking**
   All tests use `LandscapeDB.in_memory()` with real database operations. No mocking of the database layer.

### 🟡 Warning

1. **Raw SQL in helper method (lines 53-62)**
   The `_create_token_with_dependencies()` helper directly inserts into `tokens_table` using raw SQL rather than going through recorder methods. While this is necessary because the recorder doesn't expose a direct token creation method, it's worth noting this bypasses any validation the recorder might do. However, this is acceptable because the helper is only setting up test prerequisites, not testing token creation itself.

2. **Duplicate import of SchemaConfig (lines 8, 28, 37, 69)**
   `SchemaConfig.from_dict()` is called in the module-level constant definition and then the same import path is repeated inside the helper method. The helper could use the module-level `DYNAMIC_SCHEMA` constant instead of creating new `SchemaConfig` instances.

## Verdict

**KEEP** - This is a well-designed test file that covers important error recording functionality and serves as a regression test for a previously fixed bug. The tests properly exercise FK constraints, verify database state directly, and test type enforcement. The helper method pattern for FK setup is appropriate and well-documented. No changes needed.
