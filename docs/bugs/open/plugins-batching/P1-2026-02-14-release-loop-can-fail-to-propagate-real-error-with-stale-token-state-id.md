## Summary

`_release_loop()` can fail to propagate the real release-thread error because it uses `token/state_id` in the exception path even when they were never assigned for the current iteration.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 -- triggering exceptions are internal invariant violations that per CLAUDE.md should crash immediately; normal exceptions TimeoutError/ShutdownError are caught before the generic handler)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/batching/mixin.py
- Line(s): 285-320
- Function/Method: `BatchTransformMixin._release_loop`

## Evidence

In `mixin.py`, `token` and `state_id` are assigned only after `wait_for_next_release()` succeeds:

```python
entry = self._batch_buffer.wait_for_next_release(timeout=1.0)
token, result, state_id = entry.result
```

But the catch-all handler always tries to emit with those variables:

```python
except Exception as e:
    ...
    self._batch_output.emit(token, exception_result, state_id)
```

If an exception occurs before unpack (for example, `RowReorderBuffer.wait_for_next_release()` invariant failures at `/home/john/elspeth-rapid/src/elspeth/plugins/batching/row_reorder_buffer.py:254-257`), `token/state_id` are not valid for the current entry. That causes the fallback emit to fail or target stale previous-row values, and the waiter then hangs until timeout (explicitly acknowledged by log text at `mixin.py:326-328`).

Integration consequence is amplified by executor wait timeout at `/home/john/elspeth-rapid/src/elspeth/engine/executors/transform.py:249` (often very large via batch timeout config), so real root cause gets masked as timeout.

## Root Cause Hypothesis

The exception handler assumes every exception happens after `entry.result` unpack, but the protected `try` block also includes earlier operations that can fail.

## Suggested Fix

Split exception scopes and only emit per-row `ExceptionResult` when a current `token/state_id` is definitely available.

- Initialize `token/state_id` to `None` at each loop start.
- Handle pre-entry failures separately (log and trigger fail-fast shutdown path).
- Keep per-row emit fallback only for failures after unpack.

Example direction:

```python
while ...:
    token = None
    state_id = None
    try:
        entry = self._batch_buffer.wait_for_next_release(timeout=1.0)
        token, result, state_id = entry.result
        ...
        self._batch_output.emit(token, result, state_id)
    except Exception as e:
        if token is None or state_id is None:
            # fail-fast path; do not emit with stale/unbound routing data
            ...
        else:
            ...
```

## Impact

- Real release-thread errors are hidden behind generic timeout failures.
- Failure attribution can be wrong (stale routing key) or missing.
- Pipeline can stall for long wait timeouts instead of failing immediately with actionable error context.
