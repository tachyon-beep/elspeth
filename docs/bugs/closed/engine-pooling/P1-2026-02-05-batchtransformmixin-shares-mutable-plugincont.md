# Bug Report: BatchTransformMixin Shares Mutable PluginContext Across Worker Threads, Causing state_id/token Races Under Concurrent Submissions

## Summary

- BatchTransformMixin passes the shared `PluginContext` into worker threads and reads `ctx.state_id` at execution time; because the same `PluginContext` is reused and mutated per row/attempt by the executor, concurrent in-flight submissions can mis-attribute results and external-call audit metadata to the wrong `state_id`/`token`.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/plugins/batching/mixin.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a minimal transform using `BatchTransformMixin` with `max_pending=2` and `max_workers=1`; make its processor sleep before reading `ctx.state_id`/`ctx.token`.
2. Reuse a single `PluginContext` instance (as the orchestrator does) and submit two rows back-to-back: set `ctx.token`/`ctx.state_id` for row A, call `accept_row`, then immediately set them for row B and call `accept_row` again.
3. Observe the result emitted for row A uses row B’s `state_id`/token (or otherwise mismatches), breaking waiter routing and audit attribution.

## Expected Behavior

- Each worker thread uses the submission’s `state_id`/token snapshot, so results and external-call audit metadata map to the correct attempt and token.

## Actual Behavior

- Worker threads can read mutated `ctx.state_id`/`ctx.token` values from later submissions, causing mis-attribution and potentially delivering stale results to the wrong waiter.

## Evidence

- `BatchTransformMixin.accept_row()` submits the shared `ctx` into worker threads and does not snapshot `state_id`/token at submission time (`src/elspeth/plugins/batching/mixin.py:154-199`).
- `_process_and_complete()` reads `ctx.state_id` inside the worker thread, after potential concurrent mutation (`src/elspeth/plugins/batching/mixin.py:201-252`).
- The orchestrator creates a single `PluginContext` for the entire run and reuses it (`src/elspeth/engine/orchestrator/core.py:845-855`).
- The executor mutates `ctx.state_id` for each attempt (`src/elspeth/engine/executors.py:234-247`).
- The mixin explicitly documents that multiple submissions can be queued before the orchestrator waits (`src/elspeth/plugins/batching/mixin.py:45-51`).

## Impact

- User-facing impact: Wrong per-row results can be surfaced if a stale worker completes with a newer `state_id`/token.
- Data integrity / security impact: Audit trail and external-call records can be attributed to the wrong `state_id`/token, violating lineage integrity.
- Performance or cost impact: Retries may receive stale results or time out, causing unnecessary retries and extra external-call cost.

## Root Cause Hypothesis

- The mixin relies on a mutable, shared `PluginContext` and reads `ctx.state_id` in the worker thread instead of capturing immutable per-submission context data.

## Proposed Fix

- Code changes (modules/files): Capture `state_id` and `token` at submission time and pass them explicitly into `_process_and_complete`; consider creating a per-row `PluginContext` snapshot (e.g., `dataclasses.replace`) with pinned `token`, `state_id`, `contract`, and `node_id` so worker threads don’t observe later mutations. (`src/elspeth/plugins/batching/mixin.py`)
- Config or schema changes: N/A
- Tests to add/update: Add a concurrency test that submits two rows with a shared `PluginContext` and asserts each emitted result preserves its own `state_id`/token.
- Risks or migration steps: Ensure any snapshotting preserves references to shared integrations (`landscape`, `payload_store`, `telemetry_emit`) without copying heavy state.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/batching/mixin.py:45-51` (multiple submissions queued before orchestrator waits)
- Observed divergence: The mixin’s concurrency model assumes multiple in-flight submissions, but it uses a shared, mutable `PluginContext` that is mutated per attempt, making concurrent usage unsafe.
- Reason (if known): `PluginContext` is per-run and reused; the mixin does not snapshot submission context.
- Alignment plan or decision needed: Snapshot per-row context inside the mixin or require per-row contexts from the executor before enabling concurrent submissions.

## Acceptance Criteria

- Concurrent in-flight submissions using a shared `PluginContext` no longer mix `state_id`/token values.
- A unit test reproducing the race passes after the fix.
- Audit attribution (state_id/token) remains stable under concurrent batch submissions.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/test_batch_transform_mixin_context_race.py`
- New tests required: yes, concurrency race test for `BatchTransformMixin` context snapshotting.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Auditability Standard, Trust Model), `src/elspeth/plugins/batching/mixin.py` (concurrency model docstring)
