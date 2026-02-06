# Test Audit: test_azure_multi_query_retry.py

**File:** `tests/plugins/llm/test_azure_multi_query_retry.py`
**Lines:** 874
**Batch:** 123

## Summary

This test file focuses on retry behavior for the AzureMultiQueryLLMTransform, including capacity error handling with AIMD backoff, concurrent row processing, sequential fallback, memory leak prevention, and error classification (retryable vs non-retryable).

## Findings

### 1. Defects

**POTENTIAL ISSUE: test_sequential_mode_no_retry assertion mismatch** (lines 524-594)

```python
def first_call_fails(count: int) -> OpenAIRateLimitError | None:
    if count == 1:
        return OpenAIRateLimitError(...)
    return None

# ...

# All 4 queries attempted (no retry, but all queries run once)
assert call_count[0] == 4
```

The comment says "no retry" but the function only fails the FIRST call (count == 1). If queries run in any order other than strict sequential, or if there's any retry mechanism at all, this could pass incorrectly.

**ISSUE: Incomplete failure verification** (lines 589-593)

```python
failed_queries = result.reason["failed_queries"]
assert isinstance(failed_queries, list)
first_failure = failed_queries[0]
assert isinstance(first_failure, dict)  # QueryFailureDetail
assert "Rate limit" in first_failure["error"]
```

This assumes `failed_queries[0]` exists without checking `len(failed_queries) > 0`, which could cause IndexError if the list is empty.

### 2. Overmocking

**APPROPRIATE:** The retry tests mock at the OpenAI SDK level to simulate specific error types (RateLimitError, APITimeoutError, BadRequestError). This is the correct level for testing retry classification.

**CONCERN:** The `mock_azure_openai_with_counter` helper (lines 61-90) catches exceptions from `failure_condition` and re-raises them, which is correct, but the response factory doesn't track which specific queries failed, making it hard to verify retry ordering.

### 3. Missing Coverage

| Gap | Severity | Description |
|-----|----------|-------------|
| No test for retry with jitter | MEDIUM | AIMD backoff may include jitter, not tested |
| No test for max retry attempts | MEDIUM | Tests timeout but not attempt limits |
| No test for retry-after header | MEDIUM | Azure returns Retry-After header, not tested |
| No test for partial batch retry | LOW | What if some queries need retry, others don't? |
| No test for error categorization edge cases | LOW | e.g., 500 vs 502 vs 503 handling |

### 4. Tests That Do Nothing

**CONCERN: Weak assertion in test_query_level_pool_utilization** (lines 431-506)

```python
# Max concurrent should be close to pool_size (4) or at least > 1
# This verifies query-level parallelism is working
assert max_concurrent[0] >= 2, f"Expected parallel query execution, got max {max_concurrent[0]} concurrent"
```

With pool_size=4, expecting only >= 2 concurrency is a weak assertion. The comment says "close to pool_size" but the assertion allows 50% utilization. This could pass even if pooling is partially broken.

**Recommendation:** Assert `max_concurrent[0] >= 3` or add a separate assertion for average concurrency.

### 5. Inefficiency

**ISSUE: Duplicated `_make_pipeline_row` function** (lines 33-50)

Same duplication as in other files - should be imported from conftest.

**ISSUE: Duplicated `make_config` wrapper** (lines 53-58)

```python
def make_config(**overrides: Any) -> dict[str, Any]:
    """Create retry-specific config with extra timeout field."""
    defaults = {"max_capacity_retry_seconds": 10}
    defaults.update(overrides)
    return make_azure_multi_query_config(**defaults)
```

This wrapper exists to set a default for `max_capacity_retry_seconds`, but this could be added to the conftest version.

**ISSUE: Repeated fixture definitions** (lines 96-106, 284-294, 509-519, 596-609, 743-752)

Same `mock_recorder` and `collector` fixtures repeated in 5 test classes. Should be consolidated.

### 6. Structural Issues

**GOOD:** Test classes are well-named and logically organized:
- `TestRetryBehavior` - AIMD retry logic
- `TestConcurrentRowProcessing` - multi-row handling
- `TestSequentialFallback` - no-executor mode
- `TestMemoryLeakPrevention` - client cleanup
- `TestLLMErrorRetry` - error classification

**GOOD:** Tests are focused on specific behaviors with clear naming.

**MINOR:** The test file imports `ExceptionResult` (line 19) but only uses it in one test. This import should be in the specific test or class that needs it.

### 7. Test Path Integrity

**GOOD:** Tests use the actual transform's `accept()` API and `flush_batch_processing()` lifecycle.

**CONCERN:** Many tests disable pool_size:

```python
# Sequential query execution - focus on row pipelining
config = make_config()
del config["pool_size"]
```

This is done intentionally for isolation, but similar to the profiling tests, it means the pooled retry path isn't well-exercised.

**GOOD:** `test_query_level_pool_utilization` (lines 431-506) does test with `pool_size=4` and verifies concurrent execution.

## Risk Assessment

| Risk | Level | Notes |
|------|-------|-------|
| False positives | LOW | Error conditions are well-simulated |
| False negatives | MEDIUM | Weak concurrency assertions |
| Test maintenance | MEDIUM | Fixture duplication |
| Bug-hiding | LOW | Tests cover important retry scenarios |

## Recommendations

1. **FIX:** Add bounds check before accessing `failed_queries[0]`
2. **STRENGTHEN:** Increase minimum concurrency assertion from >= 2 to >= 3 for pool_size=4
3. **ADD:** Test for Retry-After header handling
4. **ADD:** Test for max retry attempts (not just timeout)
5. **CONSOLIDATE:** Move repeated fixtures to module level or conftest
6. **CONSOLIDATE:** Remove duplicated `_make_pipeline_row` function
7. **CONSIDER:** Moving the `make_config` wrapper to conftest with optional `max_capacity_retry_seconds`

## Overall Grade: B+

Good coverage of retry behavior and error classification. The tests effectively verify the AIMD backoff implementation and memory leak prevention. Main issues are fixture duplication and some weak assertions that should be strengthened.
