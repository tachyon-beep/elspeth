## Summary

`PooledExecutor.execute_batch()` has a shutdown race: if `shutdown()` happens while rows are being submitted, it can raise mid-submit and leave reserved buffer slots stranded.

## Severity

- Severity: minor
- Priority: P2
- Triaged: downgraded from P1 -- race requires shutdown(wait=False) during active submission; structurally unlikely in production; executor is discarded after shutdown

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/pooling/executor.py
- Line(s): 161-168, 259-277
- Function/Method: `shutdown`, `_execute_batch_locked`

## Evidence

`_execute_batch_locked` reserves a reorder-buffer slot before submitting to `ThreadPoolExecutor`, but does not handle submit failure:

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/pooling/executor.py:259-277
buffer_idx = self._buffer.submit()
future = self._thread_pool.submit(...)
futures[future] = buffer_idx
```

`shutdown()` can run concurrently and closes the pool immediately:

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/pooling/executor.py:167-168
self._shutdown_event.set()
self._thread_pool.shutdown(wait=wait)
```

If shutdown lands during submission, `submit()` raises `RuntimeError("cannot schedule new futures after shutdown")`, and the already-reserved buffer slot is never completed or rolled back.

I reproduced this race with a timed shutdown during a large submit loop (using this repo's code): result was:
- `execute_batch_exception RuntimeError cannot schedule new futures after shutdown`
- `pending_count 3098`

That confirms leaked internal state after the exception.

Integration evidence: shutdown during active work is an intended/used path (`tests/unit/plugins/llm/test_pooled_executor.py:915` calls `executor.shutdown(wait=False)` from processing flow), so this is not a purely hypothetical edge.

## Root Cause Hypothesis

Submission is non-atomic: buffer reservation and thread-pool submission are split, with no recovery path if submission fails due concurrent shutdown. The code assumes `submit()` cannot fail after reservation, which is false once shutdown can occur mid-batch.

## Suggested Fix

Handle submit failures inside `_execute_batch_locked` and keep buffer cardinality consistent:

- Wrap `self._thread_pool.submit(...)` in `try/except RuntimeError`.
- If shutdown is in progress, convert unscheduled rows to deterministic `TransformResult.error({"reason": "shutdown_requested", ...})` entries (including the already-reserved slot and remaining contexts), then continue normal drain.
- Ensure `pending_count` returns to zero on this path.
- Add a regression test: concurrent shutdown during submission must not raise from `execute_batch`, must return one result per context, and must leave `pending_count == 0`.

## Impact

- Batch execution can crash unexpectedly during shutdown/cancel flows.
- Internal reorder buffer can retain orphaned slots (`pending_count` leak), violating executor invariants.
- Rows in that batch may not receive deterministic per-row error outcomes from this layer (auditability impact: incomplete row-level outcome accounting during shutdown path).
