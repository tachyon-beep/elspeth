# Test Audit: tests/integration/test_rate_limit_integration.py

**Batch:** 103
**File:** `/home/john/elspeth-rapid/tests/integration/test_rate_limit_integration.py`
**Lines:** 409
**Audit Date:** 2026-02-05

## Summary

This file tests the rate limit registry wiring through the CLI -> Orchestrator -> PluginContext pipeline. Tests verify that rate limiters are properly passed to plugins and actually throttle requests.

## Test Classes Found

1. `RateLimitAwareTransform` - Test helper transform that uses rate limiting
2. `TestRateLimitRegistryInOrchestrator` - Tests for Orchestrator accepting rate limit registry
3. `TestRateLimitRegistryInContext` - Tests for PluginContext rate limit field
4. `TestRateLimitThrottling` - Tests for actual throttling behavior
5. `TestRateLimitServiceConfig` - Tests for per-service rate limit configuration
6. `TestAuditedClientRateLimiting` - Tests for audited clients using rate limiters

## Issues Found

### 1. DEFECT: Flaky Timing-Based Test (HIGH)

**Location:** Lines 125-164 (`test_rate_limiter_throttles_excess_requests`)

**Problem:** The test relies on precise timing assertions:

```python
# First 10 calls should be nearly instant
first_10_delta = call_times[9] - call_times[0]
assert first_10_delta < 0.1, f"First 10 calls took {first_10_delta * 1000:.0f}ms (expected instant)"

# 11th call should have waited for a token leak
wait_for_11th = call_times[10] - call_times[9]
assert wait_for_11th >= 0.05, f"11th call should have waited, only waited {wait_for_11th * 1000:.0f}ms"
```

These timing assertions are fragile:
- CI machines under load may take >100ms for 10 calls
- The 50ms minimum wait is very tight (might fail on fast machines or with rounding)

**Impact:** Test may flake in CI or when run under load.

**Recommendation:**
1. Use more generous timing bounds (e.g., `< 1.0` for instant, `>= 0.01` for wait)
2. Or use a mock clock instead of real time
3. Or verify rate limiting behavior without precise timing (e.g., verify limiter state)

### 2. DEFECT: Test Comment Describes Wrong Behavior (LOW)

**Location:** Lines 373-374

**Problem:** Test is named `test_audited_client_without_limiter_no_throttle` but the comment says:

```python
def test_audited_client_without_limiter_no_throttle(self) -> None:
    """AuditedLLMClient works without limiter (backward compatibility)."""
```

The test doesn't verify "no throttle" - it just verifies the client works without a limiter. The name implies timing verification that doesn't happen.

**Impact:** Misleading test name. The test is valid but the name suggests more than it tests.

### 3. MISSING COVERAGE: No Test for Rate Limit Error Propagation (MEDIUM)

**Problem:** The tests verify that `limiter.acquire()` is called, but don't test what happens when:
- `acquire()` blocks for too long (timeout)
- `acquire()` is called when rate limit is exceeded
- Multiple threads compete for tokens

The `RateLimitAwareTransform` helper just calls `acquire()` without handling errors:

```python
if ctx.rate_limit_registry is not None:
    limiter = ctx.rate_limit_registry.get_limiter(self._service_name)
    limiter.acquire()  # What if this times out?
```

### 4. STRUCTURAL: Test Modifies Method at Runtime (LOW)

**Location:** Lines 255-263, 327-335

**Problem:** Tests monkey-patch `limiter.acquire` at runtime:

```python
limiter.acquire = counting_acquire  # type: ignore[method-assign]
```

While this works, it's fragile and bypasses type checking (`type: ignore`). A spy pattern (e.g., `unittest.mock.patch.object` with `wraps=`) would be cleaner.

**Recommendation:** Use `patch.object(limiter, 'acquire', wraps=limiter.acquire)` to count calls while preserving original behavior.

### 5. OBSERVATION: Good Coverage of Wiring (Positive)

**Location:** Lines 64-90

**Positive:** The tests thoroughly verify that rate limit registry is properly wired:
- Orchestrator constructor accepts registry
- Orchestrator stores registry correctly
- Registry can be None (optional)
- Context exposes registry to plugins

This is valuable integration testing of the dependency injection chain.

### 6. OBSERVATION: Good Use of Real Components (Positive)

**Location:** Throughout

**Positive:** Tests use real `RateLimitRegistry`, `RuntimeRateLimitConfig`, and `Orchestrator`. Only the underlying HTTP/LLM calls are mocked, not the rate limiting logic itself.

### 7. MISSING COVERAGE: No Test for Registry Cleanup (LOW)

**Problem:** Tests call `registry.close()` in finally blocks, but there's no test verifying that:
- Close actually releases resources
- Using a closed registry fails appropriately
- Double-close doesn't error

### 8. STRUCTURAL: `RateLimitAwareTransform` Should Be in Fixtures (LOW)

**Location:** Lines 37-61

**Problem:** The `RateLimitAwareTransform` test helper class is defined at module level. For test isolation, it would be better as a fixture or in conftest.py.

This is minor since it's a test-only class with no side effects.

## Test Coverage Analysis

### Well-Covered Scenarios:
- Orchestrator rate limit registry wiring
- PluginContext rate limit field
- Rate limiter throttles excess requests
- Disabled rate limiting (no throttle)
- Per-service rate limit configuration
- AuditedLLMClient rate limit integration
- AuditedHTTPClient rate limit integration
- Client without limiter (backward compatibility)

### Missing Coverage:
1. **Rate limit timeout** - No test for acquire timeout
2. **Concurrent acquire** - No test for thread contention
3. **Registry cleanup** - No test for close behavior
4. **Error propagation** - No test for limiter errors
5. **Token refill** - No test verifying tokens refill over time
6. **Burst handling** - No test for burst configurations

## Test Path Integrity

**Status:** GOOD COMPLIANCE

Tests use:
- Real `Orchestrator` (lines 76, 87)
- Real `RateLimitRegistry` (throughout)
- Real `PluginContext` (lines 103-108, 114-119)
- Real `AuditedLLMClient` and `AuditedHTTPClient` (lines 279-287, 342-349)

The only mocking is for underlying HTTP/LLM clients, which is appropriate since these tests focus on rate limiting behavior, not actual API calls.

## Recommendations

1. **HIGH:** Fix flaky timing test by using more generous bounds or mock clock
2. **MEDIUM:** Add tests for rate limit timeout/error scenarios
3. **LOW:** Rename `test_audited_client_without_limiter_no_throttle` to match actual behavior
4. **LOW:** Consider using `patch.object` with `wraps=` instead of direct method assignment
5. **LOW:** Add test for registry cleanup behavior

## Final Assessment

**Quality Score:** 7.5/10

The tests provide good coverage of the rate limit wiring through the system. The use of real components (Orchestrator, Registry, Context) makes these genuine integration tests. The main issues are the flaky timing-based test and missing coverage for error scenarios. The tests successfully verify the fix for P2-2026-02-01 (rate limit registry not consumed) by asserting `limiter.acquire()` is called.
