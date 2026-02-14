# Plugins-Batching Bug Triage Notes (2026-02-14)

## Summary Table

| # | Bug | File | Original | Triaged | Verdict |
|---|-----|------|----------|---------|---------|
| 1 | Release loop can fail to propagate real error with stale token/state_id | mixin.py | P1 | P2 | Downgraded |
| 2 | Shutdown batch processing can silently drop in-flight rows | mixin.py | P1 | P2 | Downgraded |

**Result:** 0 confirmed at original priority, 2 downgraded.

## Detailed Assessments

### Bug 1: Release loop stale token/state_id in exception handler (P1 -> P2)

The code pattern identified is real. In `_release_loop()` (lines 282-329), the `except Exception` handler at line 307 references `token` and `state_id` (line 319) which are assigned at line 288. If an exception occurs at line 285 (`wait_for_next_release`) that is not `TimeoutError` or `ShutdownError`, those variables would reference values from a previous iteration (stale) or be unbound on the first iteration.

However, this is downgraded to P2 because:

1. **The triggering exceptions are invariant violations:** `wait_for_next_release()` (lines 240-269 in `row_reorder_buffer.py`) raises `RuntimeError` at lines 254-257 only on internal invariant violations (`is_complete=True` but `result is None`, or `completed_at is None`). These are Tier 1 data corruption scenarios that per CLAUDE.md should crash immediately.
2. **TimeoutError and ShutdownError are caught first:** The normal exception paths (`TimeoutError` at line 299, `ShutdownError` at line 303) are caught before the generic `except Exception` handler. The only exceptions reaching line 307 from `wait_for_next_release` are `RuntimeError` invariant violations.
3. **On first iteration, variables are unbound:** If the exception occurs on the first loop iteration before line 288 executes, `token` and `state_id` are not defined, causing an `UnboundLocalError` in the exception handler at line 319. This would be caught by the outer `except Exception` at line 320, logged, and the loop would continue. The result is a confusing error message, not silent data loss.
4. **On subsequent iterations, the stale emit targets the wrong waiter:** The `emit()` call at line 319 with stale `token`/`state_id` would deliver the `ExceptionResult` to an already-completed waiter (from the previous iteration), which would discard it. The current iteration's waiter hangs until timeout, which is the symptom described in the bug.

The fix (initializing `token = None` and `state_id = None` at loop start, then checking before emit) is correct and worth implementing for robustness. But the triggering condition requires an internal invariant violation that would itself indicate a serious bug in the buffer implementation.

### Bug 2: Shutdown batch processing can silently drop in-flight rows (P1 -> P2)

The shutdown ordering concern is technically valid but the race window is narrower than described.

Analyzing the shutdown sequence in `shutdown_batch_processing()` (lines 391-416):
1. `self._batch_shutdown.set()` (line 403) -- signals release loop to exit
2. `self._batch_executor.shutdown(wait=True)` (line 406) -- blocks until all workers finish
3. `self._batch_buffer.shutdown()` (line 409) -- sends ShutdownError to wake release thread
4. `self._batch_release_thread.join(timeout=timeout)` (line 412) -- waits for release thread

The race window: between lines 403 and 406, the release thread may check `_batch_shutdown.is_set()` and exit its while loop. Meanwhile, workers that are still running (not yet finished at line 406) complete their work and call `complete()` on their tickets. The release thread is no longer running to drain these results. The executor shutdown at line 406 then waits for workers to finish, but completed results remain in the buffer undrained.

However, this is downgraded to P2 because:

1. **In the normal execution flow, rows are processed one-at-a-time:** The `TransformExecutor` (lines 231-249 in `transform.py`) processes rows sequentially, blocking on `waiter.wait()` for each row's result before processing the next. This means by the time `close()` is called, the last submitted row's result has already been waited on and emitted.
2. **`flush_batch_processing` is the documented drain path:** The docstring examples in `azure.py:112-114` and `openrouter.py:96-98` show `flush_batch_processing()` followed by `close()`. The flush operation blocks until `pending_count == 0`.
3. **The orchestrator drains before closing:** The `RowProcessor` processes all work items before returning to the orchestrator. By the time `_close_pipeline_resources` at `orchestrator/core.py:402-407` calls `transform.close()`, all rows have been submitted, waited on, and emitted through the normal executor flow.
4. **The gap is real for error/interrupt paths:** If the pipeline is interrupted (kill signal, unhandled exception) and `close()` is called during cleanup while workers are still processing, results can be lost. But interrupt scenarios already have incomplete audit trails as a known limitation.

The fix (drain-first shutdown) is correct for robustness, particularly if future cross-row parallelism is added to the orchestrator. But in the current sequential-processing architecture, the race condition requires an error or interrupt path that already implies incomplete processing.

## Cross-Cutting Observations

### 1. Both bugs relate to the release thread lifecycle boundary

Both bugs concern the interface between the release thread and the rest of the batch processing infrastructure. Bug 1 is about exception handling within the release loop; Bug 2 is about shutdown ordering. The underlying issue is that the release thread is a consumer in a producer-consumer pattern, and its lifecycle transitions (exception handling, shutdown) need to be more carefully coordinated with the producer side (worker threads, buffer).

### 2. Sequential row processing architecture limits blast radius

Both bugs are mitigated by the current architecture decision to process rows one-at-a-time across rows (concurrency only within a row). This means the steady-state buffer typically has at most one pending entry. If cross-row parallelism is added to the orchestrator in the future, both bugs would escalate in severity because multiple in-flight rows could be affected simultaneously.

### 3. The `close()` without `flush()` pattern in LLM plugins

The bug report correctly notes that `azure.py:591-593` and `openrouter.py:711-713` call `shutdown_batch_processing()` without `flush_batch_processing()`. However, the `flush` calls shown in the docstring examples (azure.py:112-114, openrouter.py:96-98) are for standalone usage, not the orchestrator path. In the orchestrator path, the executor handles draining via its sequential wait pattern.
