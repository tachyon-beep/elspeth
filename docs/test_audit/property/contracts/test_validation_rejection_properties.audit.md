# Audit: tests/property/contracts/test_validation_rejection_properties.py

## Overview
Property-based tests for CONTRACT boundary validation rejection - Decimal, enum, and config rejection at trust boundaries.

**Lines:** 227
**Test Classes:** 3
**Test Methods:** 12

## Audit Results

### 1. Defects
**PASS** - No defects found.

Tests correctly verify:
- Non-finite Decimal values rejected (NaN, sNaN, Infinity)
- Invalid enum values rejected (RowOutcome, RoutingKind, RunStatus, NodeStateStatus)
- Invalid config values rejected (max_attempts < 1, count <= 0, timeout <= 0)

### 2. Overmocking
**PASS** - No mocking used.

Direct tests of validation behavior with `pytest.raises()`.

### 3. Missing Coverage
**MINOR** - Focused scope by design.

The file explicitly states it complements `test_nan_rejection.py` for float/numpy coverage. However:

1. **Pydantic config validation**: Only tests TriggerConfig, not other settings classes
2. **RuntimeRetryConfig**: Tests max_attempts but not other fields
3. **Edge values**: Tests negative values but not boundary values (e.g., max_attempts=1 is valid)

### 4. Tests That Do Nothing
**PASS** - All tests use `pytest.raises()` appropriately.

Good pattern:
```python
with pytest.raises(ValueError, match="max_attempts"):
    RuntimeRetryConfig(max_attempts=max_attempts, ...)
```

The `match` parameter ensures the right validation is triggered.

### 5. Inefficiency
**PASS** - Appropriate example counts.

Uses `max_examples=20-50` for rejection tests, which is appropriate given the small input space for invalid values.

### 6. Structural Issues
**PASS** - Well organized.

Clear documentation explaining relationship to other test files:
```python
"""Property-based tests for CONTRACT boundary validation rejection.
...
NOTE: Float and NumPy non-finite rejection is comprehensively tested in:
    tests/property/canonical/test_nan_rejection.py
"""
```

## Enum Validation Analysis

The enum tests use a filter pattern to generate invalid values:
```python
@given(
    invalid_value=st.text(min_size=1, max_size=20).filter(
        lambda s: s not in ("completed", "routed", ...)
    )
)
```

This is correct - it generates strings that are NOT valid enum values.

## Summary

| Criterion | Status | Notes |
|-----------|--------|-------|
| Defects | PASS | No bugs found |
| Overmocking | PASS | No mocking needed |
| Missing Coverage | MINOR | Limited config validation scope |
| Tests That Do Nothing | PASS | All use raises + match |
| Inefficiency | PASS | Appropriate example counts |
| Structural Issues | PASS | Good documentation |

**Overall:** HIGH QUALITY - Focused validation rejection testing with clear scope documentation.
