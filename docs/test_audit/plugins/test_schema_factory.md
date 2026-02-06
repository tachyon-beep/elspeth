# Audit: tests/plugins/test_schema_factory.py

## Summary
Tests for dynamic Pydantic schema generation from config. Comprehensive coverage of schema modes, coercion, and type validation. Well-aligned with the Data Manifesto three-tier trust model.

## Findings

### 1. Strong Tests - NaN/Infinity Rejection

**Location:** Lines 350-483

**Issue:** None - positive finding.

**Quality:** `TestNonFiniteFloatRejection` is excellent. Tests verify that NaN and Infinity are rejected at source validation, which prevents downstream canonical JSON crashes. Directly addresses P2-2026-01-19 bug.

### 2. Strong Tests - Coercion Control

**Location:** Lines 246-348

**Issue:** None - positive finding.

**Quality:** `TestCoercionControl` thoroughly tests the three-tier trust model:
- Sources allow coercion (Tier 3 boundary)
- Transforms reject coercion (Tier 2 data)
- int->float widening is always allowed

### 3. Missing Test - Dynamic Schema with allow_coercion=False

**Location:** Lines 337-347

**Issue:** Test `test_dynamic_schema_with_coercion_disabled` shows dynamic schema accepts anything even with coercion disabled. This may be correct behavior, but there's no test verifying this is *intentional*.

**Severity:** Low - behavior is documented in test, but intent unclear.

### 4. Incomplete Type Coverage

**Location:** Lines 135-243

**Issue:** Type coercion tests cover:
- int -> float
- str -> int
- str -> float
- str -> bool
- any

Missing:
- list type
- dict type (nested objects)
- datetime/date types
- bytes type

**Severity:** Medium - real pipelines may use these types.

### 5. Boolean Coercion Edge Cases

**Location:** Lines 185-208

**Issue:** Test verifies "yes"/"no" coerce to bool, but doesn't test:
- Case variations: "YES", "yEs"
- Numeric strings beyond "0"/"1": "2", "-1"
- Empty string ""

**Severity:** Low - edge cases, but worth considering.

### 6. Test File Too Long

**Location:** Entire file (514 lines)

**Issue:** Large test file with multiple concerns:
- Schema creation
- Type coercion
- Mode behavior
- NaN rejection
- Plugin compliance

**Recommendation:** Consider splitting into focused test modules.

### 7. mypy Directive at File Level

**Location:** Line 8

**Issue:** `# mypy: disable-error-code="attr-defined"` disables mypy checks for the entire file. This is necessary for dynamically-created schemas but could hide real issues.

**Severity:** Low - well-documented reason in file header.

## Missing Coverage

1. **Schema inheritance** - if schemas can extend other schemas
2. **Schema composition** - nested schema definitions
3. **Field aliases** - if supported
4. **Validation error messages** - verifying errors are user-friendly
5. **Schema caching** - if create_schema_from_config caches schemas

## Structural Issues

### No Issues
Test classes are well-organized and logically grouped.

## Verdict

**Overall Quality:** Very Good

One of the better test files in the codebase. Strong alignment with Data Manifesto principles. Key strengths:
- Thorough coercion control testing
- Excellent NaN/Infinity boundary enforcement
- Good negative testing (rejection cases)

## Recommendations

1. **Add tests for list/dict/datetime types** if used in schemas
2. **Add boolean edge case tests** for unusual string inputs
3. **Consider splitting file** into schema_modes, coercion, and validation modules
4. **Add test for validation error message quality** - ensure users get helpful errors
5. Keep the NaN/Infinity tests - they're critical for audit integrity
