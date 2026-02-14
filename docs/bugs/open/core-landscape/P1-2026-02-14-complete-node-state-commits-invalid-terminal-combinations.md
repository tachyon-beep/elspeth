## Summary

`complete_node_state()` can write invalid terminal combinations to DB (for example `COMPLETED` without output hash), then fail later during read-path invariant checks.

## Severity

- Severity: major
- Priority: P1

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
