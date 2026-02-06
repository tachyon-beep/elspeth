# Bug Report: DROP Backpressure Drops Newest Event Instead of Oldest

## Summary

- In `drop` backpressure mode, the telemetry queue drops the newest event when full, but the docs specify that the oldest event should be dropped.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic telemetry events with `backpressure_mode=drop` and a small queue

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/telemetry/manager.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure telemetry with `backpressure_mode=drop` and force a small queue (e.g., set `INTERNAL_DEFAULTS["telemetry"]["queue_size"]=1`).
2. Use an exporter that is slow so the queue stays full.
3. Emit event A, then immediately emit event B.
4. Observe that event B is dropped while event A remains queued.

## Expected Behavior

- When the queue is full in `drop` mode, the oldest event should be evicted to make room for the newest event.

## Actual Behavior

- The newest event is dropped and the oldest remains in the queue.

## Evidence

- `src/elspeth/telemetry/manager.py:266-273` shows `put_nowait()` and, on `queue.Full`, increments drop metrics without evicting any queued item, resulting in tail-drop behavior.
- `docs/guides/telemetry.md:72-75` specifies `drop` mode should "Drop oldest events when buffer full."

## Impact

- User-facing impact: Dashboards and alerts can lag because the newest telemetry is discarded while stale events remain.
- Data integrity / security impact: Operational telemetry is skewed toward older data, reducing its usefulness for incident response.
- Performance or cost impact: None directly, but delayed observability can increase time-to-detect and time-to-resolve.

## Root Cause Hypothesis

- Drop mode uses `queue.put_nowait()` and treats `queue.Full` as a reason to drop the incoming event, but never evicts an existing queued item.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/telemetry/manager.py` drop-mode logic to evict the oldest queued event when full (e.g., `get_nowait()` + `task_done()`), increment `_events_dropped`, then enqueue the new event.
- Config or schema changes: None.
- Tests to add/update:
  - Unit test to verify that in `drop` mode with a full queue, the oldest event is dropped and the newest is queued.
- Risks or migration steps:
  - Ensure eviction is logged consistently and does not break queue accounting (`task_done()`).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/guides/telemetry.md:72-75`
- Observed divergence: Implementation drops the newest event instead of the oldest.
- Reason (if known): Likely default `queue.Full` handling without explicit eviction.
- Alignment plan or decision needed: Align implementation to documented policy by evicting the oldest event on overflow.

## Acceptance Criteria

- In `drop` mode with a full queue, the oldest event is evicted and the newest event is queued for export.
- Drop metrics reflect exactly one dropped event per eviction.
- Unit test validating drop-oldest behavior passes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/telemetry -k telemetry_manager`
- New tests required: yes, add a drop-mode eviction test for `TelemetryManager`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/guides/telemetry.md`
