# Bug Report: AzureBlobSink does not record Azure Blob SDK calls in the audit trail

## Summary

- Azure Blob Storage operations (exists check and upload) are executed without recording external call request/response payloads, violating the audit trail requirement for external calls.

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

- Goal or task prompt: Static analysis bug audit of `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_sink.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a pipeline with the `azure_blob` sink and run a job with at least one row.
2. Inspect the Landscape `calls` table for the sink node’s `state_id` recorded during the sink write.
3. Observe no `external_call` records for the Azure Blob operations.

## Expected Behavior

- Each Azure Blob SDK call (existence check and upload) is recorded via `ctx.record_call()` with request/response payloads persisted for audit/replay.

## Actual Behavior

- Azure Blob SDK calls are executed without any `ctx.record_call()` invocation, so no external-call request/response payloads are captured in the audit trail.

## Evidence

- Audit standard requires external calls to be fully recorded. `CLAUDE.md:25`
- Sink executor explicitly sets `ctx.state_id` to enable external call recording for sinks. `src/elspeth/engine/executors.py:1667`
- Azure Blob SDK calls (exists + upload) occur in the sink without any call recording. `src/elspeth/plugins/azure/blob_sink.py:435`
- The upload call is executed directly via the SDK with no audit record. `src/elspeth/plugins/azure/blob_sink.py:445`

## Impact

- User-facing impact: No direct functional failure, but auditability of sink behavior is incomplete.
- Data integrity / security impact: Audit trail lacks required external call payloads; replay/verify modes cannot fully reconstruct sink-side external interactions.
- Performance or cost impact: Unknown

## Root Cause Hypothesis

- AzureBlobSink does not invoke `ctx.record_call()` around external Azure Blob SDK operations despite the sink executor preparing `ctx.state_id` for this purpose.

## Proposed Fix

- Code changes (modules/files):
  - Add `ctx.record_call()` calls in `src/elspeth/plugins/azure/blob_sink.py` around `blob_client.exists()` and `blob_client.upload_blob(...)`, recording request metadata (container, blob path, overwrite, size, content_hash) and response metadata (e.g., etag, last_modified when available).
- Config or schema changes: None
- Tests to add/update:
  - Add a unit test for AzureBlobSink verifying that a sink write emits `calls` records with `call_type` = `FILESYSTEM` or `HTTP` and non-empty request/response payloads.
- Risks or migration steps:
  - Ensure recorded request payloads do not include secrets (auth data must not be logged).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25`
- Observed divergence: External calls to Azure Blob Storage are not recorded in the audit trail.
- Reason (if known): Missing `ctx.record_call()` usage in AzureBlobSink.
- Alignment plan or decision needed: Implement call recording in the sink using the existing audit facilities.

## Acceptance Criteria

- For a run using `azure_blob`, the Landscape `calls` table includes entries for blob existence checks and uploads tied to the sink node state.
- Recorded request/response payloads are present (and stored in payload store when configured).
- No secrets are captured in recorded payloads.

## Tests

- Suggested tests to run: `uv run .venv/bin/python -m pytest tests/`
- New tests required: yes, add a unit test validating external call recording for AzureBlobSink

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
