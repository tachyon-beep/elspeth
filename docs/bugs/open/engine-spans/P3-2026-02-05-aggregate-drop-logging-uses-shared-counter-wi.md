# Bug Report: Aggregate Drop Logging Uses Shared Counter Without Synchronization

## Summary

- `_last_logged_drop_count` is updated by both the export thread and the pipeline thread without consistent locking, creating a race that can lead to missed or duplicated aggregate drop logs.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: High-volume telemetry events with mixed drops (backpressure + exporter failures)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/telemetry/manager.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure telemetry with `backpressure_mode=drop` and induce exporter failures so both the export thread and pipeline thread increment `_events_dropped`.
2. Emit telemetry at high volume from multiple threads.
3. Observe aggregate drop logs occasionally duplicated or missing (non-deterministic), indicating inconsistent `_last_logged_drop_count` updates.

## Expected Behavior

- Aggregate drop logging should be consistent and monotonic, with `_last_logged_drop_count` updated atomically under a single lock.

## Actual Behavior

- `_last_logged_drop_count` is updated without holding `_dropped_lock` in the export thread, while the pipeline thread updates it under lock, creating a race.

## Evidence

- `src/elspeth/telemetry/manager.py:191-203` updates `_events_dropped` under lock, then reads and mutates `_last_logged_drop_count` without lock in the export thread.
- `src/elspeth/telemetry/manager.py:284-296` documents that `_log_drops_if_needed()` must be called while holding `_dropped_lock`, and it mutates `_last_logged_drop_count`.

## Impact

- User-facing impact: Aggregate drop logs can be noisy or missing, reducing observability signal quality.
- Data integrity / security impact: None.
- Performance or cost impact: Minor (log volume variance).

## Root Cause Hypothesis

- Shared counter `_last_logged_drop_count` is accessed across threads without consistent synchronization.

## Proposed Fix

- Code changes (modules/files):
  - In `src/elspeth/telemetry/manager.py`, wrap the aggregate logging check and `_last_logged_drop_count` updates inside `_dropped_lock` in `_dispatch_to_exporters()`, or refactor to reuse `_log_drops_if_needed()` under lock for both threads.
- Config or schema changes: None.
- Tests to add/update:
  - Add a concurrency test that stresses drop logging and asserts monotonic drop log thresholds (or uses deterministic hooks to verify lock usage).
- Risks or migration steps:
  - Ensure no deadlock by keeping the lock scope minimal and consistent across both threads.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/telemetry/manager.py:18-24`, `src/elspeth/telemetry/manager.py:284-287`
- Observed divergence: Shared drop counters are not fully protected by the documented lock discipline.
- Reason (if known): Aggregate logging was implemented separately in two threads without a shared helper.
- Alignment plan or decision needed: Centralize drop logging under `_dropped_lock` to restore the stated thread-safety guarantees.

## Acceptance Criteria

- `_last_logged_drop_count` is only read or written under `_dropped_lock`.
- Aggregate drop logs fire at consistent intervals under concurrent load.
- Concurrency test (or targeted unit test) passes without inconsistent logging.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/telemetry -k telemetry_manager`
- New tests required: yes, add a concurrent drop-logging consistency test or a lock-usage unit test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/telemetry/manager.py`
