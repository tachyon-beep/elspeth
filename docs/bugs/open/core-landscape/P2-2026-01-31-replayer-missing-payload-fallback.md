# Bug Report: Replay ignores missing payloads for error calls with recorded responses

## Summary

- Replayer uses `response_data = {}` fallback for error calls with missing payloads, but ERROR calls can have `response_ref` set (HTTP errors return bodies). If purged, replay substitutes empty dict.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/plugins/clients/replayer.py:200-220`:
  - Lines 209-216: Missing payload check only fails if `not was_error`
  - Lines 219-220: For error calls, `response_data = {}` used as fallback
- Silent data loss violates audit principles

## Impact

- User-facing impact: Replay produces different results if error response purged
- Data integrity: Replay not faithful to original

## Proposed Fix

- Fail replay if response_ref exists but payload missing, regardless of error status

## Acceptance Criteria

- Missing payloads always cause replay failure, not silent substitution
