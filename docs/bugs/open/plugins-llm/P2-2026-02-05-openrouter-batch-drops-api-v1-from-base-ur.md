# Bug Report: OpenRouter Batch Drops `/api/v1` From Base URL

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- OpenRouter batch uses `httpx.Client(base_url=...)` but sends requests with a leading slash path, which causes `httpx` to discard the `/api/v1` path segment and hit the wrong endpoint.

## Severity

- Severity: moderate
- Priority: P2
- Downgrade rationale: Wrong endpoint is a functionality bug; calls fail clearly, no silent data corruption

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: `0282d1b441fe23c5aaee0de696917187e1ceeb9b` on `RC2.3-pipeline-row`
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Any batch row (e.g., `{"text": "Test"}`)

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of `src/elspeth/plugins/llm/openrouter_batch.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `OpenRouterBatchLLMTransform` with the default `base_url` (`https://openrouter.ai/api/v1`).
2. Run `process()` on any batch while intercepting `httpx.Client.post`.
3. Observe requests sent to `/chat/completions` on the host root (missing `/api/v1`).

## Expected Behavior

- Requests should be sent to `https://openrouter.ai/api/v1/chat/completions`.

## Actual Behavior

- Requests are sent to `https://openrouter.ai/chat/completions`, which is the wrong endpoint.

## Evidence

- Default base URL includes `/api/v1`: `src/elspeth/plugins/llm/openrouter_batch.py:66`
- Shared `httpx.Client` uses `base_url=self._base_url`: `src/elspeth/plugins/llm/openrouter_batch.py:429`
- Request path is absolute (`"/chat/completions"`), which drops the base path: `src/elspeth/plugins/llm/openrouter_batch.py:581`

## Impact

- User-facing impact: All calls fail or hit an unintended endpoint, yielding errors for every row.
- Data integrity / security impact: Audit trail records errors for calls that should have succeeded.
- Performance or cost impact: Repeated failed calls waste time and compute.

## Root Cause Hypothesis

- `httpx.Client(base_url=...)` with a leading-slash path causes URL join semantics to discard the base path. The plugin uses `"/chat/completions"` instead of `"chat/completions"`.

## Proposed Fix

- Code changes (modules/files):
`src/elspeth/plugins/llm/openrouter_batch.py`: change `client.post("/chat/completions", ...)` to `client.post("chat/completions", ...)`, or normalize `base_url` to host-only and keep absolute paths.
- Config or schema changes: None.
- Tests to add/update:
Add a test in `tests/plugins/llm/test_openrouter_batch.py` that asserts the final request URL includes `/api/v1`.
- Risks or migration steps:
Low risk; no schema changes, only endpoint correctness.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Base URL path is dropped due to absolute request path usage.
- Reason (if known): Incorrect URL join semantics with `httpx.Client(base_url=...)`.
- Alignment plan or decision needed: Normalize request path to be relative or adjust base URL.

## Acceptance Criteria

- Requests are sent to `/api/v1/chat/completions` when `base_url` includes `/api/v1`.
- Existing tests still pass, and a new test verifies correct URL joining.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/llm/test_openrouter_batch.py`
- New tests required: yes, add URL join assertion test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
