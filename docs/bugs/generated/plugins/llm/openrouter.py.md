# Bug Report: OpenRouter transient HTTP failures never trigger RetryManager retries

## Summary

- OpenRouter retryable HTTP/network failures are converted into TransformResult.error, but the engine only retries exceptions; this prevents RetryManager from retrying transient OpenRouter failures.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 290716a2563735271d162f1fac7d40a7690e6ed6 (fix/RC1-RC2-bridge)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit of /home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a pipeline using `openrouter_llm` and enable RetryManager with multiple attempts in settings.
2. Trigger a transient OpenRouter failure (e.g., 429/503/529 or network timeout).
3. Observe that the row fails immediately with a TransformResult.error and no retry attempts are recorded.

## Expected Behavior

- RetryManager should retry transient failures (rate limits, server errors, network errors) by re-executing the transform, recording multiple attempts.

## Actual Behavior

- The transform returns TransformResult.error for transient OpenRouter failures, so the engine does not retry and the row is routed to the error sink or failed after a single attempt.

## Evidence

- OpenRouter converts HTTPStatusError/RequestError into TransformResult.error instead of raising a retryable exception: `src/elspeth/plugins/llm/openrouter.py:294-311`.
- Engine explicitly does not retry TransformResult.error; only exceptions trigger retry: `src/elspeth/engine/processor.py:1138-1145`.
- Azure LLM transform demonstrates intended pattern: retryable errors are re-raised to let RetryManager handle them: `src/elspeth/plugins/llm/azure.py:308-323`.

## Impact

- User-facing impact: Transient OpenRouter rate limits or network issues cause immediate row failures rather than automatic retries, reducing pipeline reliability.
- Data integrity / security impact: Audit trail lacks retry attempts for transient external failures, obscuring expected behavior and potentially increasing false-negative outputs.
- Performance or cost impact: Increased manual intervention and re-runs; possible higher error rates in production.

## Root Cause Hypothesis

- The OpenRouter transform treats retryable HTTP/network failures as TransformResult.error, but RetryManager only retries on exceptions. As a result, retryable failures never trigger retry logic.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/llm/openrouter.py`: Map HTTP 429/503/529 and other transient failures to retryable exceptions (e.g., RateLimitError/ServerError/NetworkError from `elspeth.plugins.clients.llm`) and re-raise, mirroring Azure’s behavior.
  - For non-retryable HTTP errors (e.g., 4xx client errors), continue returning TransformResult.error.
- Config or schema changes: None.
- Tests to add/update:
  - Unit test that HTTP 429/503/529 results in a retryable exception and triggers RetryManager attempts.
  - Unit test that RequestError is treated as retryable (NetworkError) and triggers retries.
- Risks or migration steps:
  - Behavior change: transient OpenRouter errors will now retry instead of immediately erroring; ensure retry limits are configured appropriately.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/llm/azure.py:308-323` (documented retryable re-raise pattern for LLM transforms)
- Observed divergence: OpenRouter returns TransformResult.error for retryable failures instead of raising retryable exceptions.
- Reason (if known): Likely oversight when implementing HTTP-based OpenRouter path.
- Alignment plan or decision needed: Align OpenRouter with standard LLM retry semantics by re-raising retryable exceptions.

## Acceptance Criteria

- OpenRouter transient failures (429/503/529, network errors) raise retryable exceptions and are retried by RetryManager.
- Audit trail shows multiple attempts for retryable OpenRouter failures.
- Non-retryable HTTP errors still produce TransformResult.error and route to error sink as configured.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/ -k openrouter`
- New tests required: yes, add coverage for retryable OpenRouter errors and RetryManager behavior.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/plugins/llm/azure.py` (retryable error handling pattern)
