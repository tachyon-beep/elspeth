# Bug Report: Quarantined rows silently dropped when quarantine destination is invalid

## Summary

- When `quarantine_sink` is invalid (typo, missing config), the code silently skips all handling - no token created, no outcome recorded, row is lost.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/engine/orchestrator.py:1140` - `if quarantine_sink and quarantine_sink in config.sinks:` is a conditional guard
- If condition fails, code skips silently
- Violates "no silent drops" (CLAUDE.md:637-647)

## Impact

- User-facing impact: Rows disappear without trace on config error
- Data integrity: Silent data loss

## Proposed Fix

- Crash per "system-owned plugin bugs must crash" if quarantine_sink is configured but invalid

## Acceptance Criteria

- Invalid quarantine_sink causes immediate failure, not silent skip
