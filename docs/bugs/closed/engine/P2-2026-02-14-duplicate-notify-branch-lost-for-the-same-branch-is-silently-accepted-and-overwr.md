## Summary

Duplicate `notify_branch_lost` for the same branch is silently accepted and overwrites the original loss reason instead of surfacing an invariant violation.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P2 — duplicate loss notifications are unreachable through normal code paths; each token exits through exactly one early-exit path; hardening measure only)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/engine/coalesce_executor.py
- Line(s): 986-988
- Function/Method: `notify_branch_lost`

## Evidence

Current logic only rejects “branch already arrived”, but not “branch already lost”:

```python
# coalesce_executor.py:978-988
if lost_branch in pending.arrived:
    raise ValueError(...)
pending.lost_branches[lost_branch] = reason
return self._evaluate_after_loss(settings, key, step)
```

Observed behavior (executed in repo): calling `notify_branch_lost(..., "a", "err1")` then again `notify_branch_lost(..., "a", "err2")` returns `None` both times and mutates `lost_branches` from `{'a': 'err1'}` to `{'a': 'err2'}`.

## Root Cause Hypothesis

The method validates arrival/loss contradiction but misses duplicate-loss detection. This allows internal duplicate event bugs (retry/resume/processor signaling issues) to be hidden.

## Suggested Fix

Add explicit duplicate-loss guard before mutation:

```python
if lost_branch in pending.lost_branches:
    raise ValueError(
        f"Branch '{lost_branch}' already marked lost at coalesce '{coalesce_name}'. "
        "Duplicate loss notification indicates a processor bug."
    )
```

## Impact

- Overwrites coalesce loss causality data in-memory.
- Masks upstream control-flow bugs instead of crashing fast.
- Weakens audit clarity when branch-loss reasons differ across duplicate signals.

## Triage

- Status: open
- Source report: `docs/bugs/generated/engine/coalesce_executor.py.md`
- Finding index in source report: 2
- Beads: pending
