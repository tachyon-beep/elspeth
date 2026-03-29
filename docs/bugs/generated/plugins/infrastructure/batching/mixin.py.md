## Summary

`BatchTransformMixin.accept_row()` does not honor shutdown and can orphan a buffered submission if a row is accepted while `shutdown_batch_processing()` is in progress.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/batching/mixin.py`
- Line(s): 176-221, 420-449
- Function/Method: `accept_row`, `shutdown_batch_processing`

## Evidence

`shutdown_batch_processing()` claims step 1 "prevents new submissions via accept_row", but the code only sets `self._batch_shutdown` and `accept_row()` never checks that flag:

```python
# src/elspeth/plugins/infrastructure/batching/mixin.py:436-446
self._batch_shutdown.set()
self._batch_executor.shutdown(wait=True)
self._batch_buffer.shutdown()
self._batch_release_thread.join(timeout=timeout)
```

```python
# src/elspeth/plugins/infrastructure/batching/mixin.py:205-214
ticket = self._batch_buffer.submit(row_id)

if state_id is not None:
    with self._batch_submissions_lock:
        self._batch_submissions[(token.token_id, state_id)] = ticket

self._batch_executor.submit(
    self._process_and_complete,
    ticket,
    token,
    row,
    ctx,
    processor,
)
```

The only shutdown gate in the buffer is `RowReorderBuffer._shutdown`, but that is not set until step 3 of shutdown:

```python
# src/elspeth/plugins/infrastructure/batching/row_reorder_buffer.py:191-205
while len(self._pending) >= self._max_pending:
    if self._shutdown:
        raise ShutdownError(...)
...
if self._shutdown:
    raise ShutdownError(...)
```

That creates a race window:

1. `shutdown_batch_processing()` sets `_batch_shutdown`.
2. A concurrent `accept_row()` still calls `self._batch_buffer.submit(...)` successfully, because the buffer is not shut down yet.
3. `accept_row()` then calls `self._batch_executor.submit(...)` after executor shutdown has started, which raises.
4. The mixin never rolls back the already-submitted ticket or the `_batch_submissions` entry.

The orphaned buffer entry is then silently skipped on final buffer shutdown because `wait_for_next_release()` only releases completed entries and raises `ShutdownError` once `_shutdown` is set, even if an incomplete pending entry still exists:

```python
# src/elspeth/plugins/infrastructure/batching/row_reorder_buffer.py:282-319
if self._next_release_seq in self._pending:
    entry = self._pending[self._next_release_seq]
    if entry.is_complete:
        ...
if self._shutdown:
    raise ShutdownError(...)
```

Tests cover eviction and drain-after-shutdown, but I did not find coverage for "submit during shutdown" (`tests/unit/plugins/batching/test_batch_transform_mixin.py` covers normal shutdown paths at lines 513-579, not concurrent accept-after-shutdown-start).

## Root Cause Hypothesis

The mixin implements a drain-first shutdown, but the shutdown sentinel and the actual submission gates are split across two different components. `_batch_shutdown` is treated as the authoritative "no new work" flag in comments and method docs, yet `accept_row()` never enforces it. Because the buffer submission happens before worker-pool submission, any executor-side failure after shutdown begins leaves internal batching state inconsistent.

## Suggested Fix

Make `accept_row()` fail fast once `_batch_shutdown` is set, and roll back the ticket if worker-pool submission fails.

Helpful shape:

```python
if self._batch_shutdown.is_set():
    raise ShutdownError(f"Batch processing for {self._batch_name} is shut down")

ticket = self._batch_buffer.submit(row_id)

try:
    self._batch_executor.submit(...)
except Exception:
    if state_id is not None:
        with self._batch_submissions_lock:
            self._batch_submissions.pop((token.token_id, state_id), None)
    self._batch_buffer.evict(ticket)
    raise
```

Also update the exception type/message so callers get a clear shutdown-specific failure instead of a raw executor `RuntimeError`.

## Impact

A row accepted during shutdown can be recorded into the batching layer but never processed or emitted. That violates the mixin's documented drain-first contract, leaves stale internal state behind, and can make shutdown appear clean even though the batching layer dropped work internally. In executor-driven flows the node state may still end as `FAILED`, but the target file still loses its own submission and can wedge or misreport pending/drain behavior.
