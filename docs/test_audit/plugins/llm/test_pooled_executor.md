# Test Audit: test_pooled_executor.py

**File:** `tests/plugins/llm/test_pooled_executor.py`
**Lines:** 848
**Batch:** 129

## Summary

Tests for PooledExecutor parallel request handling with AIMD throttling. Covers initialization, shutdown, batch execution ordering, statistics tracking, capacity error handling with retries, concurrent batch isolation, dispatch pacing, and ordering metadata preservation.

## Audit Findings

### 1. Defects

**POTENTIAL ISSUE**:

1. **Lines 517-528**: `test_no_deadlock_when_batch_exceeds_pool_with_capacity_errors` uses SIGALRM for timeout detection:
   ```python
   old_handler = signal.signal(signal.SIGALRM, timeout_handler)
   signal.alarm(10)
   ```
   This is **not portable** - SIGALRM doesn't work on Windows. While ELSPETH may be Linux-only, this could cause CI failures on non-Linux runners.

### 2. Overmocking

**PASS** - Tests use real PooledExecutor instances with mock process functions. This is appropriate for testing the executor's coordination logic.

### 3. Missing Coverage

**LOW CONCERN**:

1. **No test for executor reuse after shutdown** - What happens if execute_batch is called after shutdown()? Should raise a clear error.

2. **No test for very long-running individual requests** - What if a single request takes longer than the entire batch timeout?

3. **Lines 625-698**: `test_dispatch_pacing_is_global_not_per_worker` and `test_no_burst_traffic_on_startup` test timing constraints with 90ms and 120ms tolerances. These could be flaky on slow CI machines.

### 4. Tests That Do Nothing

**PASS** - All tests make meaningful assertions and verify concrete behaviors.

### 5. Inefficiency

**LOW CONCERN**:

1. **Heavy use of time.sleep()** - Many tests use sleep-based coordination (lines 101, 181, 244-245, 295, 443-448, 681, etc.). While necessary for concurrency testing, these add up to slow test execution.

2. **Each test creates and shuts down executor** - No executor reuse across tests in a class, which is actually correct for isolation but adds overhead.

### 6. Structural Issues

**GOOD** - Well-organized test classes:
- `TestPooledExecutorInit` - Initialization
- `TestPooledExecutorShutdown` - Shutdown behavior
- `TestRowContext` - Row context dataclass
- `TestPooledExecutorBatch` - Batch execution and ordering
- `TestPooledExecutorStats` - Statistics tracking
- `TestPooledExecutorCapacityHandling` - AIMD throttle and retry
- `TestPooledExecutorConcurrentBatches` - Isolation between batches
- `TestPooledExecutorDispatchPacing` - Dispatch timing
- `TestPooledExecutorOrderingMetadata` - P2 bug regression tests

## Specific Test Analysis

### TestPooledExecutorBatch (Lines 79-196)

**EXCELLENT**: Comprehensive batch execution tests including:
- Results returned in submission order regardless of completion order
- Per-row state_id passing verified
- Pool size limit enforced (never exceeds concurrent limit)

Lines 82-125: `test_execute_batch_returns_results_in_order` uses lock-protected call_order list and varying delays to verify FIFO ordering. Clean implementation.

### TestPooledExecutorCapacityHandling (Lines 314-543)

**EXCELLENT**: Critical tests for AIMD throttle behavior:
- `test_capacity_error_triggers_throttle_and_retries` - Verifies retry on 429
- `test_capacity_retry_respects_max_timeout` - Verifies timeout enforcement
- `test_normal_error_not_retried` - Error results vs CapacityError distinction
- `test_capacity_retry_releases_semaphore_during_backoff` - **CRITICAL** test for deadlock prevention
- `test_no_deadlock_when_batch_exceeds_pool_with_capacity_errors` - Regression test for specific deadlock scenario

Lines 404-470: The semaphore release test is particularly valuable - it uses threading events to verify that semaphores are released during backoff sleep, preventing pool deadlock.

### TestPooledExecutorOrderingMetadata (Lines 702-848)

**EXCELLENT**: Regression tests for P2-2026-01-21-pooling-ordering-metadata-dropped:
- BufferEntry objects returned with full metadata
- Sequential submit_index values
- Completion order tracking
- Valid timestamps
- Buffer wait time calculation

Lines 820-848: `test_buffer_wait_ms_tracks_reorder_delay` cleverly verifies reorder buffer behavior by making row 0 slow and row 1 fast, then checking row 1's buffer_wait_ms.

## Recommendations

1. **MEDIUM**: Replace SIGALRM-based timeout in deadlock test with threading.Timer or pytest-timeout for cross-platform compatibility.

2. **LOW**: Consider using pytest-timeout plugin to avoid signal-based timeouts entirely.

3. **LOW**: Add test for execute_batch() called after shutdown() raises appropriate error.

4. **DOCUMENTATION**: The regression test references (P2-2026-01-21, P3-2026-01-21) are excellent for traceability.

## Quality Score

**9/10** - Excellent test coverage for a complex concurrent component. Thorough regression tests with clear bug references. Well-designed tests for race conditions and ordering. Only concern is the non-portable SIGALRM usage.
