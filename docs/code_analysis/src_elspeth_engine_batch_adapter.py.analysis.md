# Analysis: src/elspeth/engine/batch_adapter.py

**Lines:** 227
**Role:** Provides a thread-safe adapter that bridges batch transforms (which process rows asynchronously via accept/release) with the synchronous orchestrator flow. SharedBatchAdapter is a single output port connected to a batch transform, routing results to per-row RowWaiters keyed by (token_id, state_id) for retry safety.
**Key dependencies:**
- Imports: `threading` (stdlib), `ExceptionResult` (contracts), `TransformResult` and `TokenInfo` (TYPE_CHECKING)
- Imported by: `engine/executors.py` (TransformExecutor._get_batch_adapter creates SharedBatchAdapter instances)
**Analysis depth:** FULL

## Summary

SharedBatchAdapter is a well-designed concurrent adapter with thorough attention to threading safety, retry isolation, and resource cleanup. The documented race condition between `emit()` and timeout in `wait()` is correctly handled with cleanup of both `_waiters` and `_results`. The retry safety model using (token_id, state_id) composite keys is sound. The most notable concern is that `clear()` does not signal pending waiters, meaning waiters blocked on `event.wait()` during shutdown will hang until their individual timeout expires. The overall implementation quality is high.

## Warnings

### [219-227] clear() does not signal blocked waiters

**What:** The `clear()` method removes all entries from `_waiters` and `_results` but does not `set()` the events for any waiters that are currently blocked on `event.wait()`. Those waiters will remain blocked until their individual timeout expires (default 300 seconds), at which point they'll raise `TimeoutError`.

**Why it matters:** If `clear()` is called during shutdown while waiters are blocked:
1. The orchestrator thread(s) blocked on `waiter.wait()` will hang for up to 300 seconds each.
2. When the timeout fires, the waiter tries `self._waiters.pop(self._key, None)` but the key is already cleared, and `self._results.pop(self._key, None)` similarly finds nothing. This is safe (no crash), but the 300-second hang is problematic.
3. The docstring says "In production, normal flow ensures all waiters receive results before shutdown" -- but abnormal shutdown (crash, interrupt) could leave waiters stranded.

**Evidence:**
```python
def clear(self) -> None:
    """Clear all pending waiters and results.
    For testing and cleanup. In production, normal flow ensures
    all waiters receive results before shutdown.
    """
    with self._lock:
        self._waiters.clear()   # Events NOT signaled
        self._results.clear()   # Blocked waiters will hang
```
A more robust implementation would iterate `_waiters` and call `event.set()` before clearing, so blocked waiters immediately wake and find no result (raising `KeyError` or `TimeoutError` depending on path).

### [58-79] RowWaiter holds references to parent's internal dicts

**What:** RowWaiter receives direct references to `SharedBatchAdapter._results`, `SharedBatchAdapter._waiters`, and `SharedBatchAdapter._lock` (lines 62-64, stored at lines 77-79). This means RowWaiter has full mutable access to the parent adapter's internal state.

**Why it matters:** This is an intentional design choice for performance (avoids callback indirection), but it creates a tight coupling where RowWaiter is effectively a proxy with full internal access. Any bug in RowWaiter (or accidental misuse of the shared dicts) could corrupt SharedBatchAdapter's state. The access pattern is carefully controlled (only `pop` in `wait`, only `pop` in timeout cleanup), but the shared mutable state is a surface for subtle bugs if the code evolves.

**Evidence:**
```python
# RowWaiter stores direct references to parent's internals
self._results = results    # SharedBatchAdapter._results
self._waiters = waiters    # SharedBatchAdapter._waiters
self._lock = lock          # SharedBatchAdapter._lock
```

### [116-117] wait() success path assumes result key exists

**What:** On the success path (event was set), `wait()` does `result = self._results.pop(self._key)` without `.pop(key, None)` or a check. If `emit()` set the event but did NOT store the result (hypothetical bug), this would raise `KeyError`.

**Why it matters:** Looking at `emit()` (line 212-213), the result is stored before the event is set (`self._results[key] = result` then `self._waiters[key].set()`), so the result is guaranteed to be present when the event fires. However, there's a subtle threading consideration: if `clear()` is called between `event.set()` in `emit()` and the lock acquisition in `wait()`, the result will have been cleared and `pop` will raise `KeyError`.

This race sequence:
1. `emit()` acquires lock, stores result, sets event, releases lock
2. `clear()` acquires lock, clears all results, releases lock
3. `wait()` wakes from event.wait(), acquires lock, calls `self._results.pop(self._key)` -> `KeyError`

The window is small and `clear()` is documented as "for testing and cleanup," but it represents an unhandled crash path.

**Evidence:**
```python
# Line 116-117 - no defensive .pop(key, None)
with self._lock:
    result = self._results.pop(self._key)  # KeyError if clear() raced
```

## Observations

### [188-217] emit() correctly discards results when no waiter exists

**What:** When `emit()` is called and no matching waiter exists in `_waiters`, the result is silently discarded (line 216). This correctly handles the case where a waiter timed out and a retry is in progress.

**Why it matters:** Positive observation -- the discard path prevents memory leaks (no orphaned results stored indefinitely) and supports the retry safety model.

### [205-207] emit() guards against None state_id

**What:** If `state_id is None`, the result is discarded immediately without attempting to construct a key.

**Why it matters:** Positive observation -- prevents `None` from being used as a dict key and silently handled. The comment explains this is because no waiter can be matched without a state_id.

### [96-109] Race condition documentation in wait() timeout path is excellent

**What:** The comment at lines 96-106 documents the exact race condition that the timeout cleanup addresses, with step-by-step sequence of events.

**Why it matters:** Positive observation -- this level of documentation for concurrent code is essential. It explains WHY both `_waiters` and `_results` are cleaned up in the timeout path, preventing future maintainers from "optimizing" away the apparently-redundant `_results.pop`.

### [36] __all__ re-exports ExceptionResult

**What:** `__all__` includes `ExceptionResult` which is imported from `elspeth.contracts`. This creates an alternate import path.

**Why it matters:** Minor -- consumers should import `ExceptionResult` from `elspeth.contracts`, not from `elspeth.engine.batch_adapter`.

### [81] Default timeout of 300 seconds

**What:** `wait()` defaults to a 300-second (5-minute) timeout.

**Why it matters:** 300 seconds is generous. For transforms that are known to be fast, this means a hung transform won't be detected for 5 minutes. The caller (TransformExecutor) does not override this default. Depending on the transform type, a shorter timeout might be appropriate. This is a configuration concern rather than a bug.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) `clear()` should signal all pending waiters before clearing state, to prevent 300-second hangs during abnormal shutdown. (2) The `wait()` success path at line 117 should handle the race with `clear()` -- either by using `.pop(key, None)` with an appropriate error if None, or by documenting that `clear()` must not be called while waiters are active. (3) Consider whether the 300-second default timeout should be configurable or derived from the transform's expected latency.
**Confidence:** HIGH -- Complete analysis of all threading interactions between register(), emit(), wait(), and clear(). Cross-referenced with TransformExecutor usage in executors.py to verify production call patterns.
