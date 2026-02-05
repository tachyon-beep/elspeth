# Audit: tests/property/audit/test_recorder_properties.py

## Overview
Property-based tests for LandscapeRecorder determinism and integrity - the heart of ELSPETH's audit trail.

**Lines:** 1080
**Test Classes:** 8
**Test Methods:** 24+

## Audit Results

### 1. Defects
**PASS** - No defects found.

Tests correctly verify:
- Run recording creates RUNNING status
- Config hash is deterministic
- Row/token ID uniqueness
- Foreign key integrity
- Outcome recording with required fields

### 2. Overmocking
**PASS** - No overmocking.

- Uses `LandscapeDB.in_memory()` for real database testing
- Uses actual `LandscapeRecorder` with no mocks
- Exercises real SQL queries via `conn.execute(text(...))`

### 3. Missing Coverage
**MINOR** - Some gaps:

1. **Concurrent recording**: No tests for thread-safety of recorder
2. **Large batch recording**: Tests use max 50 rows, production may have 10K+
3. **Unicode/special characters in config**: Only text strategies, no unicode-heavy tests
4. **Outcome update scenarios**: No tests for updating existing outcomes

### 4. Tests That Do Nothing
**PASS** - All tests have meaningful assertions.

Good assertion patterns:
- `assert retrieved is not None, "Run was not persisted to database"`
- `assert len(node_ids) == n_nodes, f"Expected {n_nodes} unique node IDs, got {len(node_ids)}. ID collision detected!"`
- FK integrity verified via LEFT JOIN checking for orphans

### 5. Inefficiency
**MEDIUM** - Significant code duplication.

The pattern of:
1. Create DB
2. Create recorder
3. Begin run
4. Register source node
5. Create row
6. Create token
7. Do test

Is repeated in almost every test. Lines 506-527, 548-571, 589-619, etc.

**Recommendation:** Create a fixture:
```python
@pytest.fixture
def recorder_with_token():
    """Return (db, recorder, run, token) ready for outcome testing."""
```

### 6. Structural Issues
**MINOR** - Parametrized test could use explicit IDs.

Lines 625-637: The parametrized test uses tuple values without IDs:
```python
@pytest.mark.parametrize(
    ("outcome", "required_field", "kwargs"),
    [
        (RowOutcome.COMPLETED, "sink_name", {}),
        ...
    ],
)
```

Would be clearer with `ids=["completed", "routed", ...]`.

## Summary

| Criterion | Status | Notes |
|-----------|--------|-------|
| Defects | PASS | No bugs found |
| Overmocking | PASS | Uses real recorder |
| Missing Coverage | MINOR | Concurrency, large batches |
| Tests That Do Nothing | PASS | All assertions meaningful |
| Inefficiency | MEDIUM | Heavy code duplication |
| Structural Issues | MINOR | Parametrized test could use IDs |

**Overall:** HIGH QUALITY - Thorough recorder testing with strong invariant checks. Refactoring to reduce duplication would improve maintainability.
