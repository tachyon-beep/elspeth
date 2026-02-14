## Summary

`AzureLLMTransform._process_row()` uses mutable `ctx.state_id` in cleanup, which can evict the wrong cached client during retry/timeout races.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1: race condition requires specific timeout timing and impact is resource leak, not data corruption)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure.py`
- Line(s): 438-447, 517-519
- Function/Method: `AzureLLMTransform._process_row`

## Evidence

`_process_row()` reads `ctx.state_id` for client creation, then later uses `ctx.state_id` again in `finally` for cache eviction:

```python
if ctx.state_id is None:
    raise RuntimeError(...)
...
llm_client = self._get_llm_client(ctx.state_id, token_id=token_id)
...
finally:
    with self._llm_clients_lock:
        self._llm_clients.pop(ctx.state_id, None)
```

`ctx.state_id` is not immutable per worker attempt. The engine rewrites it per attempt on the shared context:

- `src/elspeth/engine/executors/transform.py:188` sets `ctx.state_id = state.state_id`
- `src/elspeth/engine/processor.py:1082-1090` retries by reusing the same `ctx` object
- `src/elspeth/engine/executors/transform.py:269-283` allows timeout + retry while prior worker may still finish

So a late-finishing prior attempt can run `pop(ctx.state_id, None)` against a newer attempt's state_id, removing the wrong client and leaking the original one.

## Root Cause Hypothesis

Attempt-specific keying relies on `PluginContext` mutable state instead of snapshotting attempt-local identifiers in the worker method.

## Suggested Fix

Snapshot `state_id` (and token_id) once at function start and use only the snapshot throughout:

```python
state_id = ctx.state_id
if state_id is None:
    raise RuntimeError(...)
token_id = ctx.token.token_id
llm_client = self._get_llm_client(state_id, token_id=token_id)
...
finally:
    with self._llm_clients_lock:
        self._llm_clients.pop(state_id, None)
```

## Impact

- Wrong cache entry can be evicted under retry/timeout races.
- Original client may remain cached (resource leak).
- Call-index continuity assumptions tied to per-state client lifecycle become unreliable under stress/retry scenarios.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/azure.py.md`
- Finding index in source report: 1
- Beads: pending
