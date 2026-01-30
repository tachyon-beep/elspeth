# Bug Report: NoOpLimiter.acquire() signature does not match RateLimiter.acquire()

## Summary

- NoOpLimiter lacks the `timeout` parameter present in RateLimiter.acquire(), causing a TypeError when rate limiting is disabled and callers pass `timeout`.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/core/rate_limit/registry.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a disabled rate limit config (e.g., `RuntimeRateLimitConfig.from_settings(RateLimitSettings(enabled=False))`) and a `RateLimitRegistry`.
2. Call `registry.get_limiter("any").acquire(timeout=1.0)`.

## Expected Behavior

- The no-op limiter should accept the same parameters as RateLimiter and return immediately without error.

## Actual Behavior

- `TypeError: NoOpLimiter.acquire() got an unexpected keyword argument 'timeout'`.

## Evidence

- `NoOpLimiter.acquire` lacks a `timeout` parameter in `src/elspeth/core/rate_limit/registry.py:22`.
- `RateLimiter.acquire` defines `timeout: float | None = None` in `src/elspeth/core/rate_limit/limiter.py:192`.

## Impact

- User-facing impact: Pipeline code that passes `timeout` when rate limiting is disabled will crash unexpectedly.
- Data integrity / security impact: None (fail-fast with exception).
- Performance or cost impact: None.

## Root Cause Hypothesis

- NoOpLimiter was intended to “provide the same interface as RateLimiter,” but its `acquire()` signature was not kept in sync with RateLimiter’s optional `timeout` argument.

## Proposed Fix

- Code changes (modules/files):
  - Update `NoOpLimiter.acquire` in `src/elspeth/core/rate_limit/registry.py` to accept `timeout: float | None = None` and ignore it.
- Config or schema changes: None.
- Tests to add/update:
  - Add a NoOpLimiter test that calls `acquire(timeout=...)` and asserts no error (e.g., in `tests/core/rate_limit/test_registry.py` or `tests/core/rate_limit/test_limiter.py`).
- Risks or migration steps:
  - Low risk; signature alignment only.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/core/rate_limit/registry.py:16-19` (“Provides the same interface as RateLimiter”)
- Observed divergence: NoOpLimiter.acquire signature does not match RateLimiter.acquire.
- Reason (if known): Unknown
- Alignment plan or decision needed: Update NoOpLimiter.acquire signature and add a test to prevent drift.

## Acceptance Criteria

- `NoOpLimiter.acquire(timeout=1.0)` does not raise.
- A test explicitly covers the timeout parameter on NoOpLimiter.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/rate_limit/test_registry.py`
- New tests required: yes, add coverage for `NoOpLimiter.acquire(timeout=...)`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/core/rate_limit/registry.py`
