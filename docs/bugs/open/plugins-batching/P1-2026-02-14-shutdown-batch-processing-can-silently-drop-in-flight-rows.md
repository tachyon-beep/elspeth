## Summary

`shutdown_batch_processing()` can silently drop in-flight rows by stopping the release loop before worker completion, violating its own "graceful shutdown" contract.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 -- sequential row processing architecture means buffer has at most one pending entry at close time; orchestrator drains via waiter.wait() before calling close(); race window only reachable during error/interrupt paths)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/batching/mixin.py
- Line(s): 282, 391-413
- Function/Method: `BatchTransformMixin._release_loop`, `BatchTransformMixin.shutdown_batch_processing`

## Evidence

Release loop exits solely on `_batch_shutdown`:

```python
while not self._batch_shutdown.is_set():
```

Shutdown sets that flag first, then waits for workers:

```python
self._batch_shutdown.set()
self._batch_executor.shutdown(wait=True)
self._batch_buffer.shutdown()
```

So if shutdown happens with pending work, release thread may exit before workers finish and call `complete()`. Completed results then stay undispatched because no release loop remains to emit them.

This is not theoretical in lifecycle wiring: orchestrator closes transforms directly (`/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:403-406`), and plugin `close()` implementations call `shutdown_batch_processing()` without mandatory `flush_batch_processing()` (for example `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure.py:591-593`, `/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter.py:711-713`).

## Root Cause Hypothesis

Shutdown ordering is inverted for a producer/consumer pipeline: consumer thread is signaled to stop before producers are drained.

## Suggested Fix

Drain-first shutdown sequence in the mixin:

1. Stop accepting new submissions.
2. Wait for worker pool completion.
3. Keep release loop alive until buffer drained.
4. Then shutdown buffer and join release thread.

Practical code change in target file:

- Remove `_batch_shutdown` from loop condition (exit on `ShutdownError` from buffer instead).
- In `shutdown_batch_processing()`, call executor shutdown before triggering release-loop termination.
- Optionally enforce `pending_count == 0` (or call `flush_batch_processing`) before final stop.

## Impact

- Accepted rows can disappear without being emitted downstream.
- Can produce silent data loss and missing terminal outcomes in audit flow.
- Violates stated auditability principle that row progression must be fully attributable.
