## Summary

`AuditedHTTPClient` instances are cached by `state_id` but never evicted per batch, causing unbounded client growth and resource leakage during long-running aggregation runs.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1: resource leak bounded by batch count; cleaned up at close(); only extreme runs affected)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter_batch.py
- Line(s): 197, 554, 555, 558, 569, 769, 773
- Function/Method: `__init__`, `_get_http_client`, `close`

## Evidence

`/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter_batch.py:197` initializes a persistent cache:

```python
self._http_clients: dict[str, AuditedHTTPClient] = {}
```

`/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter_batch.py:555` creates one client per new `state_id` and stores it forever in `_http_clients`.
There is no per-batch eviction in `_process_batch`; cleanup happens only in `/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter_batch.py:769` inside `close()` (run end).

Aggregation flushes generate new `state_id`s each time (`/home/john/elspeth-rapid/src/elspeth/engine/executors/aggregation.py:332`, `/home/john/elspeth-rapid/src/elspeth/engine/executors/aggregation.py:343`), so cache size grows with number of flushes.

## Root Cause Hypothesis

The cache is keyed to a value (`state_id`) that is intentionally unique per flush, but lifecycle management assumes reuse and only frees clients at plugin shutdown.

## Suggested Fix

Evict and close the state-scoped client after each batch finishes (success or failure), e.g. `finally` in `_process_batch`:

```python
state_id = ctx.state_id
try:
    ...
finally:
    with self._http_clients_lock:
        client = self._http_clients.pop(state_id, None)
    if client is not None:
        client.close()
```

## Impact

Long-running jobs can accumulate many live `httpx.Client` instances, increasing memory/socket usage and eventually causing degraded throughput or failures (resource exhaustion).

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/openrouter_batch.py.md`
- Finding index in source report: 2
- Beads: pending
