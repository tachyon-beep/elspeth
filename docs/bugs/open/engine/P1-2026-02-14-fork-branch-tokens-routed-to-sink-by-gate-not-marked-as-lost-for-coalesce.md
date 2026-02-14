## Summary

Fork-branch tokens routed to a sink by a gate are not marked as lost for coalesce, so sibling branches can remain held until timeout/end-of-source.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/engine/processor.py
- Line(s): 1766-1777, 1621-1674, 1351-1439
- Function/Method: `_process_single_token`, `_notify_coalesce_of_lost_branch`

## Evidence

In `_process_single_token`, gate sink routing exits immediately:

```python
if outcome.sink_name is not None:
    return (
        RowResult(... outcome=RowOutcome.ROUTED, sink_name=outcome.sink_name),
        child_items,
    )
```

(`/home/john/elspeth-rapid/src/elspeth/engine/processor.py:1766-1777`)

But transform early-exit paths explicitly notify coalesce of lost branches before returning:

- max retries path (`/home/john/elspeth-rapid/src/elspeth/engine/processor.py:1621-1625`)
- quarantined path (`/home/john/elspeth-rapid/src/elspeth/engine/processor.py:1651-1655`)
- error-routed transform path (`/home/john/elspeth-rapid/src/elspeth/engine/processor.py:1670-1674`)

`CoalesceExecutor.notify_branch_lost()` exists for exactly this case ("diverted ... before reaching coalesce"): `/home/john/elspeth-rapid/src/elspeth/engine/coalesce_executor.py:924-928`.

So gate-routed branch loss is currently unreported to coalesce state.

## Root Cause Hypothesis

Branch-loss handling was implemented for transform failure exits, but the analogous gate sink-routing exit path omitted `_notify_coalesce_of_lost_branch(...)`.

## Suggested Fix

In the `outcome.sink_name is not None` branch of `_process_single_token`, call `_notify_coalesce_of_lost_branch(...)` before returning, mirroring transform error branches. Merge returned sibling results into the return payload the same way as transform error handling.

## Impact

- Coalesce policies (`require_all`/`quorum`) can hold sibling tokens longer than necessary.
- In streaming/long-running runs, this creates avoidable memory growth and delayed coalesce resolution.
- Operational behavior diverges by failure mode (transform error vs gate route), reducing predictability of fork/join semantics.
