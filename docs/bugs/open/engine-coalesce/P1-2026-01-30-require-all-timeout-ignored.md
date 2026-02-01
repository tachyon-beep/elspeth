# Bug Report: require_all coalesce ignores timeout_seconds and never resolves until end-of-source

## Summary

- `CoalesceExecutor.check_timeouts()` never handles `policy="require_all"`, so `timeout_seconds` is silently ignored and pending coalesces persist indefinitely until `flush_pending()`.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Fork/coalesce pipeline with `policy=require_all` and `timeout_seconds` set; one branch delayed or missing

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit of `coalesce_executor.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a coalesce with `policy: require_all` and a small `timeout_seconds` (e.g., 1s).
2. Run a fork where only one branch reaches the coalesce (the other branch fails or stalls).
3. Wait beyond `timeout_seconds` and inspect audit/pipeline state.

## Expected Behavior

- After `timeout_seconds`, the pending coalesce should resolve as a failure (e.g., `incomplete_branches`) with node states and token outcomes recorded, and the pending entry cleared.

## Actual Behavior

- `check_timeouts()` never triggers for `require_all`, so the pending entry persists with no failure outcome until end-of-source (or indefinitely for streaming sources).

## Evidence

- `src/elspeth/engine/coalesce_executor.py:469-582` — `check_timeouts()` handles `best_effort` and `quorum` only; there is no `require_all` branch.
- `src/elspeth/engine/coalesce_executor.py:584-719` — `require_all` failure handling exists only in `flush_pending()` (end-of-source).
- `docs/reference/configuration.md:420` — `timeout_seconds` described as “Max wait time” without policy restriction.
- `src/elspeth/core/config.py:375-400` — `timeout_seconds` is allowed for `require_all` (no validator rejecting it).

## Impact

- User-facing impact: Pipelines with `require_all` + timeout can hang indefinitely when a branch never arrives (especially streaming sources).
- Data integrity / security impact: Tokens remain in non-terminal state; audit trail lacks failure resolution until end-of-source, violating “every row reaches a terminal state.”
- Performance or cost impact: Pending entries accumulate, increasing memory usage and potentially stalling progress.

## Root Cause Hypothesis

- `check_timeouts()` omits handling for `policy="require_all"`, so timeouts configured for require_all are ignored.

## Proposed Fix

- Code changes (modules/files):
  - Add `require_all` timeout handling in `src/elspeth/engine/coalesce_executor.py` `check_timeouts()` mirroring the `flush_pending()` failure path (`incomplete_branches`), including node state completion and `record_token_outcome()` for arrived tokens.
- Config or schema changes: None required if runtime behavior is added.
- Tests to add/update:
  - Add unit test for `require_all` timeout in `tests/engine/test_coalesce_executor.py` to assert failure is recorded and pending cleared.
  - Add integration test for streaming/long-running scenario to ensure timeout fires without end-of-source.
- Risks or migration steps:
  - Existing configs relying on “wait forever” behavior will now fail at timeout (expected per `timeout_seconds`).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/reference/configuration.md:417` (“timeout_seconds: Max wait time”)
- Observed divergence: `timeout_seconds` has no effect for `require_all` policy during runtime timeouts.
- Reason (if known): Missing branch in `check_timeouts()` for `require_all`.
- Alignment plan or decision needed: Define `require_all` timeout semantics explicitly (fail with `incomplete_branches`) and enforce in executor.

## Acceptance Criteria

- A `require_all` coalesce with `timeout_seconds` reliably resolves to failure after timeout without waiting for end-of-source.
- Audit trail shows failed node states and token outcomes for arrived branches.
- No pending coalesce remains after timeout expiration.

## Verification (2026-02-01)

**Status: STILL VALID**

- `check_timeouts()` still lacks `require_all` handling; only `flush_pending()` produces the `require_all` failure path. (`src/elspeth/engine/coalesce_executor.py:469-719`)

## Tests

- Suggested tests to run: `pytest tests/engine/test_coalesce_executor.py -k require_all_timeout`
- New tests required: yes, timeout failure recording for `require_all`

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/reference/configuration.md`
