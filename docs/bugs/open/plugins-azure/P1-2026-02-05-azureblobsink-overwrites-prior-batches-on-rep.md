# Bug Report: AzureBlobSink Overwrites Prior Batches on Repeated write() Calls

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


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
