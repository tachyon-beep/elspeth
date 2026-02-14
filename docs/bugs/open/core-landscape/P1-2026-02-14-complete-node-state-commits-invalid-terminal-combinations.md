## Summary

`complete_node_state()` can write invalid terminal combinations to DB (for example `COMPLETED` without output hash), then fail later during read-path invariant checks.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — write-then-read pattern catches violations before transaction commits)

## Location

- File: `src/elspeth/core/landscape/_node_state_recording.py`
- Function/Method: `complete_node_state`

## Evidence

- Source report: `docs/bugs/generated/core/landscape/_node_state_recording.py.md`
- Recorder updates DB before enforcing full status/output invariants expected by repositories.

## Root Cause Hypothesis

Invariant enforcement is split between writer and reader in the wrong order (write first, validate later).

## Suggested Fix

Validate status-specific invariants in recorder before update/commit.

## Impact

Tier-1 audit state can be durably corrupted before crash, reducing trust in terminal-state integrity.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/landscape/_node_state_recording.py.md`
- Beads: elspeth-rapid-5rom

Triage: Downgraded P1→P2. Immediate read-back via get_node_state() catches invalid combinations. Defense-in-depth gap (pre-validation would be cleaner) but not active data corruption in practice.
