## Summary

`complete_run()` allows non-terminal status values (notably `RUNNING`) while setting `completed_at`, creating logically inconsistent run states.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_run_recording.py`
- Line(s): 112-139
- Function/Method: `complete_run`

## Evidence

`complete_run()` writes `status=status.value` and always sets `completed_at=timestamp` with no status guard (`_run_recording.py:131-138`).

`RunStatus` includes `RUNNING` (`src/elspeth/contracts/enums.py:17-20`), and recovery logic treats `RUNNING` as in-progress/non-resumable (`src/elspeth/core/checkpoint/recovery.py:100-101`).

So `complete_run(run_id, RunStatus.RUNNING)` is accepted and persists a contradictory state: “running” plus terminal timestamp.

## Root Cause Hypothesis

The method depends on caller discipline instead of enforcing run-lifecycle invariants at the write boundary.

## Suggested Fix

Validate `status` inside `complete_run()` against terminal states only (currently `COMPLETED`, `FAILED`, `INTERRUPTED`), and raise `ValueError`/`AuditIntegrityError` otherwise.

## Impact

Can produce contradictory audit records, confuse status-based tooling, and incorrectly block resume paths that key off `RUNNING`.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/_run_recording.py.md`
- Finding index in source report: 2
- Beads: pending
