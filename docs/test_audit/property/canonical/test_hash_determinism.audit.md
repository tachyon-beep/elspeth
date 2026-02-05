# Audit: tests/property/canonical/test_hash_determinism.py

## Overview
Property-based tests for canonical JSON determinism - the foundational property ensuring same input always produces same hash for audit integrity.

**Lines:** 366
**Test Classes:** 5
**Test Methods:** 18

## Audit Results

### 1. Defects
**PASS** - No defects found.

Tests correctly verify:
- `canonical_json(x) == canonical_json(x)` for all valid inputs
- `stable_hash(x) == stable_hash(x)` determinism
- Different data produces different hashes (collision resistance)
- NumPy/Pandas type normalization
- Dictionary key order independence

### 2. Overmocking
**PASS** - No mocking used.

Tests directly call production functions:
- `canonical_json()`
- `stable_hash()`

No mocking needed for pure functions.

### 3. Missing Coverage
**MINOR** - Some edge cases:

1. **Unicode normalization**: Different unicode representations of same string not tested
2. **Very large integers**: Tests use `MAX_SAFE_INT` but JS-unsafe integers not tested for rejection
3. **Empty structures**: Empty dict `{}` and empty list `[]` determinism not explicitly tested
4. **Mixed types in list**: `[1, "a", True, None]` ordering not explicitly tested

### 4. Tests That Do Nothing
**PASS** - All tests have meaningful assertions.

Strong determinism checks:
```python
assert result1 == result2, f"Non-deterministic output for input: {data!r}"
```

### 5. Inefficiency
**PASS** - Efficient test design.

- Uses 500 examples for core determinism (appropriate for critical property)
- Uses 200-300 examples for secondary properties
- Reuses `json_values` strategy from conftest efficiently

### 6. Structural Issues
**MINOR** - Test class `TestStructuralProperties` could be renamed.

The name is generic. Consider: `TestCanonicalJsonStructureProperties`

## Strategy Analysis

Uses shared strategies from `tests/property/conftest.py`:
- `json_primitives` - RFC 8785 safe primitives
- `json_values` - recursive nested structures
- `row_data` - dict with string keys

This is good reuse but the strategies exclude non-finite floats by design (tested in `test_nan_rejection.py`).

## Summary

| Criterion | Status | Notes |
|-----------|--------|-------|
| Defects | PASS | No bugs found |
| Overmocking | PASS | No mocking needed |
| Missing Coverage | MINOR | Unicode, empty structures |
| Tests That Do Nothing | PASS | Strong assertions |
| Inefficiency | PASS | Appropriate example counts |
| Structural Issues | MINOR | Generic class name |

**Overall:** EXCELLENT - Core determinism property thoroughly tested with high example counts.
