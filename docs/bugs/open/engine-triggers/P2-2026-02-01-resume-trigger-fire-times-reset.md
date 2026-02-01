# Bug Report: Trigger fire times reset on checkpoint restore

## Summary

- During checkpoint restore, `TriggerEvaluator.record_accept()` stamps `_count_fire_time` and `_condition_fire_time` with the current clock time.
- The restore path then rewinds `_first_accept_time` using `elapsed_age_seconds`, so timeout fire times are in the past while count/condition fire times are effectively "now".
- This can invert the "first to fire wins" ordering after resume and misreport which trigger fired first in the audit trail.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-01

## Current Behavior

- On resume, batches reconstructed from checkpoint treat count/condition triggers as firing at restore time rather than when they actually fired before the crash.
- When timeout also applies, `should_trigger()` may report `timeout` as the earliest trigger even if count/condition fired first pre-crash.

## Expected Behavior

- Resume should preserve trigger fire ordering from before the crash.
- `which_triggered()` should report the same trigger type that would have been recorded without the crash.

## Evidence

- `src/elspeth/engine/triggers.py:99-126` - `record_accept()` sets `_count_fire_time` / `_condition_fire_time` to `current_time`.
- `src/elspeth/engine/executors.py:1458-1475` - checkpoint restore loops `record_accept()` for buffered rows, then rewinds `_first_accept_time` using `elapsed_age_seconds`.
- `src/elspeth/engine/triggers.py:147-181` - timeout fire time is derived from `_first_accept_time`, so rewinding makes timeout appear earlier than count/condition after restore.

## Impact

- User-facing impact: audit trail can report the wrong trigger type for resumed batches.
- Data integrity: violates the documented "first to fire wins" semantics for combined triggers.

## Root Cause Hypothesis

- Trigger fire times are not persisted in checkpoint state.
- Restore reconstructs counts via `record_accept()` (which uses the current clock) and then adjusts only `_first_accept_time`, leaving fire times inconsistent with the restored timeline.

## Proposed Fix

- Persist trigger fire times (or their offsets from `_first_accept_time`) in checkpoint state.
- On restore, set `_count_fire_time` and `_condition_fire_time` based on the persisted values before evaluating triggers.
- Alternative: store which trigger fired first for the batch and restore `_last_triggered`, but this may not be sufficient when multiple triggers can fire before resume.

## Acceptance Criteria

- Resumed batches report the same `which_triggered()` value as uninterrupted execution.
- Checkpoint format includes the necessary fire-time metadata and restore logic uses it.
- Add a regression test that simulates count+timeout (or condition+timeout) with a crash and resume; verify trigger ordering is preserved.

## Verification (2026-02-01)

**Status: STILL VALID**

- Restore path calls `record_accept()` before rewinding `_first_accept_time`, and fire times are not persisted. (`src/elspeth/engine/executors.py:1458-1475`, `src/elspeth/engine/triggers.py:99-126`)
