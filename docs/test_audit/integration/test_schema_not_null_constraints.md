# Test Audit: tests/integration/test_schema_not_null_constraints.py

**Auditor:** Claude
**Date:** 2026-02-05
**Batch:** 105-106

## Overview

This file contains integration tests for Bug #7 (Schema allows NULL on audit fields). Tests verify that audit-critical fields in the database schema enforce NOT NULL constraints, preventing silent data corruption.

**Lines:** 220
**Test Class:** `TestSchemaNotNullConstraints`
**Test Count:** 4

---

## Summary

| Category | Issues Found |
|----------|--------------|
| Defects | 1 (POTENTIAL) |
| Test Path Integrity Violations | 0 |
| Overmocking | 0 |
| Missing Coverage | 1 |
| Tests That Do Nothing | 0 |
| Structural Issues | 0 |
| Inefficiency | 0 |

---

## Issues

### 1. [POTENTIAL DEFECT] Error Message Assertion May Be Fragile

**Location:** Multiple tests checking error messages (lines 58-61, 92-95, 218-220)

**Problem:** The tests check error messages with loose string matching:

```python
error_msg = str(exc_info.value).lower()
assert "not null" in error_msg or "null constraint" in error_msg
assert "upstream_topology_hash" in error_msg
```

**Concern:** SQLite error messages may vary between versions or platforms. The assertion on the field name (`upstream_topology_hash`) appearing in the error message may not hold for all database backends.

**Recommendation:** Consider:
1. Adding a comment noting this is SQLite-specific behavior
2. Or relaxing the field name assertion if other backends are used in CI

---

### 2. [MINOR] Missing Coverage - Other Audit-Critical Tables

**Problem:** Tests only cover the `checkpoints_table`. Bug #7 description mentions "audit-critical fields in the database schema" (plural), suggesting other tables may also have NOT NULL requirements.

**Recommendation:** Consider adding tests for NOT NULL constraints on other audit-critical tables:
- `runs_table` (config_hash, canonical_version)
- `nodes_table` (config_hash, plugin_version)
- `node_states_table` (token_id, node_id)

---

## Strengths

### Clean Test Design

1. **Direct Schema Testing:** Tests directly insert into tables with NULL values and verify constraint violations
2. **Uses Real Database:** `LandscapeDB` creates actual SQLite database, not mocks
3. **Complete Positive Test:** `test_checkpoint_with_valid_hashes_succeeds` verifies valid inserts still work
4. **Parent Record Setup:** The positive test properly creates all parent records (run, node, row, token) to satisfy foreign keys

### Good Test Isolation

Each test creates invalid data in isolation and verifies specific constraint failures:

```python
def test_checkpoint_upstream_topology_hash_not_null(self, test_db: LandscapeDB) -> None:
    checkpoint_data = {
        # ...
        "upstream_topology_hash": None,  # <- Intentionally NULL
        # ...
    }

    with pytest.raises(IntegrityError) as exc_info, test_db.engine.begin() as conn:
        conn.execute(insert(checkpoints_table).values(**checkpoint_data))
```

### Proper Transaction Handling

Uses `engine.begin()` as context manager which handles automatic rollback on exception:

```python
with pytest.raises(IntegrityError) as exc_info, test_db.engine.begin() as conn:
    conn.execute(insert(checkpoints_table).values(**checkpoint_data))
```

---

## Verdict

**PASSES AUDIT** - This is a well-designed test file for database constraint verification. The tests are focused, use real database operations, and verify both failure and success cases. The minor issues are cosmetic or scope-related.
