# Bug Report: Batching examples implement OutputPort with outdated emit signature

## Summary

- Example OutputPort implementations have `emit(self, token, result)` missing required `state_id` parameter.

## Severity

- Severity: trivial
- Priority: P3

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/plugins/batching/examples.py:40-46` - `emit(self, token, result)` missing state_id
- `src/elspeth/plugins/batching/ports.py:40` - Protocol requires `emit(self, token, result, state_id)`

## Proposed Fix

- Update examples to match protocol signature

## Acceptance Criteria

- Example code matches current protocol
