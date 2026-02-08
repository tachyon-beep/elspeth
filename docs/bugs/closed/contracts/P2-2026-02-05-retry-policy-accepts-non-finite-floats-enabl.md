# Bug Report: Retry policy accepts non‑finite floats, enabling infinite backoff

## Summary

- `RuntimeRetryConfig.from_policy()` allows `inf`/`-inf` (and NaN) for float fields, which can propagate into Tenacity’s backoff configuration and lead to unbounded or undefined retry delays instead of failing fast.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: `1c70074e` on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit on `src/elspeth/contracts/config/runtime.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `RuntimeRetryConfig.from_policy({"base_delay": "inf", "max_delay": "inf", "jitter": "inf", "exponential_base": "inf"})`.
2. Create `RetryManager` with that config and execute any retryable operation.

## Expected Behavior

- Non‑finite numeric values (NaN/Infinity) should be rejected at config load time with a clear `ValueError`.

## Actual Behavior

- `_validate_float_field()` returns non‑finite floats without checking; `from_policy()` accepts them, and `RetryManager` passes them into Tenacity’s `wait_exponential_jitter`, enabling infinite or undefined backoff delays.

## Evidence

- `_validate_float_field()` returns floats without any `isfinite` validation. `src/elspeth/contracts/config/runtime.py:89-123`
- `from_policy()` uses `_validate_float_field()` for `base_delay`, `max_delay`, `jitter`, and `exponential_base` and then clamps only lower bounds, allowing `inf` to pass through. `src/elspeth/contracts/config/runtime.py:248-260`
- `RetryManager` directly forwards these values to Tenacity’s `wait_exponential_jitter`. `src/elspeth/engine/retry.py:117-124`

## Impact

- User-facing impact: Misconfigured retry policy can lead to hangs or effectively infinite wait times rather than fast failure with actionable errors.
- Data integrity / security impact: None directly, but it violates fail-fast configuration validation expectations.
- Performance or cost impact: Potential unbounded sleep/backoff, stalled pipelines, and increased operational cost.

## Root Cause Hypothesis

- `_validate_float_field()` does not enforce finiteness, so `inf`/`nan` values are treated as valid numeric inputs for retry policy fields.

## Proposed Fix

- Code changes (modules/files):
  - Add `math.isfinite()` checks in `_validate_float_field()` in `src/elspeth/contracts/config/runtime.py` and raise `ValueError` if the value is not finite.
  - Optionally catch `OverflowError` in `_validate_int_field()` when converting floats and re‑raise as `ValueError` with a clear message.
- Config or schema changes: None.
- Tests to add/update:
  - Add tests in `tests/contracts/config/test_runtime_retry.py` to assert `from_policy()` rejects `inf`, `-inf`, and `nan` for float fields.
- Risks or migration steps:
  - None. This only tightens validation for invalid inputs.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Retry policy validation does not reject non‑finite numeric inputs at a trust boundary.
- Reason (if known): Unknown
- Alignment plan or decision needed: Add explicit finiteness validation in `from_policy()` conversion helpers.

## Acceptance Criteria

- `RuntimeRetryConfig.from_policy()` raises `ValueError` for any `inf`, `-inf`, or `nan` value in float retry policy fields.
- Retry backoff values passed to Tenacity are always finite.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/config/test_runtime_retry.py -k "from_policy"`
- New tests required: yes, add explicit `inf`/`nan` rejection cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
