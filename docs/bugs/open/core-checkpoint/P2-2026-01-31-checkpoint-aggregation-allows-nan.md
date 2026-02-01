# Bug Report: Checkpoint aggregation_state_json allows NaN/Infinity

## Summary

- Checkpoint uses `json.dumps(aggregation_state)` which allows NaN/Infinity, violating canonical JSON policy.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/checkpoint/manager.py:82` - `agg_json = json.dumps(aggregation_state)` (no `allow_nan=False` / canonicalization).
- Uses default `json.dumps()` which allows NaN/Infinity
- CLAUDE.md requires canonical JSON

## Impact

- User-facing impact: Checkpoints could contain non-canonical JSON
- Data integrity: Resume may fail on reload if parsing differs

## Proposed Fix

- Use `canonical_json(aggregation_state)` instead of `json.dumps()`

## Acceptance Criteria

- Checkpoints use canonical JSON and reject NaN/Infinity

## Verification (2026-02-01)

**Status: STILL VALID**

- Checkpoint aggregation state is still serialized with plain `json.dumps()` (NaN/Infinity allowed). (`src/elspeth/core/checkpoint/manager.py:82`)
