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
