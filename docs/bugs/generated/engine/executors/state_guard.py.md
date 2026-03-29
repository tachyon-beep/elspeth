## Summary

`NodeStateGuard.__exit__()` swallows generic recorder failures during auto-fail, so an exception path can still leave the node state `OPEN` even though this class claims to guarantee terminality.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/executors/state_guard.py
- Line(s): 147-166
- Function/Method: `NodeStateGuard.__exit__`

## Evidence

`state_guard.py` says the guard provides a structural guarantee that every opened node state reaches terminal status:

```python
# src/elspeth/engine/executors/state_guard.py:140-166
exc_error = ExecutionError(...)
try:
    self._recorder.complete_node_state(
        state_id=self.state_id,
        status=NodeStateStatus.FAILED,
        duration_ms=duration_ms,
        error=exc_error,
    )
except (FrameworkBugError, AuditIntegrityError):
    raise
except (TypeError, AttributeError, KeyError, NameError):
    raise
except Exception:
    logger.error(...)
```

For any non-listed exception from `complete_node_state()` such as a DB outage, the guard only logs and then lets the original exception continue. That means the `node_states` row opened in `__enter__` remains `OPEN`.

The repository contract does not provide any fallback terminalization on failure; `complete_node_state()` is the only place that writes terminal status:

```python
# src/elspeth/core/landscape/execution_repository.py:288-317
update_result = conn.execute(
    node_states_table.update()
    .where(node_states_table.c.state_id == state_id)
    .values(status=status, ...)
)
if update_result.rowcount == 0:
    raise AuditIntegrityError(...)
...
result = self._node_state_loader.load(row)
```

The current test suite explicitly encodes this orphaning behavior:

```python
# tests/unit/engine/test_executors.py:3479-3496
recorder.complete_node_state.side_effect = RuntimeError("DB is down")
with pytest.raises(ValueError, match="original error"), guard:
    raise ValueError("original error")
```

What the code does:
- If processing raises and the recorder also raises a generic exception, the guard logs and returns, so the original exception propagates.

What it should do:
- Escalate the audit-write failure, because failing to record the terminal state breaks the stated invariant and leaves the audit trail incomplete.

## Root Cause Hypothesis

The implementation prioritizes preserving the original processing exception over preserving the audit invariant. That conflicts with ELSPETH’s audit-first rules: the legal record is supposed to be must-fire and crash-on-failure. By treating generic recorder failures as log-only in the exception path, `NodeStateGuard` stops being a structural guarantee and becomes best-effort.

## Suggested Fix

Change the generic `except Exception` branch in `__exit__()` to raise an audit-integrity failure instead of logging-and-suppressing. Preserve the original exception with chaining.

Example shape:

```python
except Exception as record_err:
    raise AuditIntegrityError(
        f"Failed to auto-complete node state {self.state_id} as FAILED; "
        "audit trail would be left OPEN"
    ) from record_err
```

If retaining the original processing error is important, include its type/message in the raised `AuditIntegrityError` text, but do not allow the guard to return successfully after terminal-state recording failed.

## Impact

A crashing transform/gate/aggregation can still leave an `OPEN` `node_states` row when the recorder fails generically. That breaks the core audit guarantee that every token reaches a terminal state, undermines recovery/lineage queries, and makes “I don’t know what happened” possible for affected tokens.
---
## Summary

`NodeStateGuard.complete()` marks the guard as completed only after `complete_node_state()` returns, so a post-write exception in the recorder can cause `__exit__()` to overwrite an already-persisted terminal state with `FAILED`.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/executors/state_guard.py
- Line(s): 198-207, 106-107, 147-153
- Function/Method: `NodeStateGuard.complete`, `NodeStateGuard.__exit__`

## Evidence

The guard uses `_completed` to decide whether `__exit__()` should intervene:

```python
# src/elspeth/engine/executors/state_guard.py:106-107
if self._completed:
    return
```

But `_completed` is only flipped after the recorder call returns:

```python
# src/elspeth/engine/executors/state_guard.py:198-207
self._recorder.complete_node_state(
    state_id=self.state_id,
    status=status,
    output_data=output_data,
    duration_ms=duration_ms,
    error=error,
    success_reason=success_reason,
    context_after=context_after,
)
self._completed = True
```

The recorder persists the terminal update before it loads/validates the row it just wrote:

```python
# src/elspeth/core/landscape/execution_repository.py:288-317
update_result = conn.execute(
    node_states_table.update()
    .where(node_states_table.c.state_id == state_id)
    .values(status=status, ...)
)
...
row = conn.execute(select(node_states_table).where(...)).fetchone()
...
result = self._node_state_loader.load(row)
```

Because the database update happens before the loader returns, a failure after the update but before `NodeStateGuard.complete()` sets `_completed = True` leaves the guard thinking the state is still open. If that exception escapes the `with` block, `__exit__()` runs its auto-fail path:

```python
# src/elspeth/engine/executors/state_guard.py:147-153
self._recorder.complete_node_state(
    state_id=self.state_id,
    status=NodeStateStatus.FAILED,
    duration_ms=duration_ms,
    error=exc_error,
)
```

What the code does:
- An explicit completion can persist `COMPLETED`/`PENDING`/`FAILED`, then raise.
- `__exit__()` sees `_completed == False` and writes `FAILED` again.

What it should do:
- Once explicit completion has started, `__exit__()` must not auto-fail the same state unless it is certain no terminal write occurred.

## Root Cause Hypothesis

`NodeStateGuard` models completion as a single boolean set after a fully successful round-trip, but the recorder API is not atomic from the guard’s perspective. It can mutate Tier 1 state before returning. The guard therefore conflates “recorder call raised” with “no terminal state was written,” which is not guaranteed by the integration contract.

## Suggested Fix

Track an intermediate state such as `_completion_attempted` or `_terminal_write_started` before calling `complete_node_state()`, and have `__exit__()` refuse to auto-fail when explicit completion already began.

Example shape:

```python
self._completion_started = True
self._recorder.complete_node_state(...)
self._completed = True
```

Then in `__exit__()`:

```python
if self._completed or self._completion_started:
    return
```

A stricter version would query the current node-state status on recorder exceptions and raise an `AuditIntegrityError` if the state is already terminal but the call still failed, rather than issuing a second completion.

## Impact

A successful terminal write can be mutated into `FAILED` by cleanup logic, corrupting the legal record of what actually happened. This can erase a real success, hide Tier 1 corruption behind a synthetic failure, and violate the “exactly one truthful terminal state” guarantee for the affected node.
