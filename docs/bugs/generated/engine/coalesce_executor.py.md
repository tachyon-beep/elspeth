# Bug Report: require_all policy ignores timeout_seconds and never fails on timeout

## Summary

- `check_timeouts()` does not handle `policy="require_all"`, so configured timeouts are ignored and pending tokens never fail until end-of-source (or never, for streaming sources).

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 290716a2563735271d162f1fac7d40a7690e6ed6
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline with `coalesce` policy `require_all` and `timeout_seconds` set, with at least one branch missing.

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/coalesce_executor.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a coalesce with `policy: require_all` and `timeout_seconds: 5` (or any >0).
2. Run a pipeline where only some branches reach the coalesce for a row.
3. Wait past the timeout.

## Expected Behavior

- After timeout, the incomplete coalesce should fail: pending node states completed with `FAILED`, token outcomes recorded as `FAILED`, and the pending entry cleared.

## Actual Behavior

- Timeout is ignored for `require_all`; no failure is recorded and the pending coalesce is held until end-of-source flush (or indefinitely for streaming sources).

## Evidence

- `check_timeouts()` only handles `best_effort` and `quorum`, with no `require_all` failure path. `src/elspeth/engine/coalesce_executor.py:512`
- Quorum timeout failure handling exists, proving the timeout path is expected to record failures. `src/elspeth/engine/coalesce_executor.py:525`
- Contract says `require_all` should “fail if any missing after timeout.” `docs/contracts/plugin-protocol.md:1094`

## Impact

- User-facing impact: pipelines with `require_all` + timeout appear stuck at coalesce until end-of-source; timeouts don’t fire as configured.
- Data integrity / security impact: missing terminal outcomes during run violates the “no silent drops” auditability standard for long-running/streaming pipelines.
- Performance or cost impact: pending coalesce entries can accumulate indefinitely, increasing memory usage.

## Root Cause Hypothesis

- `check_timeouts()` omits a `require_all` branch, so timeout logic is never applied to this policy.

## Proposed Fix

- Code changes (modules/files):
  - Implement `require_all` timeout handling in `check_timeouts()` mirroring `flush_pending()`’s `incomplete_branches` failure path.
  - Record node_state failures and token outcomes when timeout expires and not all branches arrived.
- Config or schema changes: none.
- Tests to add/update:
  - Add a test that `require_all` with `timeout_seconds` fails after timeout and records outcomes.
- Risks or migration steps:
  - None; behavior aligns with documented contract.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/contracts/plugin-protocol.md:1094`
- Observed divergence: `require_all` does not fail after timeout in runtime behavior.
- Reason (if known): missing branch in `check_timeouts()` implementation.
- Alignment plan or decision needed: implement timeout failure path for `require_all`.

## Acceptance Criteria

- For `policy="require_all"` with `timeout_seconds`, timed-out pending coalesces are failed with recorded node_state errors and `FAILED` token outcomes.
- Pending entries are cleared and marked completed after timeout failure.
- New test proves the timeout path fires and persists audit records.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_coalesce_executor.py -k require_all_timeout`
- New tests required: yes (require_all timeout failure + audit recording)

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/contracts/plugin-protocol.md`
