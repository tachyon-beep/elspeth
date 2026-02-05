# Bug Report: Azure Batch LLM Crashes on Aggregation Flush Due to dict/PipelineRow Mismatch

## Summary

- `azure_batch_llm` assumes `PipelineRow` in batch mode and calls `.to_dict()`, but the engine’s aggregation path passes `list[dict]`, causing `AttributeError` at runtime when a batch flush occurs.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any aggregation pipeline using `azure_batch_llm` with a batch trigger

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/plugins/llm/azure_batch.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `azure_batch_llm` as a batch-aware transform under `aggregations` with a trigger (e.g., count-based).
2. Run a pipeline until the aggregation trigger fires and the engine flushes the buffer.
3. Observe the transform call path: engine passes `list[dict]` to `process()`; `azure_batch_llm` calls `row.to_dict()` and raises `AttributeError`.

## Expected Behavior

- `azure_batch_llm` should accept the engine’s `list[dict]` in aggregation mode and process the batch without attribute errors.

## Actual Behavior

- The plugin crashes with `AttributeError: 'dict' object has no attribute 'to_dict'` during batch submission or completion.

## Evidence

- `azure_batch_llm` declares batch input as `list[PipelineRow]` and calls `.to_dict()` on each row. `src/elspeth/plugins/llm/azure_batch.py:356-420` and `src/elspeth/plugins/llm/azure_batch.py:535-540`.
- Batch completion path also calls `.to_dict()` on each row before downloading results. `src/elspeth/plugins/llm/azure_batch.py:774-776`.
- The engine’s aggregation path explicitly buffers rows as `dict` and calls `transform.process(rows: list[dict])`. `src/elspeth/engine/processor.py:1715-1723` and `src/elspeth/engine/executors.py:1232-1302`.

## Impact

- User-facing impact: Pipelines using `azure_batch_llm` in aggregation nodes fail at the first batch flush, halting processing.
- Data integrity / security impact: No data corruption, but runs fail with incomplete processing and missing outputs.
- Performance or cost impact: Wasted batch setup time and potential retry churn due to deterministic crash.

## Root Cause Hypothesis

- Incomplete PipelineRow migration: `azure_batch_llm` was updated to `PipelineRow` assumptions, but the aggregation executor still passes `list[dict]` (current engine contract for batch-aware transforms).

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/llm/azure_batch.py`: Normalize batch inputs by accepting `list[dict[str, Any]]` in aggregation mode, and only call `.to_dict()` when `row` is a `PipelineRow` (e.g., when used outside aggregation).
  - Update type hints and docstrings to reflect actual engine contract for batch-aware transforms.
- Config or schema changes: N/A
- Tests to add/update:
  - Add a test in `tests/plugins/llm/test_azure_batch.py` that calls `process()` with `list[dict]` and verifies no `AttributeError`.
  - Add an integration test that exercises an aggregation flush path with `azure_batch_llm`.
- Risks or migration steps:
  - Ensure non-aggregation usage (single-row transform path) still works with `PipelineRow`.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/base.py:41-83` and `src/elspeth/engine/processor.py:1715-1718` describe batch-aware transforms receiving `list[dict]`.
- Observed divergence: `azure_batch_llm` implements batch processing as `list[PipelineRow]` and calls `.to_dict()`, incompatible with the engine’s batch contract.
- Reason (if known): Partial PipelineRow migration; batch-aware transform contract not updated consistently.
- Alignment plan or decision needed: Align `azure_batch_llm` with the engine’s `list[dict]` batch contract and gate any `PipelineRow` usage to non-aggregation paths.

## Acceptance Criteria

- `azure_batch_llm` successfully processes batches when invoked by AggregationExecutor without attribute errors.
- Unit test coverage includes `list[dict]` batch input and passes.
- Existing single-row usage (non-aggregation path) still functions with `PipelineRow`.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/llm/test_azure_batch.py -k batch`
- New tests required: yes, add coverage for `list[dict]` batch input and aggregation flush path

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/2026-02-03-pipelinerow-migration.md`
