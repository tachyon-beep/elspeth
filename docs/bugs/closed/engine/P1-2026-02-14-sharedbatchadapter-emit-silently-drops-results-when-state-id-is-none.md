## Summary

`SharedBatchAdapter.emit()` silently drops results when `state_id` is `None`, which can mask internal invariant violations and turn real plugin/caller bugs into long timeout failures.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — state_id=None requires a pre-existing executor bug; in all known production paths state_id is always set by begin_node_state(); defensive pattern violation is real but precondition is structurally guaranteed)

## Location

- File: `src/elspeth/engine/batch_adapter.py`
- Line(s): 205-207
- Function/Method: `SharedBatchAdapter.emit`

## Evidence

`emit()` currently does an unconditional silent return when `state_id` is missing:

```python
# src/elspeth/engine/batch_adapter.py:205-207
if state_id is None:
    # Cannot match a waiter without state_id - discard result
    return
```

But waiters only complete when `emit()` sets their event; otherwise they timeout:

```python
# src/elspeth/engine/batch_adapter.py:95-114
if not self._event.wait(timeout=timeout):
    ...
    raise TimeoutError(...)
```

Executor behavior on that timeout records a failed node state with `TimeoutError` and may retry:

- `src/elspeth/engine/executors/transform.py:249`
- `src/elspeth/engine/executors/transform.py:255-267`
- `src/elspeth/engine/executors/transform.py:277-282`

Timeout can be very long (default 3600s):

- `src/elspeth/plugins/batching/mixin.py:126`
- `src/elspeth/plugins/batching/mixin.py:146`

Plugins explicitly treat missing `state_id` as an internal bug and raise immediately:

- `src/elspeth/plugins/llm/openrouter.py:535-536`
- `src/elspeth/plugins/llm/azure.py:438-439`

Tests also codify that expectation (exception propagation, not silent recovery):

- `tests/unit/plugins/llm/test_openrouter.py:549-582`
- `tests/unit/plugins/llm/test_azure.py:479-511`

So in adapter-backed execution, the current silent drop path can hide the real bug and misclassify it as timeout.

## Root Cause Hypothesis

`SharedBatchAdapter` treats `state_id=None` as a discardable condition, but for this adapter `state_id` is effectively required for correlation. The silent-return path conflicts with the project's crash-on-internal-bug policy and causes bug-hiding behavior.

## Suggested Fix

Handle `state_id=None` as an invariant failure instead of dropping silently:

1. In `emit()`, when `state_id is None`, locate waiter(s) for `token.token_id` and deliver an `ExceptionResult` (e.g., `RuntimeError("Missing state_id in batch emit...")`) so `waiter.wait()` fails immediately.
2. If no waiter exists, emit explicit structured error logging (or raise an invariant error in a controlled way) rather than silent return.
3. Add a unit test in `tests/unit/engine/test_batch_adapter.py` asserting `emit(..., state_id=None)` surfaces an immediate exception via waiter (not timeout).

## Impact

- Real internal bugs can be hidden behind `TimeoutError`.
- Failure latency can stretch to configured batch timeout (often 3600s), slowing incident detection.
- Retries may be triggered on false timeout classification, causing unnecessary external calls/work.
- Audit trail may record misleading failure cause, weakening diagnostic and accountability guarantees.
