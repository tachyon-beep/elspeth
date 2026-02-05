# Bug Report: CheckpointManager cannot serialize aggregation state containing allowed `datetime` values

## Summary

- `CheckpointManager.create_checkpoint()` uses `json.dumps()` for `aggregation_state`, which raises `TypeError` when buffered rows contain `datetime` (an allowed `SchemaContract` field type), causing checkpoint creation (and thus crash recovery) to fail.

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
- Data set or fixture: Any pipeline where aggregation buffers include `datetime` fields

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/core/checkpoint/manager.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a source schema with a field typed as `datetime` and ensure rows include `datetime` values.
2. Add an aggregation node and enable checkpointing (so aggregation buffers are serialized on checkpoint).
3. Run the pipeline until a checkpoint is created while aggregation buffers are non-empty.

## Expected Behavior

- Checkpoint creation succeeds and aggregation state is serialized with type fidelity (or at least a deterministic, type-restorable encoding), enabling recovery without type corruption.

## Actual Behavior

- `json.dumps()` raises `TypeError: Object of type datetime is not JSON serializable`, aborting checkpoint creation and crashing the run.

## Evidence

- `src/elspeth/core/checkpoint/manager.py:91-96` uses plain `json.dumps()` on `aggregation_state` with no type handling.
```python
agg_json = json.dumps(aggregation_state, allow_nan=False) if aggregation_state is not None else None
```
- Aggregation checkpoint state explicitly stores raw row data dicts from `PipelineRow.to_dict()` and is intended for JSON serialization.
`src/elspeth/engine/executors.py:1549-1567`
```python
"row_data": t.row_data.to_dict(),  # Extract dict for JSON serialization
```
- `SchemaContract` allows `datetime` as a valid field type (so rows can legally contain datetimes).
`src/elspeth/contracts/schema_contract.py:29-38`

## Impact

- User-facing impact: Runs with aggregation + checkpointing can crash on valid input types (`datetime`).
- Data integrity / security impact: Crash recovery becomes unreliable; if workarounds stringify datetimes, resumes will violate Tier 2 “type-valid” guarantees.
- Performance or cost impact: Forced reruns, repeated processing, and manual intervention.

## Root Cause Hypothesis

- `CheckpointManager` assumes aggregation state is JSON-serializable, but aggregation buffers store raw `PipelineRow` data that can include `datetime` (explicitly allowed by schema contracts). This mismatch causes serialization errors or, if coerced, silent type degradation.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/core/checkpoint/manager.py` to use a type-preserving checkpoint serializer (e.g., datetime to ISO with explicit type tags), not raw `json.dumps`.
  - Ensure the same serializer is used wherever aggregation state is size-checked or deserialized (e.g., `src/elspeth/engine/executors.py` and recovery paths) so round-trip fidelity is maintained.
- Config or schema changes: None.
- Tests to add/update:
  - Add a checkpoint test where buffered rows include `datetime`; assert checkpoint creation and restore succeed with type fidelity.
- Risks or migration steps:
  - Migration required for existing checkpoints if serialization format changes; document format versioning for aggregation state.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` (Tier 2 pipeline data must retain validated types; no coercion downstream).
- Observed divergence: Checkpoint serialization either fails or would coerce `datetime` to strings without restoration, violating type fidelity for pipeline data.
- Reason (if known): Checkpoint serialization was implemented with `json.dumps` for simplicity without a type-preserving encoding.
- Alignment plan or decision needed: Define a checkpoint serialization contract that preserves allowed schema types and update both serialization and restore paths accordingly.

## Acceptance Criteria

- Checkpoints can be created when aggregation buffers contain `datetime` values.
- Recovery restores buffered rows with correct Python types (e.g., `datetime`, not string).
- Tests cover at least one non-JSON-native type in aggregation state.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/checkpoint/test_manager.py -v`
- New tests required: yes, add a checkpoint round-trip test with `datetime` in aggregation buffers.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Three-Tier Trust Model); `docs/architecture/landscape-audit-entry-points.md` (checkpoint subsystem)
