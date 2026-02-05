# Audit: tests/property/canonical/test_nan_rejection.py

## Overview
Property-based tests verifying NaN and Infinity are strictly rejected in canonical JSON - critical defense-in-depth for audit integrity.

**Lines:** 283
**Test Classes:** 4
**Test Methods:** 22

## Audit Results

### 1. Defects
**PASS** - No defects found.

Tests correctly verify:
- Python float NaN rejected
- NumPy NaN rejected
- Infinity (both +/-) rejected
- Decimal NaN/Infinity rejected
- Deeply nested non-finite values rejected

### 2. Overmocking
**PASS** - No mocking used.

Direct tests of production functions with `pytest.raises()`.

### 3. Missing Coverage
**PASS** - Comprehensive coverage.

All non-finite value sources tested:
- Python `float("nan")`, `float("-nan")`
- Python `float("inf")`, `float("-inf")`
- NumPy `np.nan`, `np.inf`, `-np.inf`
- NumPy arrays with non-finite values
- Decimal `NaN`, `sNaN`, `Infinity`, `-Infinity`

### 4. Tests That Do Nothing
**PASS** - All tests use `pytest.raises()` with pattern matching.

Example:
```python
with pytest.raises(ValueError, match="non-finite"):
    canonical_json(nan)
```

The `match="non-finite"` ensures the right exception is raised for the right reason.

### 5. Inefficiency
**MINOR** - Low example counts.

Most tests use `max_examples=20`. While this is acceptable for rejection tests (the input space is small), some tests could benefit from more examples:

- `test_mixed_valid_and_invalid_rejected`: Could use 100 examples to catch edge cases

### 6. Structural Issues
**PASS** - Well organized.

Clear class structure:
- `TestNaNRejection` - NaN-specific tests
- `TestInfinityRejection` - Infinity-specific tests
- `TestNonFiniteEdgeCases` - Edge cases
- `TestValidFloatsAccepted` - Positive control tests

The positive control tests (`TestValidFloatsAccepted`) are important - they verify finite floats work correctly.

## Error Message Analysis

All tests match on `"non-finite"` which is good for consistency. The Decimal tests match on `"non-finite Decimal"` which provides more specific error identification.

## Summary

| Criterion | Status | Notes |
|-----------|--------|-------|
| Defects | PASS | No bugs found |
| Overmocking | PASS | No mocking needed |
| Missing Coverage | PASS | Comprehensive |
| Tests That Do Nothing | PASS | All use raises + match |
| Inefficiency | MINOR | Low example counts (acceptable) |
| Structural Issues | PASS | Well organized |

**Overall:** EXCELLENT - Thorough rejection testing with positive controls. Critical for audit integrity.
