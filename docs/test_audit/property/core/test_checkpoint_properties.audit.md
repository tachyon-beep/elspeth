# Audit: tests/property/core/test_checkpoint_properties.py

## Overview
Property-based tests for checkpoint recovery system - verifying aggregation state round-trips, format version validation, and topology hash detection.

**Lines:** 740
**Test Classes:** 6
**Test Methods:** 18

## Audit Results

### 1. Defects
**PASS** - No defects found.

Tests correctly verify:
- Aggregation state survives JSON round-trip
- NaN/Infinity rejected in aggregation state
- Format version incompatibility detected
- Topology changes detected (including sibling branches - BUG-COMPAT-01 fix)
- Sequence number ordering

### 2. Overmocking
**PASS** - Minimal mocking.

Uses actual:
- `CheckpointManager`
- `CheckpointCompatibilityValidator`
- `LandscapeDB` (SQLite file-based, not in-memory)
- Real SQL tables via `setup_checkpoint_prerequisites()`

### 3. Missing Coverage
**MINOR** - Some gaps:

1. **Partial topology changes**: Tests full graph changes, not incremental
2. **Checkpoint pruning**: No tests for deleting old checkpoints
3. **Concurrent checkpoint creation**: No thread-safety tests
4. **Large aggregation states**: Tests use `max_size=5`, production may have larger

### 4. Tests That Do Nothing
**PASS** - All tests have meaningful assertions.

Strong checkpoint validation:
```python
result = validator.validate(checkpoint, graph_modified)
assert result.can_resume is False
assert result.reason is not None and "no longer exists" in result.reason
```

### 5. Inefficiency
**MEDIUM** - Resource management concerns.

Lines 96-100 create temp DB files that may not be cleaned up:
```python
def create_test_db() -> tuple[LandscapeDB, Path]:
    tmp_dir = tempfile.mkdtemp()  # Not cleaned up
    db_path = Path(tmp_dir) / "test_audit.db"
    db = LandscapeDB(f"sqlite:///{db_path}")
    return db, db_path
```

Tests do call `db.close()` in finally blocks, but temp directories are not removed.

**Recommendation:** Use pytest's `tmp_path` fixture or clean up in finally blocks.

### 6. Structural Issues
**MINOR** - Long setup helper.

`setup_checkpoint_prerequisites()` (lines 103-183) is 80 lines. Could be split:
- `create_run()`
- `create_source_and_transform_nodes()`
- `create_row_and_token()`

## Topology Hash Testing (Critical)

The test `test_sibling_branch_change_detected` (lines 451-481) explicitly tests the fix for BUG-COMPAT-01:
```python
def test_sibling_branch_change_detected(self) -> None:
    """Property: Changes to sibling branches (not upstream) are detected.

    BUG-COMPAT-01: Previously only upstream changes were detected,
    allowing sibling sink branches to change silently.
    """
```

This is excellent - the test documents the bug it prevents.

## Format Version Testing

Tests both rejection of old AND new versions:
```python
# Skip current version (it's valid)
assume(version != Checkpoint.CURRENT_FORMAT_VERSION)
```

This ensures cross-version resume is forbidden in both directions.

## Summary

| Criterion | Status | Notes |
|-----------|--------|-------|
| Defects | PASS | No bugs found |
| Overmocking | PASS | Uses real components |
| Missing Coverage | MINOR | Pruning, concurrency |
| Tests That Do Nothing | PASS | Strong assertions |
| Inefficiency | MEDIUM | Temp file cleanup |
| Structural Issues | MINOR | Long setup helper |

**Overall:** HIGH QUALITY - Thorough checkpoint testing with good bug documentation. Temp file cleanup should be improved.
