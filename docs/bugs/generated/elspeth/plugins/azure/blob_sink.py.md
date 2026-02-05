# Bug Report: AzureBlobSink Overwrites Prior Batches on Repeated write() Calls

## Summary

- AzureBlobSink uploads only the current batch and overwrites the blob on each `write()` call, causing earlier batches in the same run to be lost while tokens are still marked as COMPLETED.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any dataset that results in multiple sink write batches in a single run

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/azure/blob_sink.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a pipeline with `azure_blob` sink using a fixed `blob_path` (no per-batch template) and default `overwrite: true`.
2. Run a pipeline that causes more than one `sink_executor.write()` call for the sink (e.g., a large source or any pipeline producing multiple pending token batches).
3. Inspect the resulting blob; only the last batch’s rows are present.

## Expected Behavior

- The blob should contain all rows written during the run, or the sink should fail fast if it cannot aggregate multiple batches safely.

## Actual Behavior

- Each `write()` call uploads only the current batch and overwrites the blob, so earlier batches are lost.

## Evidence

- `src/elspeth/plugins/azure/blob_sink.py:533-552` shows the sink serializes only the provided `rows` and uploads them immediately via `upload_blob()` with overwrite behavior.
- `src/elspeth/plugins/azure/blob_sink.py:607-623` shows `flush()` is a no-op and there is no buffering across calls.
- `src/elspeth/engine/executors.py:2054-2074` shows `sink.write()` is invoked per batch inside `SinkExecutor`.
- `src/elspeth/engine/orchestrator/core.py:1538-1566` shows the orchestrator groups tokens and calls `sink_executor.write()` repeatedly for pending batches.

## Impact

- User-facing impact: Output blob contains only the last batch of rows, silently dropping earlier batches.
- Data integrity / security impact: Audit trail may show tokens completed, but the artifact lacks corresponding rows, breaking auditability.
- Performance or cost impact: Wasted work and repeated uploads, potential reprocessing.

## Root Cause Hypothesis

- AzureBlobSink is implemented as a single-shot uploader without buffering or append semantics, but the engine calls `write()` multiple times per run.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/plugins/azure/blob_sink.py` should buffer rows across `write()` calls and upload once in `flush()`/`close()`, or implement Azure append/staged block uploads; alternatively, detect multiple `write()` calls for the same blob path and raise a clear error to prevent silent data loss.
- Config or schema changes: None
- Tests to add/update: Add a sink integration test that triggers two `write()` calls and asserts the blob contains rows from both batches (or asserts a hard failure if multiple writes are unsupported).
- Risks or migration steps: Buffering may increase memory usage; staged block uploads require additional Azure SDK calls and error handling.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:647-657` (Terminal Row States: no silent drops), `CLAUDE.md:252-255` (silent wrong results are worse than crashes).
- Observed divergence: Tokens can reach terminal states while their rows are missing from the sink artifact due to overwrites.
- Reason (if known): Sink assumes a single write per run and does not aggregate across batches.
- Alignment plan or decision needed: Implement buffering or append semantics for Azure Blob outputs or enforce single-write behavior with explicit failure.

## Acceptance Criteria

- A pipeline that triggers multiple `write()` calls results in a blob containing all rows from all batches, and the artifact hash reflects the full output.

## Tests

- Suggested tests to run: `./.venv/bin/python -m pytest tests/plugins/test_azure_blob_sink.py -v`
- New tests required: yes, add a multi-write sink test covering batch aggregation behavior

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`, `src/elspeth/engine/executors.py`, `src/elspeth/engine/orchestrator/core.py`
---
# Bug Report: AzureBlobSink Skips Audit Call When overwrite=False and Blob Exists

## Summary

- When `overwrite=False` and the blob already exists, `AzureBlobSink` raises `ValueError` without recording an external call, leaving the audit trail incomplete.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline writing to an existing Azure blob with `overwrite: false`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/azure/blob_sink.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `azure_blob` sink with `overwrite: false` and a fixed `blob_path`.
2. Run the pipeline once to create the blob.
3. Run the pipeline again with the same configuration and inspect Landscape calls for the second run.

## Expected Behavior

- The existence check and failure should be recorded via `ctx.record_call()` with an ERROR status and a clear reason.

## Actual Behavior

- The sink raises `ValueError` without recording any external call, leaving no audit record of the attempted write or the existence check.

## Evidence

- `src/elspeth/plugins/azure/blob_sink.py:547-578` shows `blob_client.exists()` is called and `ValueError` is raised, but the `except ValueError` path re-raises without calling `ctx.record_call()`.
- `docs/release/feature-inventory.md:200-208` specifies external calls should have full request/response recorded via `record_call()`.

## Impact

- User-facing impact: Failures due to existing blobs are harder to audit or diagnose.
- Data integrity / security impact: Audit trail lacks a record of the external call and failure reason.
- Performance or cost impact: None

## Root Cause Hypothesis

- The overwrite-exists path treats `ValueError` as a purely local error and skips `record_call()`, even though it is triggered by an external Azure call.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/plugins/azure/blob_sink.py` should record an ERROR call before raising when `overwrite=False` and `blob_client.exists()` returns true, including a reason like `"blob_exists"`.
- Config or schema changes: None
- Tests to add/update: Add a test that mocks `blob_client.exists()` to return true and asserts `ctx.record_call()` is invoked with ERROR status.
- Risks or migration steps: None

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/release/feature-inventory.md:200-208` (External call must record full request/response via `record_call()`).
- Observed divergence: External call (`exists`) leads to an error without a recorded call.
- Reason (if known): Explicit `except ValueError` path bypasses audit recording.
- Alignment plan or decision needed: Record the failure in the audit trail before raising.

## Acceptance Criteria

- When `overwrite=False` and the blob exists, a failed external call entry is recorded with request details and error reason.

## Tests

- Suggested tests to run: `./.venv/bin/python -m pytest tests/plugins/test_azure_blob_sink.py -v`
- New tests required: yes, add an overwrite-exists audit-recording test

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/release/feature-inventory.md`
