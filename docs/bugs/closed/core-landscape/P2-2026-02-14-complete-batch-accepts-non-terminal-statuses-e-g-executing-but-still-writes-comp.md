## Summary

`complete_batch()` accepts non-terminal statuses (e.g., `EXECUTING`) but still writes `completed_at`, creating invalid batch lifecycle states.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py`
- Line(s): 165, 179, 183
- Function/Method: `complete_batch`

## Evidence

Docstring says final status should be `COMPLETED` or `FAILED`:

- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py:165`

But implementation does not validate this and always sets `completed_at`:

- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py:179`
- `/home/john/elspeth-rapid/src/elspeth/core/landscape/_batch_recording.py:183`

Reproduction: calling `complete_batch("b1", BatchStatus.EXECUTING)` persisted `status="executing"` with `completed_at != None`.

## Root Cause Hypothesis

Method contract is documented but not enforced in code, so invalid status values are accepted and persisted.

## Suggested Fix

Add a strict guard at method start:

- If `status` is not `BatchStatus.COMPLETED` or `BatchStatus.FAILED`, raise `ValueError` (or `AuditIntegrityError`).
- Keep `update_batch_status()` as the path for non-terminal transitions.

## Impact

- Invalid lifecycle state (`executing` + terminal timestamp) can be recorded.
- Recovery and audit interpretation can become inconsistent.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/_batch_recording.py.md`
- Finding index in source report: 2
- Beads: pending
