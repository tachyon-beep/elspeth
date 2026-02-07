# Bug Report: Deaggregation path crashes when TransformResult.rows are PipelineRow

## Summary

- RowProcessor passes multi-row outputs directly to `TokenManager.expand_token`, which expects `list[dict]`. If a transform returns `PipelineRow` objects (allowed by `TransformResult.rows`), `expand_token` fails while re-wrapping, crashing the run and leaving the parent token without a terminal outcome.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074e / RC2.3-pipeline-row
- OS: Linux 6.8.0-90-generic
- Python version: 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline with a deaggregation transform returning `PipelineRow` outputs

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `src/elspeth/engine/processor.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a transform with `creates_tokens=True` that returns `TransformResult.success_multi([PipelineRow(...), PipelineRow(...)], success_reason=...)`.
2. Run a pipeline with this transform and process any row.
3. Observe the crash during token expansion.

## Expected Behavior

- Multi-row outputs containing `PipelineRow` instances should be normalized to dicts before token expansion, allowing child tokens to be created and processing to continue.

## Actual Behavior

- `TokenManager.expand_token()` receives `PipelineRow` entries, and `PipelineRow` re-wrapping fails with a `TypeError` during `dict(data)` conversion, aborting the run and leaving the parent token without a terminal outcome.

## Evidence

- `src/elspeth/engine/processor.py:1807-1835` passes `transform_result.rows` directly to `expand_token` without converting `PipelineRow` to dicts.
- `src/elspeth/contracts/results.py:117-121` allows `TransformResult.rows` to contain `PipelineRow`.
- `src/elspeth/engine/tokens.py:307-339` documents `expanded_rows` as `list[dict[str, Any]]` and wraps them as dicts for `PipelineRow` construction.

## Impact

- User-facing impact: Pipelines with deaggregation transforms that return `PipelineRow` outputs crash during processing.
- Data integrity / security impact: Parent token does not receive a terminal outcome (EXPANDED), creating an audit trail gap.
- Performance or cost impact: Run aborts, wasted compute and partial processing.

## Root Cause Hypothesis

- The deaggregation path in `RowProcessor._process_single_token` does not normalize multi-row outputs to dicts before calling `TokenManager.expand_token`, unlike other aggregation paths that use `_extract_dict()`.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/processor.py`: Convert `transform_result.rows` to dicts via `_extract_dict()` before `expand_token` in the non-aggregation multi-row path.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test covering a deaggregation transform returning `PipelineRow` list and assert child tokens are created without error.
- Risks or migration steps:
  - Low risk; aligns deaggregation behavior with existing aggregation paths that already normalize row types.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/2026-02-03-pipelinerow-migration.md` (PipelineRow migration plan)
- Observed divergence: Multi-row PipelineRow outputs are allowed but not normalized in the deaggregation path.
- Reason (if known): Likely an omission when aligning deaggregation with aggregation handling.
- Alignment plan or decision needed: Normalize rows using `_extract_dict()` before expansion.

## Acceptance Criteria

- Deaggregation transforms returning `PipelineRow` outputs no longer crash.
- Child tokens are created and continue through downstream processing.
- Parent token’s EXPANDED outcome is recorded as expected.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_processor_deaggregation_pipeline_row.py -v`
- New tests required: yes, add a focused test for PipelineRow multi-row deaggregation.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/2026-02-03-pipelinerow-migration.md`
