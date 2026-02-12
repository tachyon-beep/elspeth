# Bug Report: AzureBlobSink Skips Audit Call When overwrite=False and Blob Exists

**Status: CLOSED**

## Pre-Fix Verification (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.

## Resolution (2026-02-13)

- Status: **FIXED**
- Changes applied:
  - Updated `AzureBlobSink.write()` exception flow to record an ERROR external call
    before raising the overwrite conflict `ValueError`, including
    `error.reason = "blob_exists"` for `ResourceExistsError`.
  - Added regression coverage asserting `ctx.record_call()` is invoked on
    overwrite conflict and carries the expected error reason.
- Files changed:
  - `src/elspeth/plugins/azure/blob_sink.py`
  - `tests/unit/plugins/transforms/azure/test_blob_sink.py`
- Verification:
  - `./.venv/bin/python -m pytest tests/unit/plugins/transforms/azure/test_blob_sink.py -q` (57 passed)
  - `./.venv/bin/python -m ruff check src/elspeth/plugins/azure/blob_sink.py tests/unit/plugins/transforms/azure/test_blob_sink.py` (passed)


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
