# Bug Report: Quarantined outcomes recorded before sink durability

## Summary

- `record_token_outcome(QUARANTINED)` is called immediately when a row fails, before the quarantine sink actually writes the data. If the sink write fails, the QUARANTINED outcome is recorded but no durable output exists.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31
- Related run/issue ID: N/A

## Evidence

- `src/elspeth/engine/orchestrator.py:1164-1170` - `record_token_outcome(QUARANTINED)` called immediately
- Line 1173 - Token added to `pending_tokens[quarantine_sink]` for later sink write
- Lines 1483-1504 - Sink writes happen later in separate loop
- If sink write fails, QUARANTINED outcome already recorded but no durable output

## Impact

- User-facing impact: Audit trail shows QUARANTINED but data may not exist in sink
- Data integrity / security impact: Terminal outcome without durability violates sink contract
- Performance or cost impact: None

## Root Cause Hypothesis

- Outcome recording happens before sink durability is confirmed, violating the "outcome = durable output" invariant.

## Proposed Fix

- Code changes:
  - Record QUARANTINED outcome AFTER sink write succeeds
  - Or: Record outcome with "pending" status, confirm after sink durability
- Tests to add/update:
  - Add test that mocks sink.write() to fail for quarantine, verify no QUARANTINED outcome

## Acceptance Criteria

- QUARANTINED outcome is only recorded after sink confirms durability
- Failed sink writes result in appropriate error handling, not false outcomes
