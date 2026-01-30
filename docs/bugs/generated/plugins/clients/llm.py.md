# Bug Report: LLM response payload dropped when post-call parsing fails

## Summary

- `AuditedLLMClient.chat_completion()` records an ERROR without `response_data` when an exception is raised after the external call returns (e.g., `choices` empty or `model_dump()` fails), violating the audit requirement to persist full request and response for external calls.

## Severity

- Severity: major
- Priority: P1

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

- Goal or task prompt: static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/plugins/clients/llm.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a mock OpenAI-compatible client that returns a response object with `choices = []` (or a `model_dump()` that raises).
2. Call `AuditedLLMClient.chat_completion(...)`.
3. Inspect the recorder call: `record_call()` is invoked with `status=ERROR` and **no `response_data`**, despite a response object having been returned.

## Expected Behavior

- If an external response exists but parsing/inspection fails, the audit record should still include the raw response payload (`response_data`) alongside the error.

## Actual Behavior

- The exception handler records only `request_data` and `error`, dropping the response payload entirely.

## Evidence

- Response parsing that can raise after the external call returns: `/home/john/elspeth-rapid/src/elspeth/plugins/clients/llm.py:291-305`
- Error handler records no `response_data`: `/home/john/elspeth-rapid/src/elspeth/plugins/clients/llm.py:331-350`
- Audit requirement for external calls to record full request/response: `/home/john/elspeth-rapid/CLAUDE.md:21-26`

## Impact

- User-facing impact: `explain()` and replay/verify lose the actual provider response for failed parses.
- Data integrity / security impact: Audit trail is incomplete for external calls, violating the auditability standard.
- Performance or cost impact: N/A

## Root Cause Hypothesis

- The external call and response parsing are inside a single `try` block; any parsing error is treated as a call failure and the `except` path does not include response payloads.

## Proposed Fix

- Code changes (modules/files):
  - `/home/john/elspeth-rapid/src/elspeth/plugins/clients/llm.py`: split network call from response parsing; if a response object exists, capture and record `raw_response` in `response_data` even when parsing fails.
- Config or schema changes: none
- Tests to add/update:
  - Add a test that simulates a malformed response (`choices=[]` or `model_dump()` failure) and asserts `record_call()` includes `response_data` with `raw_response` on ERROR.
- Risks or migration steps:
  - Ensure `raw_response` serialization handles edge cases (fallback to `repr` if `model_dump()` fails).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `/home/john/elspeth-rapid/CLAUDE.md:21-26`
- Observed divergence: Error path drops the external response payload when parsing fails.
- Reason (if known): Single `try/except` block treats parse errors like call failures without preserving response.
- Alignment plan or decision needed: Record raw responses for all external calls, even when downstream parsing fails.

## Acceptance Criteria

- When response parsing fails after a successful external call, the audit record includes `response_data` containing the raw response payload.
- A unit test covers malformed response handling and verifies audit recording.

## Tests

- Suggested tests to run: `pytest /home/john/elspeth-rapid/tests/plugins/clients/test_audited_llm_client.py -k malformed`
- New tests required: yes, malformed response audit recording test

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `/home/john/elspeth-rapid/CLAUDE.md`
