## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/engine/batch_adapter.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/engine/batch_adapter.py
- Line(s): 79-284
- Function/Method: RowWaiter.wait, SharedBatchAdapter.register, SharedBatchAdapter.emit, SharedBatchAdapter._signal_waiters_by_token_id

## Evidence

I read the target file and traced its integration with the batch execution path in [transform.py](/home/john/elspeth/src/elspeth/engine/executors/transform.py#L266), the batch mixin release loop in [mixin.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/batching/mixin.py#L281), the output-port contract in [ports.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/batching/ports.py#L25), and node-state lifecycle enforcement in [state_guard.py](/home/john/elspeth/src/elspeth/engine/executors/state_guard.py#L88).

The target file’s main invariants appear intentionally enforced:

```python
if not self._event.wait(timeout=timeout):
    with self._lock:
        self._entries.pop(self._key, None)
    raise TimeoutError(...)
```

[batch_adapter.py](/home/john/elspeth/src/elspeth/engine/batch_adapter.py#L120) cleans up timed-out waiters, which matches the retry/eviction design used by the executor at [transform.py](/home/john/elspeth/src/elspeth/engine/executors/transform.py#L318).

```python
if key in self._entries and not self._entries[key].event.is_set():
    self._entries[key].deliver(result)
```

[batch_adapter.py](/home/john/elspeth/src/elspeth/engine/batch_adapter.py#L243) preserves first-result-wins semantics and avoids overwriting an already-signaled waiter.

```python
if state_id is None:
    error = OrchestrationInvariantError(...)
    self._signal_waiters_by_token_id(token.token_id, error)
    return
```

[batch_adapter.py](/home/john/elspeth/src/elspeth/engine/batch_adapter.py#L228) fails fast on missing `state_id` instead of letting the orchestrator hang until timeout.

The intended behaviors are also covered by focused tests in [test_batch_adapter.py](/home/john/elspeth/tests/unit/engine/test_batch_adapter.py#L164), [test_batch_adapter.py](/home/john/elspeth/tests/unit/engine/test_batch_adapter.py#L307), and [test_batch_adapter.py](/home/john/elspeth/tests/unit/engine/test_batch_adapter.py#L436), including timeout cleanup, retry safety, duplicate emit handling, and `state_id=None` error delivery.

## Root Cause Hypothesis

No bug identified.

## Suggested Fix

No fix recommended.

## Impact

No confirmed defect in this file based on the audited code paths. Residual risk is Unknown.
