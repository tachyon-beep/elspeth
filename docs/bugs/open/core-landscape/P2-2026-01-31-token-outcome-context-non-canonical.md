# Bug Report: Token Outcome Context Stored with json.dumps (Non-Canonical JSON)

## Summary

- `record_token_outcome` serializes `context` with `json.dumps`, allowing NaN/Infinity and bypassing canonical JSON enforcement.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/landscape/recorder.py:2433` - `context_json = json.dumps(context)`
- Uses `json.dumps` instead of `canonical_json`, allowing NaN/Infinity
- Violates CLAUDE.md canonical JSON policy

## Impact

- User-facing impact: Audit exports may contain invalid JSON
- Data integrity: Inconsistent serialization across audit trail

## Proposed Fix

- Replace `json.dumps(context)` with `canonical_json(context)`

## Acceptance Criteria

- `record_token_outcome` uses canonical JSON and rejects NaN/Infinity

## Verification (2026-02-01)

**Status: STILL VALID**

- `record_token_outcome()` still serializes `context` via plain `json.dumps()`. (`src/elspeth/core/landscape/recorder.py:2433`)
