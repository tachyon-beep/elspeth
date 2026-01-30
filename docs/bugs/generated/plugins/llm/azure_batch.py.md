# Bug Report: Unknown custom_id in Azure batch output can crash during call recording

## Summary

- Batch output lines are accepted without validating that `custom_id` exists in the checkpoint’s row mapping; later direct indexing crashes with `KeyError` if Azure returns an unexpected `custom_id`.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Azure Batch JSONL output with an unexpected `custom_id`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/plugins/llm/azure_batch.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Submit a batch and persist the checkpoint.
2. Provide/receive a batch output JSONL containing a line with a `custom_id` that is not present in the checkpoint’s `row_mapping` (e.g., stale checkpoint or corrupted output).
3. Resume processing so `_download_results()` executes.

## Expected Behavior

- The unexpected `custom_id` is rejected as malformed external data, reported as an error, and the batch is handled deterministically without crashing.

## Actual Behavior

- The code accepts the line, then crashes with `KeyError` when recording calls because it indexes `row_mapping[custom_id]` / `requests_data[custom_id]` without validating membership. This aborts the run and leaves the checkpoint uncleared.

## Evidence

- `src/elspeth/plugins/llm/azure_batch.py:729` extracts `custom_id` from external output without validating it against `row_mapping`.
- `src/elspeth/plugins/llm/azure_batch.py:758` stores the result for any `custom_id`.
- `src/elspeth/plugins/llm/azure_batch.py:866` uses `requests_data[custom_id]` with no guard.
- `src/elspeth/plugins/llm/azure_batch.py:868` uses `row_mapping[custom_id]` with no guard.

## Impact

- User-facing impact: Pipeline can crash on malformed or unexpected batch output.
- Data integrity / security impact: Audit trail incomplete due to crash before recording calls or clearing checkpoints.
- Performance or cost impact: Potential retries and repeated batch submissions.

## Root Cause Hypothesis

- External batch output is treated as valid after basic structural checks, but `custom_id` is not validated against checkpoint-owned mappings before being used as a trusted key.

## Proposed Fix

- Code changes (modules/files):
  - Validate `custom_id` membership in `row_mapping` (and/or `requests_data`) before storing in `results_by_id`; treat unknown IDs as malformed and include them in `malformed_lines`.
  - Guard call-recording loop to skip or explicitly error on unknown `custom_id`.
- Config or schema changes: None.
- Tests to add/update:
  - Unit test for `_download_results()` with a JSONL line containing an unknown `custom_id` to assert no crash and a structured error.
- Risks or migration steps:
  - None; change is localized and defensive at the external boundary.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` (External Call Boundaries in Transforms: validate external data immediately).
- Observed divergence: External output is accepted without validating `custom_id` against internal mappings.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Add explicit validation at the boundary to keep external data from crashing the pipeline.

## Acceptance Criteria

- Unknown `custom_id` lines are rejected and reported without crashing.
- Batch processing completes with a deterministic error result and stable audit trail.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/test_azure_batch.py -k unknown_custom_id`
- New tests required: yes, simulate unknown `custom_id` in output JSONL.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Auditability Standard, External Call Boundaries)
---
# Bug Report: Missing audit Call records for rows absent from batch output

## Summary

- When the output JSONL omits a row’s `custom_id`, the code emits an error row but records no LLM call for that row, leaving a gap in the audit trail.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Azure Batch JSONL output missing one or more `custom_id` lines

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/plugins/llm/azure_batch.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Submit a batch with N rows and persist the checkpoint.
2. Provide a batch output JSONL missing one or more `custom_id` entries.
3. Resume processing so `_download_results()` executes.

## Expected Behavior

- For each missing output line, a corresponding LLM call is recorded with `CallStatus.ERROR` and a reason like `result_missing`, ensuring full audit coverage.

## Actual Behavior

- The row is marked with `result_not_found`, but no call record is written because `record_call()` runs only for `results_by_id` entries.

## Evidence

- `src/elspeth/plugins/llm/azure_batch.py:795` finds `custom_id` by index mapping and allows missing outputs to proceed.
- `src/elspeth/plugins/llm/azure_batch.py:797` marks missing results as `result_not_found` without recording a call.
- `src/elspeth/plugins/llm/azure_batch.py:861` starts the call-recording loop for only `results_by_id`.
- `src/elspeth/plugins/llm/azure_batch.py:866` records calls only for present results.

## Impact

- User-facing impact: Operators cannot trace what happened for specific rows when output is missing.
- Data integrity / security impact: Audit trail violates “full request and response recorded” for missing outputs.
- Performance or cost impact: None direct, but audit gaps increase investigation time and compliance risk.

## Root Cause Hypothesis

- Call recording is tied only to parsed output lines, and no fallback exists to record calls for requests whose outputs are missing.

## Proposed Fix

- Code changes (modules/files):
  - Track missing `custom_id` values during output assembly.
  - Record an LLM call with `CallStatus.ERROR` for each missing output using the stored request from `checkpoint["requests"]`.
- Config or schema changes: None.
- Tests to add/update:
  - Unit test that simulates missing output lines and asserts an audit call is recorded for each missing row.
- Risks or migration steps:
  - None; adds audit entries without altering core flow.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` (Auditability Standard: “External calls - Full request AND response recorded”).
- Observed divergence: Missing output lines yield no LLM call records.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Record a call for every submitted request, even when the output is missing.

## Acceptance Criteria

- Each submitted request has a corresponding call record (success or error), even when the output file omits the result line.
- Audit trail contains explicit error entries for missing results.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/test_azure_batch.py -k missing_output_records_call`
- New tests required: yes, cover missing output line behavior.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Auditability Standard)
