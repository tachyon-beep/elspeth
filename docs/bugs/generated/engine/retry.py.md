# Bug Report: RetryManager calls `on_retry` even when no retry will occur

## Summary

- `RetryManager.execute_with_retry()` invokes `on_retry` for retryable exceptions even on the final attempt, so callbacks can record retries that never happen.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/RC1-RC2-bridge @ 290716a2563735271d162f1fac7d40a7690e6ed6
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/retry.py`.
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate `RetryManager` with `max_attempts=1`.
2. Call `execute_with_retry()` with a retryable exception and an `on_retry` callback that records invocations.
3. Observe `on_retry` fires even though no further retry is scheduled.

## Expected Behavior

- `on_retry` should be called only when a subsequent retry attempt will actually execute.

## Actual Behavior

- `on_retry` fires for any retryable exception, including the final attempt that ends in `MaxRetriesExceeded`.

## Evidence

- `src/elspeth/engine/retry.py:101-121` calls `on_retry` when `is_retryable(e)` is true but does not check remaining attempts before invoking the callback.
- `src/elspeth/engine/retry.py:119` comment states “Only call on_retry for retryable errors that will be retried,” but the code does not enforce this.

## Impact

- User-facing impact: Retry hooks can record “scheduled retry” events that never occur.
- Data integrity / security impact: Audit/telemetry about retries can become misleading.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `on_retry` is invoked inside the attempt block before tenacity evaluates stop conditions, so it fires even when the next attempt will not run.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/retry.py`: only call `on_retry` when `attempt < self._config.max_attempts`, or move the callback to tenacity’s `before_sleep` hook.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test asserting `on_retry` is not called when `max_attempts=1`.
- Risks or migration steps:
  - Update any metrics/tests that currently count `on_retry` calls as “actual retries.”

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/engine/retry.py:119` (inline comment describing “will be retried”).
- Observed divergence: Callback fires even when no retry will happen.
- Reason (if known): Callback is triggered before stop condition evaluation.
- Alignment plan or decision needed: Clarify `on_retry` semantics and enforce them in the implementation.

## Acceptance Criteria

- `on_retry` is invoked only when a subsequent retry is actually scheduled.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_retry.py -k on_retry`
- New tests required: yes, verify no callback when `max_attempts=1`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
---
# Bug Report: `on_retry` attempt numbers are 1-based while audit uses 0-based

## Summary

- `RetryManager.execute_with_retry()` passes Tenacity’s 1-based `attempt_number` into `on_retry`, but engine audit attempts are 0-based, causing an off-by-one mismatch for any consumer that records attempt indices.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/RC1-RC2-bridge @ 290716a2563735271d162f1fac7d40a7690e6ed6
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/retry.py`.
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Provide an `on_retry` callback that records the attempt numbers.
2. Compare the recorded attempt numbers against node-state attempts (first attempt = 0).
3. Observe `on_retry` reports `1` for the first failure while audit uses `0`.

## Expected Behavior

- Retry callbacks should use the same 0-based attempt indexing as audit records.

## Actual Behavior

- `on_retry` receives Tenacity’s 1-based attempt numbers.

## Evidence

- `src/elspeth/engine/retry.py:114-121` sets `attempt` to `attempt_state.retry_state.attempt_number` and passes it directly to `on_retry`.
- `src/elspeth/core/landscape/recorder.py:992-1005` documents “attempt number (0 for first attempt).”
- `src/elspeth/engine/processor.py:1230-1239` uses a 0-based attempt counter when calling `execute_transform()`, indicating engine-wide 0-based indexing.

## Impact

- User-facing impact: Retry hooks may emit off-by-one attempt numbers.
- Data integrity / security impact: Any audit record keyed by attempt can be misaligned with node_state attempt numbering.
- Performance or cost impact: None.

## Root Cause Hypothesis

- RetryManager forwards Tenacity’s 1-based attempt counter without normalizing to the engine’s 0-based convention.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/retry.py`: normalize attempt before calling `on_retry` (e.g., `attempt - 1`).
  - Update any tests that currently assert 1-based values (e.g., `tests/engine/test_retry.py`).
- Config or schema changes: None.
- Tests to add/update:
  - Add/adjust test asserting `on_retry` receives 0-based attempt indices.
- Risks or migration steps:
  - If any external consumers already rely on 1-based values, update their expectations.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/core/landscape/recorder.py:1004` (0-based attempt convention).
- Observed divergence: Retry callback uses 1-based attempts.
- Reason (if known): Direct pass-through from Tenacity.
- Alignment plan or decision needed: Standardize attempt indexing across retry callbacks and audit records.

## Acceptance Criteria

- `on_retry` receives attempt indices that match audit node_state attempts (0-based).

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_retry.py -k records_attempts`
- New tests required: yes, update `test_records_attempts` to expect 0-based attempts.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
