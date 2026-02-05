# Test Audit: test_azure_multi_query_profiling.py

**File:** `tests/plugins/llm/test_azure_multi_query_profiling.py`
**Lines:** 823
**Batch:** 123

## Summary

This test file focuses on load testing, profiling, and performance verification of the AzureMultiQueryLLMTransform. It includes tests for row atomicity under failure conditions, memory usage, timing distribution, and batch processing overhead.

## Findings

### 1. Defects

**ISSUE: Unreliable assertion in test_row_atomicity_high_failure_rate** (lines 528-609)

```python
def mock_chat_completion(**kwargs: Any) -> Mock:
    """Simulate 80% failure rate."""
    llm_call_count[0] += 1
    # Only calls ending in 0 or 5 succeed (20%)
    if llm_call_count[0] % 5 not in [0, 5]:  # <-- BUG: should be != 0
        raise RateLimitError("Rate limit exceeded")
```

The condition `llm_call_count[0] % 5 not in [0, 5]` is confusing and may not achieve 80% failure rate:
- `x % 5` produces values 0, 1, 2, 3, 4
- `not in [0, 5]` means fail on 1, 2, 3, 4 (since 5 is never produced by `% 5`)
- This is actually 80% failure rate (4 out of 5), but the logic is obfuscated

**Recommendation:** Simplify to `if llm_call_count[0] % 5 != 0:`

**ISSUE: Memory test may be flaky** (lines 224-301)

```python
# Should not leak excessive memory (conservative threshold)
# With 200 rows x 4 queries = 800 results, expect < 100MB increase
assert memory_increase_mb < 100
```

Memory assertions are inherently flaky due to:
- GC timing variations
- Python object allocation patterns
- Test isolation (previous tests may affect baseline)

**Recommendation:** Mark this test as `@pytest.mark.flaky` or increase the threshold.

### 2. Overmocking

**MODERATE:** Similar to other files, uses ChaosLLM helpers which is appropriate. However, the `response_factory` pattern with delays simulates network latency but doesn't test actual async I/O behavior.

### 3. Missing Coverage

| Gap | Severity | Description |
|-----|----------|-------------|
| No CPU profiling | LOW | Test mentions profiling but doesn't actually profile CPU usage |
| No actual concurrent thread stress | MEDIUM | Row atomicity tests use sequential mode, not parallel |
| No test for executor shutdown under load | MEDIUM | What happens when close() is called with pending work? |

### 4. Tests That Do Nothing

**CONCERN: Print statements instead of assertions** (multiple tests)

Several tests print stats but don't assert on them:

```python
# test_many_rows_parallel_execution (lines 136-141)
print("\nLoad test stats:")
print(f"  Rows processed: {row_count}")
print(f"  Queries per row: {queries_per_row}")
# ... no assertion on performance

# test_sequential_vs_parallel_performance (lines 219-222)
print("\nSequential vs Parallel comparison:")
print(f"  Sequential time: {sequential_time:.2f}s")
print(f"  Parallel time: {parallel_time:.2f}s")
# ... no assertion that parallel is faster
```

These are informational but don't fail on regressions.

**Recommendation:** Either add assertions or document these as benchmarks (not tests) and move to a separate benchmarks directory.

### 5. Inefficiency

**ISSUE: Duplicated `_make_pipeline_row` function** (lines 35-52)

Same as in test_azure_multi_query.py - should be imported from conftest.

**ISSUE: Slow tests not properly isolated** (lines 64-144, 146-222, 224-301)

Tests marked `@pytest.mark.slow` but:
- `test_many_rows_parallel_execution` processes 100 rows x 4 queries = 400 queries
- `test_memory_usage_with_large_batch` processes 200 rows

These should ideally use pytest-benchmark or be in a separate performance test suite.

**ISSUE: test_client_caching_behavior assertion logic** (lines 365-422)

```python
# Track how many times we create underlying AzureOpenAI client
azure_client_creations = mock_azure_class.call_count  # <-- Captured BEFORE processing

# ... processing ...

# Should only create ONE underlying AzureOpenAI client
final_creations = mock_azure_class.call_count
assert final_creations == azure_client_creations + 1, "Should reuse underlying Azure client"
```

This tests that ONE client is created during the test, but `azure_client_creations` is captured after the context manager enters (when the mock is set up), not at test start. This may not reflect actual client reuse if the mock was already called during setup.

### 6. Structural Issues

**GOOD:** Test classes are properly named (`TestLoadScenarios`, `TestRowAtomicity`, `TestProfilingInstrumentation`).

**GOOD:** `@pytest.mark.slow` markers are used appropriately.

**MINOR:** No fixture definitions in this file - all setup is inline. This is fine for profiling tests but inconsistent with other test files.

### 7. Test Path Integrity

**GOOD:** Tests use production `AzureMultiQueryLLMTransform` with `accept()` API.

**CONCERN:** Tests deliberately disable pooling in many cases:

```python
# Disable query-level pooling to avoid mock threading issues
config = make_config()
del config["pool_size"]
```

This is documented and intentional, but it means the parallel execution path is not well-tested under load. The "mock threading issues" should be investigated.

## Risk Assessment

| Risk | Level | Notes |
|------|-------|-------|
| False positives | MEDIUM | Memory tests may pass on actual leaks |
| False negatives | LOW | Atomicity tests are thorough |
| Test maintenance | MEDIUM | Slow tests may become flaky |
| Bug-hiding | MEDIUM | Disabling pool_size hides real concurrency issues |

## Recommendations

1. **FIX:** Simplify the 80% failure rate logic for clarity
2. **ADD:** Performance regression assertions (e.g., "parallel should be at least 2x faster")
3. **INVESTIGATE:** Why "mock threading issues" require disabling pool_size - this may indicate a real bug
4. **REFACTOR:** Move benchmark-style tests to a dedicated benchmarks directory
5. **CONSOLIDATE:** Remove duplicated `_make_pipeline_row` function
6. **ADD:** Test for executor shutdown behavior under load

## Overall Grade: B

Good atomicity and stress testing, but several tests are more like benchmarks than regression tests. The disabled pooling in many tests is a coverage gap that should be addressed.
