# Analysis: src/elspeth/plugins/pooling/executor.py

**Lines:** 479
**Role:** PooledExecutor manages a thread pool for concurrent transform execution (primarily LLM API calls). It handles submission with semaphore-controlled dispatch, AIMD throttle-based rate limiting, reorder buffering for strict output ordering, and capacity error retry with timeout.
**Key dependencies:** Imports `ThreadPoolExecutor`, `Semaphore`, `Lock` from threading/concurrent.futures; `TransformResult` and `TransformErrorReason` from contracts; `LLMClientError` from `plugins.clients.llm`; `PoolConfig`, `CapacityError`, `ReorderBuffer`, `AIMDThrottle` from sibling modules. Consumed by `azure_multi_query.py`, `openrouter_multi_query.py`, `prompt_shield.py`, `content_safety.py`.
**Analysis depth:** FULL

## Summary

The executor is well-structured with clear separation of concerns and careful attention to deadlock avoidance (semaphore acquired inside workers, not on the dispatch thread). However, it has three confirmed bugs (already filed) around stats accumulation, dispatch gate pacing, and the throttle's interaction with success at negative delay. I also found one additional critical issue: the `_shutdown` flag is checked without synchronization, creating a data race on multi-core systems. The concurrency model is otherwise sound, and the reorder buffer integration is correct.

## Critical Findings

### [116-125] `_shutdown` flag is read/written without any synchronization

**What:** `_shutdown` is a plain `bool` set in `shutdown()` (line 166) and read in `_execute_single()` implicitly via the infinite while loop, but critically it is never checked by `_execute_single` at all -- so workers that are already retrying in the capacity-error loop will continue retrying indefinitely after shutdown is called, bounded only by `max_capacity_retry_seconds`. While the thread pool's `shutdown(wait=True)` will eventually reclaim threads after their current task completes, any worker in an active retry-backoff-sleep cycle will not be interrupted.

**Why it matters:** If `shutdown(wait=False)` is called during a batch with active capacity retries, the executor sets `_shutdown = True` and calls `self._thread_pool.shutdown(wait=False)`, but workers sleeping in `time.sleep(retry_delay_ms / 1000)` at line 462 will continue sleeping and then attempt to re-acquire the semaphore. Since the thread pool is shut down, the behavior is undefined -- the worker may complete or may encounter an exception from the destroyed thread pool. More practically, `shutdown(wait=True)` during active retries will block for up to `max_capacity_retry_seconds` (default 3600s = 1 hour) with no way to cancel.

**Evidence:**
```python
self._shutdown = False  # line 125, no lock
...
self._shutdown = True   # line 166, no lock
```
No check of `_shutdown` exists inside the `while True` retry loop (lines 398-468). The flag is set but never consulted by workers.

### [144-148, 178] AIMD throttle stats accumulate across batches (confirmed P2 bug)

**What:** `_reset_batch_stats()` resets only `_max_concurrent` and `_dispatch_delay_at_completion_ms`, but does not call `self._throttle.reset_stats()`. The throttle's `capacity_retries`, `successes`, `peak_delay_ms`, and `total_throttle_time_ms` accumulate across batch boundaries.

**Why it matters:** `get_stats()` is called per-row by `azure_multi_query.py` (line 799) to populate `context_after_json` in the audit trail. Rows in later batches inherit cumulative stats from earlier batches, corrupting per-row audit metadata. This is a confirmed P2 bug: `P2-2026-02-05-pool-stats-persist-across-batches-corrupting`.

**Evidence:**
```python
def _reset_batch_stats(self) -> None:
    with self._stats_lock:
        self._max_concurrent = 0
        self._dispatch_delay_at_completion_ms = 0.0
        # Missing: self._throttle.reset_stats()
```

## Warnings

### [306-356] Dispatch gate uses `min_dispatch_delay_ms` instead of AIMD `current_delay_ms` (confirmed P2 bug)

**What:** `_wait_for_dispatch_gate()` enforces only `self._config.min_dispatch_delay_ms`, a static floor. The AIMD throttle's `current_delay_ms` (which increases on capacity errors) is never used for global dispatch pacing. The code comments at lines 312-317 explicitly state this is intentional, but it contradicts the design spec.

**Why it matters:** After capacity errors, individual workers back off personally via `time.sleep(retry_delay_ms / 1000)` at line 462, but other workers (including newly dispatched ones) still pass through the gate at the static minimum delay. This means the system doesn't globally slow down under pressure, leading to repeated 429/503 errors as healthy workers continue dispatching at full speed. This is confirmed P2 bug: `P2-2026-02-05-global-dispatch-gate-ignores-aimd-current-de`.

**Evidence:**
```python
def _wait_for_dispatch_gate(self) -> None:
    delay_ms = self._config.min_dispatch_delay_ms  # Static, not AIMD
    if delay_ms <= 0:
        return  # No pacing at all if min_dispatch_delay_ms is 0
```

### [346-356] Dispatch gate records accumulated wait time including spurious loop iterations

**What:** In `_wait_for_dispatch_gate()`, `total_wait_ms` accumulates across loop iterations. But `remaining_ms` is computed from `remaining_s` which was computed before the sleep, not after. This means if the sleep completes and the gate is still not open (another thread snuck in), the accumulated `total_wait_ms` includes this iteration's planned sleep but the actual sleep may have been shorter (due to spurious wakeups, though `time.sleep` is not interruptible in CPython -- but the value `remaining_ms` is the *planned* sleep, not the *actual* sleep).

**Why it matters:** The throttle wait metrics recorded in the audit trail may be slightly inaccurate. This is a minor issue since the values are approximate anyway, but it's worth noting for audit precision.

**Evidence:**
```python
remaining_s = delay_s - time_since_last
remaining_ms = remaining_s * 1000
# Sleep OUTSIDE the lock
time.sleep(remaining_s)
total_wait_ms += remaining_ms  # Assumes sleep was exactly remaining_s
```

### [280-296] Final drain loop can silently drop entries if buffer implementation has a bug

**What:** The `while self._buffer.pending_count > 0` loop at lines 292-296 has a `break` on `if not ready`. The comment says "shouldn't happen if all futures completed," but if there's any edge case where a future completes but the buffer doesn't emit (e.g., a bug in `complete()` or `get_ready_results()`), the loop breaks and the subsequent assertion at line 298 catches the mismatch. This is actually defensive correctly -- the assertion will crash as it should.

**Why it matters:** The concern is theoretical. The assertion at line 298 is the correct crash-on-bug behavior per CLAUDE.md. However, it's worth noting that the loop's `break` means the error message will be about count mismatch rather than the actual root cause (buffer stuck), which could make debugging harder.

### [460-463] Throttle wait is recorded after sleep but before re-acquiring semaphore

**What:** After sleeping for the retry delay, the code records throttle wait time at line 463 and then re-acquires the semaphore at line 466. If semaphore acquisition blocks (because pool is full), the additional wait time spent acquiring the semaphore is not recorded in throttle stats.

**Why it matters:** Audit trail underreports actual time a worker spent blocked during retry. The gap between "sleeping for backoff" and "actually dispatching" is not captured.

**Evidence:**
```python
time.sleep(retry_delay_ms / 1000)
self._throttle.record_throttle_wait(retry_delay_ms)  # Only sleep time
# Missing: time spent waiting for semaphore below
self._semaphore.acquire()  # May block further
```

## Observations

### [88-125] Initialization creates resources that are never cleaned up on partial failure

**What:** If `ThreadPoolExecutor`, `Semaphore`, or `AIMDThrottle` initialization fails partway through `__init__`, previously created resources (e.g., the thread pool) are not cleaned up. This is standard Python behavior (no RAII), but worth noting since `ThreadPoolExecutor` spawns threads.

### [29-43] `RowContext.row` is a shared mutable reference

**What:** `RowContext.row` is `dict[str, Any]`, a mutable type. The test at line 69-76 explicitly verifies this shared-reference behavior. Since rows are dispatched to different threads, if a caller mutates the dict after submitting it, the worker thread sees the mutation. The current consumers (`azure_multi_query.py`) create fresh dicts per context, so this is not a current problem, but it's a footgun.

### [254-275] `futures` dict uses `Future` objects as keys

**What:** `futures: dict[Future[...], int]` uses `Future` objects as dictionary keys. This is correct since `Future` objects are hashable by identity (`id()`), but it's unusual. The dict is only used for tracking buffer indices alongside futures and doesn't require key stability, so this is fine.

### [410] Catch clause catches both `CapacityError` and `LLMClientError`

**What:** The retry loop catches `(CapacityError, LLMClientError)`. Since `LLMClientError` is a separate class from `CapacityError` (they don't share an inheritance chain), both must be listed. This is correct but means any new exception type intended for retry must be explicitly added here. The code documents this clearly at lines 411-415.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Fix the three confirmed P2 bugs (stats accumulation, dispatch gate pacing, shutdown). The `_shutdown` flag issue should be addressed as part of the shutdown fix -- either add a check inside the retry loop or use a threading.Event for cooperative cancellation. The stats accumulation fix is a one-liner (add `self._throttle.reset_stats()` to `_reset_batch_stats()`). The dispatch gate fix requires reading `self._throttle.current_delay_ms` instead of the static config value.
**Confidence:** HIGH -- The bugs are confirmed by filed reports with reproduction steps. The concurrency model has been validated by extensive tests including deadlock regression tests.
