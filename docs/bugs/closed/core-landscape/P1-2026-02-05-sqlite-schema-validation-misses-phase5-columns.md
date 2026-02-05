# BUG #8: SQLite Schema Validation Misses Phase 5 Columns

**Issue ID:** elspeth-rapid-6cjx
**Priority:** P1
**Status:** CLOSED
**Date Opened:** 2026-02-05
**Date Closed:** 2026-02-05
**Component:** core-landscape (database.py)

## Summary

Schema validation in `_REQUIRED_COLUMNS` omitted the Phase 5 schema contract audit columns, allowing stale SQLite databases to pass validation checks. This could lead to runtime crashes when code attempts to access these missing columns.

## Impact

- **Severity:** High - Tier-1 audit trail integrity
- **Effect:** Stale SQLite databases without Phase 5 contract columns would pass validation
- **Risk:** Runtime crashes when accessing `schema_contract_json`, `schema_contract_hash`, `input_contract_json`, or `output_contract_json`

## Root Cause

When Phase 5 added schema contract tracking columns to the `runs` and `nodes` tables, the `_REQUIRED_COLUMNS` list in `database.py` was not updated to include these columns.

**Missing columns:**
- `runs.schema_contract_json` (line 56 in schema.py)
- `runs.schema_contract_hash` (line 57 in schema.py)
- `nodes.input_contract_json` (line 81 in schema.py)
- `nodes.output_contract_json` (line 83 in schema.py)

These columns are critical for the audit trail - they record what schema contracts were in effect for each run and what contracts each plugin instance enforced.

## Files Affected

- `src/elspeth/core/landscape/database.py` (lines 27-41)
- `src/elspeth/core/landscape/schema.py` (lines 54-58, 80-83)

## Fix

Added the four Phase 5 contract columns to `_REQUIRED_COLUMNS`:

```python
# Phase 5: Schema contract audit trail - captures contracts in effect for run
("runs", "schema_contract_json"),
("runs", "schema_contract_hash"),
# Phase 5: Plugin contract audit trail - captures input/output contracts per node
("nodes", "input_contract_json"),
("nodes", "output_contract_json"),
```

This ensures that `_validate_schema()` will detect stale SQLite databases and raise `SchemaCompatibilityError` with remediation instructions.

## Test Coverage

Added comprehensive test in `tests/core/landscape/test_database.py`:

```python
def test_missing_phase5_contract_columns_fails_validation(self, tmp_path: Path)
```

**Test strategy:**
1. Create pre-Phase5 SQLite database with runs/nodes tables missing contract columns
2. Attempt to open with `LandscapeDB()`
3. Verify `SchemaCompatibilityError` is raised
4. Verify error message mentions all four missing columns

**Test results:**
- RED: Test failed initially (schema validation didn't detect missing columns)
- GREEN: Test passed after fix (validation now catches missing columns)
- All 558 landscape tests pass

## Verification

```bash
# Run specific test
.venv/bin/python -m pytest tests/core/landscape/test_database.py::TestSchemaCompatibility::test_missing_phase5_contract_columns_fails_validation -xvs

# Run all database tests
.venv/bin/python -m pytest tests/core/landscape/test_database.py -x

# Run full landscape test suite
.venv/bin/python -m pytest tests/core/landscape/ -x
```

**Results:** All 558 tests pass

## Pattern Observed

This is the second instance of schema evolution not updating validation lists:
1. Bug #3 (database_ops ignoring rowcount) - missing validation in write operations
2. **Bug #8 (this bug)** - missing validation in schema compatibility checks

**Lesson:** When adding new schema columns, the `_REQUIRED_COLUMNS` list must be updated in lockstep to prevent stale databases from being silently accepted.

## TDD Cycle Duration

- RED (write failing test): 5 minutes
- GREEN (implement fix): 2 minutes
- Verification (run all tests): 5 minutes
- **Total:** ~12 minutes

## Related Bugs

- Part of Group 1: Tier-1 Audit Trail Integrity (10 bugs total)
- Follows same pattern as Bugs #1-4 (validation gaps in Tier-1 code)
