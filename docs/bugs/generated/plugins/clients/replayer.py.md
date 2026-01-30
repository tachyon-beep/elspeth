# Bug Report: Replay ignores missing payloads for error calls with recorded responses

## Summary

- CallReplayer treats missing response payloads as acceptable for error calls, returning `{}` even when the call originally recorded a response payload that has since been purged, causing silent data loss and incorrect replay behavior.

## Severity

- Severity: major
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
- Data set or fixture: Any run with HTTP calls that returned non-2xx and later had payloads purged

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/plugins/clients/replayer.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Run a pipeline that makes an HTTP call returning a non-2xx status so `AuditedHTTPClient` records `response_data` even though the call is marked ERROR.
2. Configure a payload store, then purge payloads for the source run (retention).
3. Use `CallReplayer.replay(...)` for the same request hash.

## Expected Behavior

- Replay should fail with `ReplayPayloadMissingError` when a recorded response payload is missing (response_ref present), regardless of SUCCESS/ERROR status.

## Actual Behavior

- Replay treats missing payloads as acceptable for ERROR calls and returns `{}` instead, losing the recorded error response.

## Evidence

- `CallReplayer` allows missing payloads for error calls and substitutes `{}`: `/home/john/elspeth-rapid/src/elspeth/plugins/clients/replayer.py:212-220`
- `record_call` persists response payloads whenever `response_data` is provided (even for errors): `/home/john/elspeth-rapid/src/elspeth/core/landscape/recorder.py:1863-1876`
- HTTP client records `response_data` even when status is ERROR (non-2xx): `/home/john/elspeth-rapid/src/elspeth/plugins/clients/http.py:263-293`
- `get_call_response_data` returns `None` when payload has been purged: `/home/john/elspeth-rapid/src/elspeth/core/landscape/recorder.py:2471-2497`
- Calls carry `response_ref`, so `CallReplayer` can detect when a payload should exist: `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py:260-270`

## Impact

- User-facing impact: Replay mode returns empty error responses, potentially changing pipeline behavior and hiding recorded error details.
- Data integrity / security impact: Silent data loss in replay violates auditability expectations and can mislead investigations.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `CallReplayer` only checks `was_error` to decide whether missing payloads are allowed, but does not verify whether the call actually recorded a response payload (`response_ref`), so purged error responses are treated as legitimate “no response.”

## Proposed Fix

- Code changes (modules/files):
  - Update `/home/john/elspeth-rapid/src/elspeth/plugins/clients/replayer.py` to treat `response_data is None` as a replay failure **if** `call.response_ref` is set, regardless of `call.status`.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test in `/home/john/elspeth-rapid/tests/plugins/clients/test_replayer.py` that sets `call.status=ERROR`, `call.response_ref` non-None, and `get_call_response_data` returning `None`, expecting `ReplayPayloadMissingError`.
- Risks or migration steps:
  - Replay runs will now fail fast on missing error payloads that were previously masked.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `/home/john/elspeth-rapid/CLAUDE.md:21-27` (external calls must have full request/response recorded), `/home/john/elspeth-rapid/CLAUDE.md:38-41` (no silent recovery for audit data)
- Observed divergence: Replay substitutes `{}` for missing error response payloads, effectively inventing data instead of failing.
- Reason (if known): Missing check for `call.response_ref` when `response_data` is `None`.
- Alignment plan or decision needed: Ensure replay fails whenever a recorded response payload is missing, regardless of call status.

## Acceptance Criteria

- Replay raises `ReplayPayloadMissingError` when `call.response_ref` is set but payload is missing, for both SUCCESS and ERROR calls.
- New test covering missing error payloads passes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/clients/test_replayer.py`
- New tests required: yes, add coverage for error calls with missing response payloads.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `/home/john/elspeth-rapid/CLAUDE.md`
