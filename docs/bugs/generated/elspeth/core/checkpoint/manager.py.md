# Bug Report: Checkpoint serialization crashes on datetime values in aggregation state

## Summary

- `CheckpointManager.create_checkpoint()` serializes `aggregation_state` with `json.dumps()` which cannot handle `datetime` values that are allowed in pipeline contracts; this causes checkpoint creation to crash for aggregation buffers containing datetime fields.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: 7a155997ad574d2a10fa3838dd0079b0d67574ff (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Aggregation pipeline with a datetime-typed field in row data

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/checkpoint/manager.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a source schema that produces a `datetime` field (allowed by `SchemaContract`).
2. Use an aggregation transform so rows are buffered and checkpointing is enabled (default).
3. Process enough rows to create a checkpoint while buffered tokens exist.

## Expected Behavior

- Checkpoint creation should succeed, preserving aggregation state (including datetime fields) so recovery can restore accurate types.

## Actual Behavior

- Checkpoint creation raises `TypeError: Object of type datetime is not JSON serializable`, aborting checkpoint creation and potentially failing the run.

## Evidence

- `CheckpointManager.create_checkpoint()` uses `json.dumps()` for `aggregation_state` without a custom encoder.  
  `src/elspeth/core/checkpoint/manager.py:91-95`
- Aggregation checkpoints include `row_data` dicts taken directly from `PipelineRow.to_dict()`, which can contain datetime values.  
  `src/elspeth/engine/executors.py:1464-1542`
- Pipeline contracts explicitly allow `datetime` field types.  
  `src/elspeth/contracts/schema_contract.py:29-39`

## Impact

- User-facing impact: Pipelines with aggregation and datetime fields cannot checkpoint; crash recovery is unavailable.
- Data integrity / security impact: Checkpoint creation fails mid-run, increasing risk of lost progress on crash.
- Performance or cost impact: Reprocessing rows after failures; increased runtime due to loss of checkpointing.

## Root Cause Hypothesis

- `CheckpointManager` serializes aggregation state with `json.dumps()` (no datetime handling). Aggregation state can contain datetime values because pipeline contracts permit them, leading to serialization failure.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/checkpoint/manager.py`: Replace `json.dumps()` with a serializer that can handle datetime (and any other contract-permitted types) while preserving type fidelity.
  - Consider adding a dedicated checkpoint serialization helper (e.g., `checkpoint_json.dumps/loads`) used consistently by both `CheckpointManager` and aggregation checkpoint size validation.
- Config or schema changes: None.
- Tests to add/update:
  - Add a checkpoint creation test that includes aggregation state with datetime values and asserts successful serialization and restore.
  - Add a round-trip restore test ensuring datetime fields remain datetimes after resume.
- Risks or migration steps:
  - If serialization format changes (e.g., type tags), bump aggregation checkpoint `_version` and add backward-compat decoding for existing checkpoints.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- Checkpoint creation succeeds when aggregation buffers contain datetime fields.
- Resume restores buffered token row data with correct datetime types.
- Added tests cover datetime checkpoint serialization and restoration.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_executor_pipeline_row.py`
- New tests required: yes, aggregation checkpoint serialization/restoration with datetime values

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
