# Bug Report: Sink flush failures leave sink node_states OPEN

## Summary

- When `sink.flush()` raises an exception, sink node_states are left in OPEN status instead of being completed with FAILED, violating the terminal state requirement.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31
- Related run/issue ID: N/A

## Evidence

- `src/elspeth/engine/executors.py:1703-1705` - `sink.flush()` is called with no exception handling
- Lines 1684-1701 handle `sink.write()` exceptions and complete node_states with FAILED
- If `sink.flush()` fails, exception bubbles up without completing node_states
- Violates CLAUDE.md:637-647 "every row reaches exactly one terminal state"

## Impact

- User-facing impact: Runs can crash with dangling OPEN node_states
- Data integrity / security impact: Audit trail has incomplete state transitions
- Performance or cost impact: May complicate resume and debugging

## Root Cause Hypothesis

- Exception handling was added for `sink.write()` but not for `sink.flush()`.

## Proposed Fix

- Code changes:
  - Wrap `sink.flush()` in try/except similar to `sink.write()`
  - On flush failure, complete all pending node_states with FAILED status
- Tests to add/update:
  - Add test that mocks `sink.flush()` to raise, verify node_states are completed as FAILED

## Acceptance Criteria

- Sink flush failures result in FAILED node_states, not OPEN
- No dangling OPEN states after sink exceptions
