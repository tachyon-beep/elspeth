# Test Audit: test_executor_retryable_errors.py

**File:** `tests/plugins/pooling/test_executor_retryable_errors.py`
**Lines:** 369
**Audited:** 2026-02-05

## Summary

Integration tests for PooledExecutor retry behavior with various error types. Comprehensive coverage of retryable vs non-retryable errors, timeout behavior, and dispatch gate timing after retries.

## Findings

### 1. Good Practices Observed

- **Exhaustive error type coverage** - Tests all LLMClientError subtypes (NetworkError, ServerError, RateLimitError, ContentPolicyError, ContextLengthError)
- **Retry count verification** - Tests verify exact call counts to ensure retry behavior
- **Timeout verification** - Tests verify errors return after max_capacity_retry_seconds
- **Regression test for dispatch gate** - `TestDispatchGateAfterRetry` class addresses specific bug

### 2. Potential Issues

#### 2.1 Time-Based Test May Be Flaky (Potential Defect - Medium)

**Location:** Lines 193-195

```python
# Should timeout around 1 second (max_capacity_retry_seconds)
# Allow some variance for system load
assert 0.9 <= elapsed <= 2.0
```

The tolerance (0.9 to 2.0 seconds for 1-second timeout) is reasonable but could still fail under heavy CI load. The lower bound is particularly risky.

**Recommendation:** Either remove the lower bound or use a more generous margin.

#### 2.2 Timing Test with Small Margins (Potential Defect - Medium)

**Location:** Lines 364-369

```python
# Allow 10% tolerance for timing jitter
assert gap >= min_delay_s * 0.9, (
    f"Dispatch gap {i - 1}->{i} was {gap * 1000:.1f}ms, "
    f"expected >= {config.min_dispatch_delay_ms}ms. "
```

10% tolerance on a 50ms delay (45ms effective minimum) is tight. Sleep timing on busy systems can vary more than this.

**Recommendation:** Increase tolerance to 20% or use a longer base delay.

#### 2.3 Mutable State in Closures (Minor Code Smell)

**Location:** Lines 42-43, 67-68, 89-90, etc.

```python
call_count = [0]  # Using list to allow mutation in closure

def process_fn(...):
    call_count[0] += 1
```

While this pattern works, it's a workaround for Python's closure semantics. Using `nonlocal` in Python 3 or a class attribute would be cleaner.

**Recommendation:** Consider using a simple counter class or `nonlocal` keyword.

### 3. Missing Coverage

| Path Not Tested | Risk |
|-----------------|------|
| Multiple concurrent batches | Low - _batch_lock prevents this |
| Shutdown during retry | Medium - could leave threads hanging |
| Exception other than LLMClientError | Low - documented to crash |
| CapacityError with different status codes | Low - 503, 504, 529, etc. |

#### 3.1 No Test for Unknown Exception Types

**Location:** Entire file

Per CLAUDE.md, unexpected exceptions in `process_fn` should crash (not be caught). This is not explicitly tested.

```python
def test_unknown_exception_crashes_executor():
    def process_fn(...):
        raise RuntimeError("Unexpected")  # Should propagate, not be caught
```

**Recommendation:** Add test verifying non-LLMClientError exceptions propagate.

### 4. Tests That Do Nothing

None - all tests have meaningful assertions with specific conditions.

### 5. Test Quality Score

| Criterion | Score |
|-----------|-------|
| Defects | 1 (timing flakiness) |
| Overmocking | 0 |
| Missing Coverage | 1 (crash on unknown exception) |
| Tests That Do Nothing | 0 |
| Inefficiency | 0 |
| Structural Issues | 0 |

**Overall: PASS** - Excellent integration tests with good regression test documentation. Minor timing flakiness concerns.

## Specific Test Reviews

### TestRetryableErrorHandling

Comprehensive coverage of all error types:
- `NetworkError` - retryable, succeeds on 3rd attempt
- `ServerError` - retryable (503)
- `RateLimitError` - retryable
- `ContentPolicyError` - NOT retryable, fails immediately
- `ContextLengthError` - NOT retryable, fails immediately
- `LLMClientError(retryable=False)` - 401 unauthorized, fails immediately

Each test verifies both the result status and the exact call count, ensuring retry behavior matches specification.

### TestDispatchGateAfterRetry

**Location:** Lines 309-369

This is an excellent regression test:
- Documents the bug in the docstring (workers bypassing dispatch gate after retry)
- Uses small timing values (50ms delay) to make violations detectable
- Records dispatch times and verifies ALL consecutive dispatches respect timing
- Error message explains what a failure means

```python
f"This indicates the retry bypassed the dispatch gate."
```

**Rating:** Exemplary regression test pattern

## Test Architecture Note

The tests use a real `PooledExecutor` with mocked `process_fn`, which exercises the actual threading and retry logic. This is the correct approach for integration testing - the concurrency behavior cannot be properly tested with mocks.
