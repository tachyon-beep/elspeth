# Bug Report: Config gate MissingEdgeError leaves node_state OPEN

## Summary

- When `_record_routing()` raises `MissingEdgeError` in config gate routing paths, node_state remains OPEN because there's no try/except around the call.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/engine/executors.py:843-879` - `_record_routing()` can raise `MissingEdgeError` (lines 858-859, 872-873)
- Config gate routing paths at lines 741-817 call `_record_routing()` after `begin_node_state()` without try/except
- If `MissingEdgeError` raised, node_state remains OPEN

## Impact

- User-facing impact: Dangling OPEN states in audit trail
- Data integrity: Terminal state requirement violated

## Proposed Fix

- Wrap `_record_routing()` calls in try/except, complete node_state as FAILED on error

## Acceptance Criteria

- MissingEdgeError results in FAILED node_state, not OPEN
