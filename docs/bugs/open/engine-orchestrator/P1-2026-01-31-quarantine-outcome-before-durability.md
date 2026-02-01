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

- `src/elspeth/engine/orchestrator.py:1194-1229` - `record_token_outcome(QUARANTINED)` is called immediately after creating the quarantine token.
- `src/elspeth/engine/orchestrator.py:1231-1232` - token is enqueued into `pending_tokens[quarantine_sink]` for later sink write.
- `src/elspeth/engine/orchestrator.py:1586-1623` - sink writes occur later, outside the source loop, via `SinkExecutor.write()`.
- If the quarantine sink write fails, the QUARANTINED outcome has already been recorded without durable output.

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

## Verification (2026-02-01)

**Status: STILL VALID**

- QUARANTINED outcomes are still recorded before quarantine sink durability; sink writes happen later via `pending_tokens` flush. (`src/elspeth/engine/orchestrator.py:1194-1232`, `src/elspeth/engine/orchestrator.py:1586-1623`)
