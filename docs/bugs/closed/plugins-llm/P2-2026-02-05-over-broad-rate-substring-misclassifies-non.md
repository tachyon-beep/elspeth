# Bug Report: Over-broad “rate” substring misclassifies non‑rate errors as retryable

**Status: CLOSED (FIXED)**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- `_is_retryable_error()` treats any error message containing the substring `"rate"` as a rate‑limit, which misclassifies non‑rate errors (e.g., invalid `temperature`) as retryable and raises `RateLimitError`.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row (1c70074ef3b71e4fe85d4f926e52afeca50197ab)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/clients/llm.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `AuditedLLMClient.chat_completion()` with an invalid `temperature` (e.g., `temperature=5.0`) so the provider returns an error message containing “temperature”.
2. Observe the raised exception type and retry classification.

## Expected Behavior

- Non‑rate‑limit configuration errors should be classified as non‑retryable (`LLMClientError` with `retryable=False`) and should not be raised as `RateLimitError`.

## Actual Behavior

- Errors whose message contains `"rate"` as a substring (e.g., `"temperature"`) are treated as retryable and raised as `RateLimitError`, triggering unnecessary retries.

## Evidence

- Broad substring match: `src/elspeth/plugins/clients/llm.py:148`
- Rate‑limit classification branch: `src/elspeth/plugins/clients/llm.py:151`
- Corresponding raise path: `src/elspeth/plugins/clients/llm.py:441`

## Impact

- User-facing impact: Permanent configuration errors can be retried repeatedly, delaying failure visibility.
- Data integrity / security impact: Misclassified errors are recorded as retryable rate‑limits, reducing audit accuracy.
- Performance or cost impact: Unnecessary retries waste LLM quota and increase latency.

## Root Cause Hypothesis

- `_is_retryable_error()` uses an over‑broad substring check (`"rate" in error_str`), which matches unrelated words like “temperature”.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/clients/llm.py`: Replace `"rate" in error_str` with a stricter pattern such as `"rate limit"`, `"rate_limit"`, or HTTP status‑code parsing; avoid generic substring matching.
- Config or schema changes: None
- Tests to add/update:
  - Add unit tests for `_is_retryable_error()` covering “temperature” and other non‑rate error messages to ensure non‑retryable classification.
- Risks or migration steps:
  - Low risk; behavior changes only for misclassified errors.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- Errors containing “temperature” (or similar non‑rate terms) are not classified as rate‑limit and do not raise `RateLimitError`.
- `_is_retryable_error()` only returns `True` for explicit rate‑limit indicators (e.g., `429`, “rate limit”).

## Tests

- Suggested tests to run: `Unknown`
- New tests required: yes, `_is_retryable_error()` classification tests

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A


## Resolution (2026-02-12)

- Status: CLOSED (FIXED)
- Fix summary: Replaced broad substring matching with canonical error classification and explicit rate-limit indicators.
- Code updated:
  - `src/elspeth/plugins/clients/llm.py`
- Tests added/updated:
  - `tests/unit/plugins/clients/test_llm_error_classification.py`
  - `tests/unit/plugins/clients/test_audited_llm_client.py`
- Verification: `ruff check` passed and targeted pytest passed (`39 passed`).
- Ticket moved from `docs/bugs/open/plugins-llm/` to `docs/bugs/closed/plugins-llm/`.
