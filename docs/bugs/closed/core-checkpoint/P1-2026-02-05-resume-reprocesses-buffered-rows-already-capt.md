# Bug Report: Resume Reprocesses Buffered Rows Already Captured In Checkpoint State

## Summary

- `RecoveryManager.get_unprocessed_rows()` ignores `checkpoint.aggregation_state_json`, so rows already buffered and restored from the checkpoint are still treated as unprocessed and re-run, causing duplicate buffering and duplicate downstream outputs.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (branch unknown)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Aggregation passthrough run with checkpointing enabled while buffers are non-empty

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/checkpoint/recovery.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a pipeline with passthrough aggregation (BUFFERED outcomes) and enable checkpointing (e.g., every N rows).
2. Ensure a checkpoint is created while aggregation buffers contain buffered tokens (e.g., other branch/sink writes trigger checkpoint).
3. Crash the run and resume it.
4. Observe that buffered rows appear in `get_unprocessed_rows()` and are reprocessed.

## Expected Behavior

- Rows already present in `checkpoint.aggregation_state_json` (buffered tokens restored into the aggregation executor) should be excluded from `unprocessed_rows` to avoid duplicate buffering and duplicate outputs.

## Actual Behavior

- `get_unprocessed_rows()` only inspects token outcomes and does not exclude buffered rows already included in `aggregation_state_json`. On resume, those rows are both restored and reprocessed, creating duplicates.

## Evidence

- `src/elspeth/core/checkpoint/recovery.py:271-384` — `get_unprocessed_rows()` computes unprocessed rows solely from token outcomes, with no filtering by `checkpoint.aggregation_state_json`.
- `src/elspeth/engine/executors.py:1489-1565` — aggregation checkpoint state includes buffered tokens with `row_id`, meaning buffered rows can be restored from checkpoint state.
- `src/elspeth/engine/orchestrator/core.py:1704-1783` — resume restores `aggregation_state` and then processes `unprocessed_rows` from payloads, so restored buffered tokens and reprocessed rows can both be present.

## Impact

- User-facing impact: Duplicate rows emitted after resume in passthrough aggregation pipelines.
- Data integrity / security impact: Audit trail records duplicated processing for the same row, undermining traceability and correctness.
- Performance or cost impact: Extra processing and downstream writes for duplicated rows.

## Root Cause Hypothesis

- `RecoveryManager.get_unprocessed_rows()` ignores the checkpoint’s aggregation buffer contents, so buffered rows already captured in `aggregation_state_json` are still treated as unprocessed.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/core/checkpoint/recovery.py` — parse `checkpoint.aggregation_state_json`, collect buffered `row_id`s from each node’s `tokens` list, and exclude those row IDs from the `unprocessed` set before returning.
- Config or schema changes: None.
- Tests to add/update: Add a recovery test that builds a checkpoint with non-empty aggregation buffers and verifies buffered rows are excluded from `get_unprocessed_rows()` when `aggregation_state_json` includes them.
- Risks or migration steps: Ensure exclusion is limited to rows present in checkpoint state to avoid skipping genuinely unprocessed rows when no buffer state was captured.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): CLAUDE.md “Auditability Standard” and “Terminal Row States” (audit trail must be accurate; no silent duplication).
- Observed divergence: Resume path can process the same row twice (restored buffer + reprocessing), creating duplicate audit entries and outputs.
- Reason (if known): `get_unprocessed_rows()` does not account for checkpoint aggregation buffers.
- Alignment plan or decision needed: Exclude buffered row IDs already captured in checkpoint aggregation state.

## Acceptance Criteria

- Resume no longer reprocesses rows whose tokens are already present in `checkpoint.aggregation_state_json`.
- Aggregation buffers restored from checkpoint do not receive duplicate rows on resume.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/checkpoint/test_recovery.py`
- New tests required: yes, add a recovery test for buffered rows present in checkpoint aggregation state.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: CLAUDE.md (Auditability Standard, Terminal Row States)

## Resolution

**Status:** FIXED (2026-02-06)

**Fix Details:**

Modified `RecoveryManager.get_unprocessed_rows()` in `src/elspeth/core/checkpoint/recovery.py`:

1. Parse `checkpoint.aggregation_state_json` to extract all buffered row IDs
2. Collect `row_id` from each token in each node's `tokens` list
3. Filter these row IDs from the unprocessed set before returning

**Code Changes:**
- `src/elspeth/core/checkpoint/recovery.py:271-410` - Added aggregation buffer extraction and filtering

**Tests Added:**
- `tests/core/checkpoint/test_recovery.py::TestGetUnprocessedRowsBufferedInAggregation::test_buffered_rows_excluded_from_unprocessed` - Verifies buffered rows are excluded
- `tests/core/checkpoint/test_recovery.py::TestGetUnprocessedRowsBufferedInAggregation::test_empty_aggregation_state_does_not_affect_unprocessed` - Verifies null/empty state works

**Verification:**
```bash
.venv/bin/python -m pytest tests/core/checkpoint/test_recovery.py::TestGetUnprocessedRowsBufferedInAggregation -v
# 2 passed
```
