# Bug Report: Aggregation Flushes Do Not Emit TransformCompleted Telemetry

## Summary

- Batch-aware aggregation flushes (count/timeout/end-of-source) never emit `TransformCompleted` telemetry events, so row-level telemetry is missing for aggregation transforms.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline with a batch-aware transform configured as an aggregation and telemetry enabled (granularity=rows or full)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/engine/processor.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Enable telemetry with `granularity: rows` (or `full`) in settings.
2. Configure a pipeline with a batch-aware transform (`is_batch_aware=True`) and aggregation settings so a flush occurs (count/timeout/end-of-source).
3. Run the pipeline and inspect emitted telemetry events.

## Expected Behavior

- A `TransformCompleted` event is emitted for each aggregation flush (success or error), consistent with row-level telemetry behavior for regular transforms.

## Actual Behavior

- No `TransformCompleted` event is emitted for aggregation flushes; only regular (non-aggregation) transforms produce `TransformCompleted` telemetry.

## Evidence

- Aggregation flush paths call `execute_flush()` but never call `_emit_transform_completed()`:
  - `src/elspeth/engine/processor.py:482-489` (handle_timeout_flush execute_flush)
  - `src/elspeth/engine/processor.py:786-793` (_process_batch_aggregation_node execute_flush)
- `_emit_transform_completed()` is only invoked on the regular transform path:
  - `src/elspeth/engine/processor.py:1684-1698`

## Impact

- User-facing impact: telemetry dashboards miss aggregation transform completions, hiding batch latency and failure signals.
- Data integrity / security impact: None (Landscape audit trail still records node_states/batches).
- Performance or cost impact: Operational blind spot can delay detection of slow or failing aggregations.

## Root Cause Hypothesis

- Aggregation flush paths bypass the regular transform execution flow where `_emit_transform_completed()` is called, so telemetry emission is skipped entirely.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/processor.py`: After `execute_flush()` returns in both `_process_batch_aggregation_node()` and `handle_timeout_flush()`, call `_emit_transform_completed()` with the returned `TransformResult` (for both success and error statuses) after audit recording.
- Config or schema changes: None.
- Tests to add/update:
  - Add an integration test that runs a batch aggregation with telemetry enabled and asserts a `TransformCompleted` event for the aggregation node (count trigger).
  - Add a timeout/end-of-source flush telemetry test to ensure the same event is emitted in those paths.
- Risks or migration steps:
  - Low risk; telemetry-only change.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/guides/telemetry.md` (row granularity includes `TransformCompleted`)
- Observed divergence: aggregation transforms do not emit `TransformCompleted` telemetry events.
- Reason (if known): telemetry emission is only wired in the non-aggregation transform path.
- Alignment plan or decision needed: emit `TransformCompleted` in aggregation flush paths after `execute_flush()` completes.

## Acceptance Criteria

- Aggregation flushes (count/timeout/end-of-source) emit `TransformCompleted` telemetry events with correct node_id, status, duration, and hashes.
- Row-level telemetry includes aggregation transforms alongside regular transforms.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/ tests/telemetry/`
- New tests required: yes, aggregation telemetry emission coverage for count and timeout flushes.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/guides/telemetry.md`
