# Bug Report: Pool Stats Persist Across Batches, Corrupting Per-Row Audit Context

## Summary

- AIMD throttle counters (`capacity_retries`, `successes`, `total_throttle_time_ms`, `peak_delay_ms`) are never reset per batch, but `get_stats()` is used to populate per-row `context_after_json`. This causes later rows to inherit cumulative stats from prior rows, violating audit accuracy for per-row execution metadata.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b / RC2.3-pipeline-row
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic pooled batches

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of `src/elspeth/plugins/pooling/executor.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `PooledExecutor(PoolConfig(pool_size=1))`.
2. Run `execute_batch()` with a `process_fn` that raises `CapacityError` once, then succeeds.
3. Call `get_stats()` and observe `pool_stats.capacity_retries == 1`.
4. Run a second `execute_batch()` where `process_fn` succeeds immediately.
5. Call `get_stats()` again and observe `pool_stats.capacity_retries` still equals 1.

## Expected Behavior

- `pool_stats` in `context_after_json` reflect only the current batch/row execution; counters reset between batches.

## Actual Behavior

- `pool_stats` are cumulative across batches, so per-row audit context misattributes retries and throttle time from previous rows.

## Evidence

- `src/elspeth/plugins/pooling/executor.py:144-149` resets only `_max_concurrent` and `_dispatch_delay_at_completion_ms`, not AIMD counters.
- `src/elspeth/plugins/pooling/executor.py:178-194` returns `self._throttle.get_stats()` (cumulative).
- `src/elspeth/plugins/llm/azure_multi_query.py:783-813` uses `executor.get_stats()` to populate per-row `context_after`.
- `docs/plans/completed/2026-01-20-pooled-llm-queries-design.md:152-165` defines `pool_stats` inside `node_state.context_after_json` (per execution), while `docs/plans/completed/2026-01-20-pooled-llm-queries-design.md:177-182` separates run-level totals.

## Impact

- User-facing impact: Audit metadata for a row can claim capacity retries that never happened for that row.
- Data integrity / security impact: Audit trail accuracy is compromised for pooled executions.
- Performance or cost impact: None directly, but misleading stats hinder troubleshooting.

## Root Cause Hypothesis

- `PooledExecutor` never calls `AIMDThrottle.reset_stats()` per batch, so `get_stats()` reflects executor lifetime totals rather than per-batch metrics.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/plugins/pooling/executor.py` call `self._throttle.reset_stats()` inside `_reset_batch_stats()`, and keep `current_delay_ms` intact.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/plugins/llm/test_pooled_executor.py` asserting `capacity_retries` resets between batches.
- Risks or migration steps: If run-level totals are needed, aggregate them at a higher layer (e.g., run summary), not via per-row context.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/completed/2026-01-20-pooled-llm-queries-design.md:152-165` and `:177-182`
- Observed divergence: Per-row `pool_stats` are cumulative rather than per execution.
- Reason (if known): Throttle stats reset not wired into batch lifecycle.
- Alignment plan or decision needed: Reset per-batch stats and move run-level totals to a separate aggregation path.

## Acceptance Criteria

- `capacity_retries`, `successes`, `total_throttle_time_ms`, `peak_delay_ms` in `get_stats()` reset between batches.
- Per-row `context_after_json.pool_stats` reflects only the current batch execution.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/llm/test_pooled_executor.py -k stats`
- New tests required: yes, reset-between-batches for throttle stats

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-01-20-pooled-llm-queries-design.md`
---
# Bug Report: Global Dispatch Gate Ignores AIMD `current_delay`, Violating Specified Pacing

## Summary

- `_wait_for_dispatch_gate()` enforces only `min_dispatch_delay_ms`, not the AIMD `current_delay_ms`. After capacity errors increase `current_delay_ms`, other workers still dispatch at the minimum delay, so global pacing never reflects AIMD backoff.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b / RC2.3-pipeline-row
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic pooled batches

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of `src/elspeth/plugins/pooling/executor.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `PoolConfig(pool_size=4, min_dispatch_delay_ms=0, recovery_step_ms=50)`.
2. Run `execute_batch()` with a `process_fn` that raises `CapacityError` on the first attempt, then succeeds.
3. Record the start times of each retry attempt across workers.
4. Observe that retries still start in near-simultaneous bursts because the dispatch gate uses only `min_dispatch_delay_ms`.

## Expected Behavior

- The dispatcher enforces `current_delay_ms` between consecutive dispatches across all workers, per design.

## Actual Behavior

- The dispatcher enforces only `min_dispatch_delay_ms`, so AIMD backoff does not globally pace dispatches.

## Evidence

- `src/elspeth/plugins/pooling/executor.py:306-323` uses `self._config.min_dispatch_delay_ms` in `_wait_for_dispatch_gate()` and explicitly states it does not enforce AIMD delay.
- `src/elspeth/plugins/pooling/executor.py:399-409` calls `_wait_for_dispatch_gate()` before dispatch.
- `docs/plans/completed/2026-01-20-pooled-llm-queries-design.md:83-85` specifies “Dispatcher waits `current_delay` between dispatches (AIMD-controlled).”

## Impact

- User-facing impact: Increased burst traffic and higher likelihood of repeated 429/503 errors.
- Data integrity / security impact: None directly.
- Performance or cost impact: More retries and longer end-to-end latency under rate limits.

## Root Cause Hypothesis

- The global dispatch gate is wired to `min_dispatch_delay_ms` only, so AIMD `current_delay_ms` never governs global pacing.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/plugins/pooling/executor.py` use `self._throttle.current_delay_ms` (already min/max bounded) for gating, and recompute it inside the loop to reflect concurrent updates.
- Config or schema changes: None.
- Tests to add/update: Add a test ensuring dispatch start times are globally spaced by `current_delay_ms` after a capacity error.
- Risks or migration steps: Ensure the gate doesn’t hold locks during sleep and avoid deadlocks.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/completed/2026-01-20-pooled-llm-queries-design.md:83-85`
- Observed divergence: Dispatcher enforces only `min_dispatch_delay_ms` instead of AIMD `current_delay_ms`.
- Reason (if known): Implementation intentionally split “global pacing” and “per-worker backoff.”
- Alignment plan or decision needed: Align dispatcher pacing with AIMD `current_delay_ms` as specified.

## Acceptance Criteria

- Dispatch timestamps across workers are spaced by at least the AIMD `current_delay_ms` after capacity errors.
- New pacing test passes alongside existing pooling tests.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/llm/test_pooled_executor.py -k dispatch`
- New tests required: yes, global pacing test

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-01-20-pooled-llm-queries-design.md`
