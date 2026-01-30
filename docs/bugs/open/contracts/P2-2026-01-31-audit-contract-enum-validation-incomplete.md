# Bug Report: Audit contract enum validation is incomplete

## Summary

- `Call`, `RoutingEvent`, `Batch`, and `TokenOutcome` dataclasses lack `__post_init__` validation for enum fields, despite being marked as "strict contracts". Invalid string values could slip into audit objects.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/contracts/audit.py`:
  - `Run` (lines 60-63) and `Node` (lines 88-91) HAVE `__post_init__` validation
  - `Call` (lines 253-272): No `__post_init__`
  - `RoutingEvent` (lines 290-306): No `__post_init__`
  - `Batch` (lines 308-325): No `__post_init__`
  - `TokenOutcome` (lines 543-566): No `__post_init__`

## Impact

- User-facing impact: Invalid enum values could pass silently
- Data integrity: Violates Tier 1 "crash on invalid data"

## Proposed Fix

- Add `__post_init__` validation to all four classes checking enum field types

## Acceptance Criteria

- Invalid enum values in Call/RoutingEvent/Batch/TokenOutcome raise immediately
