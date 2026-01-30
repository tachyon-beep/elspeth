# Bug Report: Aggregation Flushes Do Not Emit TransformCompleted Telemetry

## Summary

- Batch-aware aggregation flushes never emit `TransformCompleted` telemetry events, creating a gap in row-level telemetry.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/engine/processor.py:480-519` - `execute_flush()` called with no telemetry emission
- Regular transforms DO call `_emit_transform_completed()` (lines 1684-1698)
- Audit trail (Landscape) is still correct; only telemetry gap

## Proposed Fix

- Call `_emit_transform_completed()` after `execute_flush()` returns

## Acceptance Criteria

- Aggregation flushes emit TransformCompleted telemetry events
