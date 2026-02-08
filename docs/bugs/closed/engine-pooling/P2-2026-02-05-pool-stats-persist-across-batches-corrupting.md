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
