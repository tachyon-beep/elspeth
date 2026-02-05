# Test Audit: tests/core/landscape/test_schema_contracts_schema.py

**Lines:** 204
**Test count:** 22
**Audit status:** ISSUES_FOUND

## Summary

This test file validates schema contract columns across three Landscape tables (runs, nodes, validation_errors). The tests are thorough for column existence and type verification but contain significant structural issues including code duplication, unnecessary imports, and tests that could be consolidated. The single integration test at the end provides good value by verifying actual database creation.

## Findings

### 🟡 Warning

1. **Repeated import pattern inside test methods (lines 16, 22, 31, 37, 44, 56, 65, 73, 79, 89, 96, 103, 110, 117, 124, 131, 142, 151, 158, 167, 180)** - Every test method imports from `elspeth.core.landscape.schema` locally. While this works, it creates unnecessary overhead and could be consolidated at module level. The pattern suggests copy-paste development.

2. **Highly repetitive test structure** - Tests like `test_runs_table_has_schema_contract_json_column` and `test_runs_table_has_schema_contract_hash_column` (lines 14-26) are nearly identical except for the column name being checked. Same pattern repeats throughout all three test classes. This could be parameterized.

3. **Unused import at line 8** - `inspect` and `create_engine` are only used in the final test class but imported at module top. The `String` import is used appropriately.

4. **"Backward compatibility" docstrings are misleading (lines 29, 35, 69, 75, 122)** - Per CLAUDE.md "No Legacy Code Policy", there should be no backward compatibility. These columns are nullable because they were added to an existing schema, not for legacy support. The docstrings are technically inaccurate.

### 🔵 Info

1. **Good column type verification** - Tests like `test_schema_contract_hash_length` (lines 42-49) properly verify both the type class and length constraints, which catches schema drift.

2. **Single integration test provides end-to-end validation** - `test_create_tables_with_contract_columns` (lines 178-204) verifies all columns exist after actual database creation, which is valuable.

3. **No mocking** - Tests operate on real schema objects, which is appropriate for schema verification tests.

## Verdict

**KEEP** - The tests provide value by verifying schema contracts, but they would benefit from parameterization to reduce duplication. The misleading "backward compatibility" docstrings should be corrected. The tests are functional and catch real schema issues; the problems are structural, not functional.
