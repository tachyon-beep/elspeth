## Summary

`complete_run()` can rewrite an already-terminal run, which lets later callers overwrite the original terminal status and completion timestamp in the audit record.

## Severity

- Severity: critical
- Priority: P0

## Location

- File: `/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py`
- Line(s): 148-170
- Function/Method: `complete_run`

## Evidence

`complete_run()` validates only that the *new* status is terminal, then unconditionally updates the row:

```python
if status not in _TERMINAL_RUN_STATUSES:
    raise AuditIntegrityError(...)

values = {
    "status": status,
    "completed_at": timestamp,
}
...
self._ops.execute_update(
    runs_table.update().where(runs_table.c.run_id == run_id).values(**values)
)
```

Source: [`run_lifecycle_repository.py:148`](\/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py#L148) and [`run_lifecycle_repository.py:165`](\/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py#L165)

There is no `WHERE` guard preventing updates when the run is already `COMPLETED`, `FAILED`, or `INTERRUPTED`. By contrast, the same repository explicitly treats completed runs as immutable in `update_run_status()`:

```python
.where(runs_table.c.status != RunStatus.COMPLETED.value)
...
raise AuditIntegrityError(
    f"Cannot transition run {run_id} from COMPLETED to {status.value!r}. "
    f"Completed runs are immutable."
)
```

Source: [`run_lifecycle_repository.py:354`](\/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py#L354)

The audit contract says the run row is the legal record, and terminal lifecycle data must not be rewritten after completion. The current implementation permits all of these silent mutations:

- `COMPLETED -> FAILED`
- `FAILED -> INTERRUPTED`
- `COMPLETED -> COMPLETED` with a new `completed_at`
- terminal status rewrite plus reproducibility grade rewrite

Because `runs_table` stores only one terminal state row per run, any later overwrite destroys the prior audit fact rather than appending a new history record. See schema: [`schema.py:38-67`](\/home/john/elspeth/src/elspeth/core/landscape/schema.py#L38)

## Root Cause Hypothesis

The method enforces “terminal-only input” but not “terminal-state immutability.” That conflates validation of the requested transition with validation of the current persisted state. The repository already encoded immutability thinking in `update_run_status()`, but the same invariant was not carried into `complete_run()`.

## Suggested Fix

Make `complete_run()` perform an atomic conditional update that only succeeds when the current row is non-terminal, or when explicitly allowing the resume path from `RUNNING` only. For example:

```python
result = conn.execute(
    runs_table.update()
    .where(runs_table.c.run_id == run_id)
    .where(runs_table.c.status.not_in([s.value for s in _TERMINAL_RUN_STATUSES]))
    .values(**values)
)
```

If `rowcount == 0`, fetch the current status and raise a specific `AuditIntegrityError` explaining that terminal runs are immutable.

Add an integration/unit test that calls `complete_run()` twice on the same run and asserts the second call raises without changing `status`, `completed_at`, or `reproducibility_grade`.

## Impact

A caller can silently falsify the run’s final outcome after the fact. That breaks the audit trail’s “source of truth” guarantee, destroys the original terminal timestamp, and can make downstream diagnostics, retention, and formal inquiry report the wrong final state for the run.
---
## Summary

`update_run_status()` allows `FAILED`/`INTERRUPTED` runs to resume to `RUNNING` without clearing `completed_at`, leaving runs simultaneously marked as running and completed.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py`
- Line(s): 331-367
- Function/Method: `update_run_status`

## Evidence

`complete_run()` always stamps terminal runs with `completed_at`:

```python
values = {
    "status": status,
    "completed_at": timestamp,
}
```

Source: [`run_lifecycle_repository.py:158-161`](\/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py#L158)

`update_run_status()` is the documented resume path for `FAILED`/`INTERRUPTED` runs:

```python
# FAILED and INTERRUPTED runs CAN be transitioned back
# to RUNNING during resume
...
.values(status=status)
```

Source: [`run_lifecycle_repository.py:348-357`](\/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py#L348)

But the method only updates `status`; it never clears `completed_at`. The repository’s own tests explicitly allow this transition and only assert the status changed:

```python
repo.complete_run("run-1", RunStatus.FAILED)
repo.update_run_status("run-1", RunStatus.RUNNING)
run = repo.get_run("run-1")
assert run.status == RunStatus.RUNNING
```

Source: [`tests/unit/core/landscape/test_run_lifecycle_repository.py:601-609`](\/home/john/elspeth/tests/unit/core/landscape/test_run_lifecycle_repository.py#L601)

Resume code in orchestrator uses exactly this path:

```python
recorder.update_run_status(run_id, RunStatus.RUNNING)
```

Source: [`engine/orchestrator/core.py:2592-2593`](\/home/john/elspeth/src/elspeth/engine/orchestrator/core.py#L2592)

Other code interprets `RUNNING` plus `completed_at is None` as the definition of an in-progress run:

```python
.where(runs_table.c.status == "running")
.where(runs_table.c.completed_at.is_(None))
```

Source: [`mcp/analyzers/diagnostics.py:73-76`](\/home/john/elspeth/src/elspeth/mcp/analyzers/diagnostics.py#L73)

So after resume, a run can be `RUNNING` but excluded from stuck-run detection and any other “active run” queries that rely on `completed_at` being null.

## Root Cause Hypothesis

The method was designed around status mutability for resume, but it treats `completed_at` as an independent field instead of part of the same lifecycle state machine. The repository therefore permits an impossible composite state: active status with terminal timestamp.

## Suggested Fix

When transitioning to a non-terminal status, clear terminal markers atomically:

```python
updates = {"status": status}
if status == RunStatus.RUNNING:
    updates["completed_at"] = None
```

Apply that in the same `UPDATE` used for resume transitions, and add a test asserting that `FAILED -> RUNNING` and `INTERRUPTED -> RUNNING` both produce `completed_at is None`.

## Impact

Resumed runs carry contradictory lifecycle facts in the audit database. Operational tooling can miss genuinely running resumed jobs, and auditors inspecting the run record can see a run represented as both completed and in progress at once. That weakens lifecycle traceability even though the fix belongs entirely in this repository.
