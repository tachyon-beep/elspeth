# Test Audit: test_database_sink.py

**File:** `tests/plugins/sinks/test_database_sink.py`
**Lines:** 724
**Audit Date:** 2026-02-05
**Auditor:** Claude Opus 4.5

## Summary

Comprehensive tests for DatabaseSink plugin covering writes, batch operations, schema validation, secret handling, canonical hashing, and `if_exists` behavior. Well-organized with focused test classes.

## Findings

### 1. Defects

**SEVERITY: LOW**
- **Line 53:** Test checks `rows[0][1] == "alice"` using positional index. This is fragile - if column order changes, test breaks. Should use column names or dict access.
- **Line 93:** `test_memory_database` writes data but can't verify it (as noted in comment). Test only verifies no exception, which is weak.

### 2. Overmocking

None identified. Tests use real SQLite databases with actual SQL operations.

### 3. Missing Coverage

**SEVERITY: MEDIUM**
- No test for database connection failures (network timeout, authentication failure)
- No test for transaction rollback on partial batch failure
- Missing test for SQL injection protection (if rows contain malicious values)
- No test for database constraints (unique, foreign key) violations

**SEVERITY: LOW**
- No test for very large batches (memory pressure)
- Missing test for concurrent writes from multiple sink instances
- No test for connection pooling behavior
- No tests for PostgreSQL or other database backends (only SQLite)

### 4. Tests That Do Nothing

**SEVERITY: LOW**
- **Line 93:** `test_memory_database` - As noted in its own comment, it "can't verify in-memory after close, but should not raise". This provides minimal value.

### 5. Inefficiency

**SEVERITY: LOW**
- `_get_row_count()` helper in `TestDatabaseSinkIfExistsReplace` creates and disposes engine on each call. Could reuse connection.
- Multiple test classes have identical `ctx` and `db_url` fixtures. Consider consolidating.

### 6. Structural Issues

**SEVERITY: LOW**
- `TestDatabaseSinkSchemaValidation` exists here but there's also `TestDatabaseSinkSpecific` in `test_sink_schema_validation_common.py`. Some consolidation might help.
- `TestDatabaseSinkCanonicalHashing` tests overlap somewhat with canonical module tests. Consider if this duplication is necessary for integration testing.

## Positive Observations

1. Excellent coverage of canonical JSON hashing including edge cases (NaN, Infinity, numpy types)
2. Comprehensive `if_exists` behavior testing with clear bug reference (P2-2026-01-19)
3. Secret handling tests properly verify both dev mode and production mode behavior
4. Type mapping tests verify SQLAlchemy types are correctly inferred
5. Good use of SQLAlchemy introspection to verify schema

## Recommendations

1. Add tests for database error scenarios (connection failure, constraint violations)
2. Replace positional column access with named access
3. Consider removing or enhancing `test_memory_database` to provide actual value
4. Add tests for other database backends if they're supported
5. Consider transaction atomicity tests
