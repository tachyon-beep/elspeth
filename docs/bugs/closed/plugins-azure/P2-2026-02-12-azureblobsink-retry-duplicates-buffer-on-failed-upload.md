# Bug Report: AzureBlobSink Retry Can Duplicate Buffered Rows After Failed Upload

**Status: CLOSED (FIXED)**

## Summary

- `AzureBlobSink.write()` mutated `_buffered_rows` before `upload_blob()` succeeded.
- If upload failed and the same batch was retried on the same sink instance, the batch was appended again and the subsequent successful upload could include duplicate rows.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Review comment (Codex implementation)
- Date: 2026-02-12
- Related run/issue ID: N/A

## Steps To Reproduce

1. Call `write()` with batch A.
2. Simulate upload failure from Azure SDK.
3. Retry `write()` with batch A on the same sink instance.
4. Observe duplicate rows in uploaded cumulative payload.

## Expected Behavior

- Retries should be idempotent for sink instance state.
- Failed uploads should not commit current batch into `_buffered_rows`.

## Actual Behavior

- Failed uploads committed rows to `_buffered_rows` before external success.
- Retry appended the same batch again.

## Root Cause

- Premature state mutation at `write()` before external call success.

## Resolution (2026-02-12)

- Fixed in commit: `TBD` (set by git history)
- `write()` now builds `candidate_rows` for upload and commits to `_buffered_rows` only after `upload_blob()` succeeds.
- Added regression test verifying retry after failed upload does not duplicate rows.

## Evidence

- Code fix: `src/elspeth/plugins/azure/blob_sink.py`
- Regression test: `tests/unit/plugins/transforms/azure/test_blob_sink.py`

## Validation

- `.venv/bin/python -m pytest tests/unit/plugins/transforms/azure/test_blob_sink.py -k "upload_error_propagates_with_context or retry_after_failed_upload_does_not_duplicate_rows" -q`
- `.venv/bin/python -m pytest tests/unit/plugins/transforms/azure/test_blob_sink.py -q`
- `.venv/bin/python -m ruff check src/elspeth/plugins/azure/blob_sink.py tests/unit/plugins/transforms/azure/test_blob_sink.py`
- `.venv/bin/python -m mypy src/elspeth/plugins/azure/blob_sink.py`
