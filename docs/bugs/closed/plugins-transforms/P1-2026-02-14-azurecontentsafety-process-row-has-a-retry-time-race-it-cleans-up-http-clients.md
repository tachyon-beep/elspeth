## Summary

`AzureContentSafety._process_row()` has a retry-time race: it cleans up HTTP clients using mutable `ctx.state_id` in `finally`, which can point to a newer retry attempt and close the wrong client.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/content_safety.py`
- Line(s): 283-297
- Function/Method: `_process_row`

## Evidence

`_process_row()` uses `ctx.state_id` twice: once for work, then again later for cleanup.

```python
if ctx.state_id is None:
    raise RuntimeError(...)
...
return self._process_single_with_state(row, ctx.state_id, token_id=token_id)
...
with self._http_clients_lock:
    if ctx.state_id in self._http_clients:
        client = self._http_clients.pop(ctx.state_id)
```

Source: `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/content_safety.py:283-297`

But worker threads receive the shared mutable `ctx` object (`accept_row(..., ctx, ...)`):
`/home/john/elspeth-rapid/src/elspeth/plugins/batching/mixin.py:211-218`

And retry flow reuses the same `ctx` across attempts while assigning a new `ctx.state_id` each attempt:
`/home/john/elspeth-rapid/src/elspeth/engine/processor.py:1082-1090` and `/home/john/elspeth-rapid/src/elspeth/engine/executors/transform.py:188`

The architecture explicitly allows timed-out attempts to keep running while retry attempts proceed:
`/home/john/elspeth-rapid/src/elspeth/engine/batch_adapter.py:23-26,137-145`

So `finally` can pop/close the retry attempt's client instead of the original one.

## Root Cause Hypothesis

Cleanup is keyed off a mutable shared context field (`ctx.state_id`) instead of an immutable per-invocation snapshot, creating a cross-attempt race under timeout/retry overlap.

## Suggested Fix

Capture `state_id` once at method entry and use only that captured value for both processing and cleanup.

```python
state_id = ctx.state_id
if state_id is None:
    raise RuntimeError(...)
...
return self._process_single_with_state(row, state_id, token_id=token_id)
...
with self._http_clients_lock:
    client = self._http_clients.pop(state_id, None)
```

This keeps cleanup bound to the attempt that created the client.

## Impact

- Retry attempt client can be closed by stale timed-out worker.
- Stale clients can be leaked in `_http_clients` until transform shutdown.
- Can cause spurious network failures and unstable retry behavior in a security-critical external-call transform.
