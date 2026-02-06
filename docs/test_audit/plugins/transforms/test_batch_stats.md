# Audit: test_batch_stats.py

**File:** `tests/plugins/transforms/test_batch_stats.py`
**Lines:** 165
**Auditor:** Claude
**Date:** 2025-02-05

## Summary

Test file for BatchStats aggregation transform. References a known bug (P1-2026-01-19) in the file docstring about output schema mismatch. Tests are generally well-structured.

## Findings

### 1. POTENTIAL ISSUE - Output Schema Test May Fail

**Location:** Lines 139-165, `test_output_schema_is_observed`

**Issue:** The test expects `len(output_fields) == 0` and `config.get("extra") == "allow"`. The docstring notes this "Currently fails because output_schema = input_schema".

**Question:** Is this test expected to fail currently? If the bug is known and documented (P1-2026-01-19), should this test be marked with `@pytest.mark.xfail`?

**Severity:** Medium - If test passes when bug exists, it's testing wrong behavior. If test fails, CI would be broken.

**Recommendation:** Either:
1. Mark as `@pytest.mark.xfail(reason="P1-2026-01-19 not yet fixed")`
2. Or fix the bug and update the test

### 2. GOOD - Type Enforcement

**Location:** Lines 105-128, `test_non_numeric_values_raise_type_error`

Properly verifies Tier 2 trust model - non-numeric values in numeric field raise TypeError rather than being silently skipped.

### 3. OBSERVATION - Uses Raw Dicts

**Location:** Lines 47-51, 74-77

Tests use raw dicts instead of PipelineRow. This works because BatchStats accepts dict-like objects, but differs from BatchReplicate tests.

### 4. GOOD - Empty Batch Handling

**Location:** Lines 85-103, `test_empty_batch_returns_zeros`

Tests edge case where empty batch returns count=0, sum=0, mean=None. The `batch_empty=True` marker is properly tested.

## Missing Coverage

1. **Very Large Values**: No test for numeric overflow scenarios
2. **NaN Values**: No test for how NaN values are handled (should raise TypeError per trust model)
3. **Infinity Values**: No test for positive/negative infinity
4. **Mixed Numeric Types**: No test for mixed int/float in value_field

## Structural Assessment

- **Organization:** Good separation between happy path and output schema tests
- **Bug Documentation:** Explicit P1 reference in docstring is helpful
- **Fixtures:** Simple and appropriate

## Verdict

**NEEDS ATTENTION** - Test file has unclear status on output schema bug. Either mark test as xfail or ensure bug is fixed.
