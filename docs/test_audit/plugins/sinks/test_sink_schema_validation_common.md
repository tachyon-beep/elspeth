# Test Audit: test_sink_schema_validation_common.py

**File:** `tests/plugins/sinks/test_sink_schema_validation_common.py`
**Lines:** 490
**Audit Date:** 2026-02-05
**Auditor:** Claude Opus 4.5

## Summary

Consolidated tests for sink output target schema validation across all sink types. Uses factory fixtures and pytest parametrization to test common behavior while also having sink-specific test classes.

## Findings

### 1. Defects

None identified.

### 2. Overmocking

None identified. Tests use real file/database operations.

### 3. Missing Coverage

**SEVERITY: MEDIUM**
- No test for schema validation timeout (what if file is very large?)
- Missing test for validation when file is being written by another process (race condition)
- No test for schema validation with unicode field names

**SEVERITY: LOW**
- No test for validation result `target_fields` being empty list vs None
- Missing test for validation error message formatting

### 4. Tests That Do Nothing

None identified.

### 5. Inefficiency

**SEVERITY: LOW**
- Helper functions `_create_csv_with_headers`, `_create_jsonl_with_record`, `_create_table_with_columns` could be shared fixtures or moved to conftest
- Database sink factory creates and disposes engine for each test - could pool connections

### 6. Structural Issues

**SEVERITY: LOW**
- File mixes parametrized cross-sink tests with sink-specific classes. Could be clearer with separate files or clearer section markers.
- `SinkProtocol` defined locally (line 28-33) duplicates the actual protocol - should import from contracts

**SEVERITY: MEDIUM**
- `json_only_sink_factory` fixture exists for JSONSink-specific tests, but the comment explains why CSV/Database can't use certain modes. This architecture works but requires understanding the full context.

## Positive Observations

1. Excellent use of factory fixtures for consistent sink creation
2. Good separation of common tests (parametrized) and sink-specific tests
3. Comprehensive validation result checking (valid, missing_fields, extra_fields, order_mismatch)
4. CSV order validation properly separated from database set comparison
5. JSON-specific behaviors (invalid JSON, non-object records) well tested

## Recommendations

1. Import `SinkProtocol` from contracts instead of redefining locally
2. Add documentation header explaining the test organization
3. Consider moving helper functions to conftest for reuse
4. Add tests for edge cases like unicode field names
5. Add tests for large file validation performance
