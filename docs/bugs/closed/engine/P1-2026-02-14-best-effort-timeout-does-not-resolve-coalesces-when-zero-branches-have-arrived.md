## Summary

`best_effort` timeout does not resolve coalesces when zero branches have arrived (only `lost_branches` exists), so timed-out entries can remain pending indefinitely.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — `flush_pending` catches this at end-of-source for batch runs; only streaming sources with never-ending inputs are affected; fix is a one-liner else clause)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/engine/coalesce_executor.py
- Line(s): 763-765, 964-974
- Function/Method: `check_timeouts`, `notify_branch_lost`

## Evidence

`notify_branch_lost()` can create pending state with no arrivals:

```python
# coalesce_executor.py:964-973
if key not in self._pending:
    self._pending[key] = _PendingCoalesce(
        arrived={},
        ...
        lost_branches={lost_branch: reason},
    )
```

But `check_timeouts()` only handles `best_effort` when `len(pending.arrived) > 0`:

```python
# coalesce_executor.py:763-765
if settings.policy == "best_effort" and len(pending.arrived) > 0:
    outcome = self._execute_merge(...)
```

So a timed-out entry with `arrived == {}` is skipped and left in `_pending`.

Repro (executed in repo): after `notify_branch_lost(...)`, advancing clock past timeout, `check_timeouts("merge")` returns 0 outcomes and key remains in `_pending`.

This conflicts with documented behavior: `best_effort` waits until timeout and uses what arrived (`docs/reference/configuration.md:492`) and with the method docstring "merges whatever has arrived when timeout expires" (`coalesce_executor.py:724`).

## Root Cause Hypothesis

`check_timeouts()` assumes pending entries are created by `accept()` (which always has at least one arrival), but `notify_branch_lost()` introduced a second creation path with zero arrivals. Timeout logic was not updated for that state shape.

## Suggested Fix

Handle `best_effort` timeout when `arrived` is empty by failing and cleaning up pending state (rather than skipping):

```python
if settings.policy == "best_effort":
    if len(pending.arrived) > 0:
        results.append(self._execute_merge(...))
    else:
        results.append(
            self._fail_pending(
                settings,
                key,
                step,
                failure_reason="best_effort_timeout_no_arrivals",
            )
        )
```

Also add a unit test for: `notify_branch_lost` before any arrival + timeout expiry.

## Impact

- Pending coalesce entries can accumulate unboundedly in long-running/streaming runs.
- Timeout semantics are violated for `best_effort`.
- Coalesce completion/failure counters and failure audit events are delayed until end-of-source flush (or never for never-ending sources), reducing operational/audit visibility.
