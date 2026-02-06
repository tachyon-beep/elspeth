# Test Audit: tests/performance/test_token_expansion_performance.py

**Audit Date:** 2026-02-05
**Auditor:** Claude Code
**Test File:** `/home/john/elspeth-rapid/tests/performance/test_token_expansion_performance.py`
**Lines:** 307

## Summary

Performance baseline tests for `copy.deepcopy()` overhead in token expansion scenarios. These tests measure the cost of maintaining audit integrity (isolated sibling tokens) when expanding rows. Related to bug fix P2-2026-01-21-expand-token-shared-row-data.

## Findings

### 1. INFO: Tests Measure Raw `deepcopy` Rather Than Production `expand_token`

**Location:** All `test_deepcopy_*` and `test_expand_token_simulation_*` methods

**Observation:** Tests directly measure `copy.deepcopy()` performance rather than the actual `expand_token` function from `tokens.py`:
```python
# Simulate expand_token loop (tokens.py:269-278)
_children = [copy.deepcopy(row) for _ in range(expansion_count)]
```

**Impact:** This is acceptable for baseline measurement but won't catch performance regressions in the actual `expand_token` implementation if it adds overhead beyond deepcopy.

**Recommendation:** Consider adding one test that uses the actual `expand_token` function to measure end-to-end performance including any additional overhead.

### 2. POSITIVE: Good Documentation and Context

**Location:** File docstring and method docstrings

**Good Practice:** Clear explanation of what's being measured and why:
```python
"""Measures the cost of copy.deepcopy() in expand_token for various row sizes
and expansion ratios. Critical for validating that audit integrity (isolation
of sibling tokens) doesn't create unacceptable performance overhead.

Related: P2-2026-01-21-expand-token-shared-row-data (the fix being measured)
"""
```

### 3. POSITIVE: Comprehensive Row Size Coverage

**Location:** Methods `_create_small_row`, `_create_medium_row`, `_create_large_row`

**Good Practice:** Tests cover realistic row sizes:
- Small: ~100 bytes (simple flat dict)
- Medium: ~5KB (nested with 100 items)
- Large: ~50KB (LLM response simulation)

### 4. LOW: Timing Assertions May Be Fragile

**Location:** Lines 99, 121, 143, 167, 190, 214

**Issue:** Fixed timing thresholds like `< 10us`, `< 200us`, `< 5ms` may fail on slow CI systems:
```python
assert us_per_copy < 10, f"Small row deepcopy: {us_per_copy:.2f}us (expected < 10us)"
```

**Mitigation:** Tests are marked with `@pytest.mark.performance` allowing selective exclusion.

### 5. LOW: `_children` Variable Assigned But Not Used

**Location:** Lines 161, 184, 207, 292

**Issue:** The expanded children are assigned to `_children` (prefixed underscore) and never used:
```python
_children = [copy.deepcopy(row) for _ in range(expansion_count)]
```

**Impact:** Minor - the underscore prefix correctly signals intentional non-use. However, the Python optimizer may not always eliminate the list creation, which is what we want to measure.

### 6. INFO: Informational Test Without Assertions

**Location:** `test_shallow_vs_deep_copy_comparison` (lines 218-252)

**Observation:** Test explicitly states "No assertion - this is informational only":
```python
# No assertion - this is informational only
```

**Impact:** This is documented and intentional - the test is for documentation purposes to show the cost of correctness. Acceptable.

### 7. POSITIVE: Memory Amplification Test

**Location:** `TestMemoryAmplification.test_memory_amplification_factor` (lines 257-307)

**Good Practice:** Tests memory impact, not just timing:
```python
# Memory should scale linearly with expansion count (within 20% tolerance)
expected_min = expansion_count * 0.8
expected_max = expansion_count * 1.2
assert expected_min <= amplification <= expected_max
```

This validates that deepcopy creates true independent copies (important for audit integrity).

### 8. INFO: Print Statements for Timing Output

**Location:** Lines 101, 123, 145, 169, 192, 216, 245-249, 297-300

**Observation:** Uses `print()` for timing output. These require `-s` flag to see.

**Recommendation:** Consider using `pytest-benchmark` for standardized performance reporting.

## Test Path Integrity

**Status:** NOT APPLICABLE

These tests measure raw Python operations (`copy.deepcopy`) rather than ELSPETH production code paths. This is appropriate for baseline performance measurement. The tests don't involve `ExecutionGraph` or DAG construction.

## Verdict

**PASS**

These are well-designed performance baseline tests that:
1. Measure the correct thing (deepcopy overhead for token expansion)
2. Cover realistic scenarios (various row sizes and expansion ratios)
3. Include memory impact testing
4. Document the purpose clearly with bug reference

The main limitation is that tests measure raw `deepcopy` rather than the actual `expand_token` function, but this is acceptable for establishing baselines. The `@pytest.mark.performance` marker allows these tests to be excluded from fast CI runs.
