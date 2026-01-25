# Bug Report: Resume compatibility ignores non-ancestor branches in multi-sink DAGs

## Summary

- Checkpoint compatibility validation only hashes the ancestors of the checkpoint node (a sink), so changes to other sink branches are ignored, allowing resume with mixed pipeline configurations inside a single run.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: 8635789 (fix/rc1-bug-burndown-session-4)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic DAG with a gate routing to sink_a and sink_b

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `compatibility.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Build a graph with a gate that routes to sink_a and sink_b, and create a checkpoint for a row that routes to sink_a.
2. Modify only the transform or sink config in the sink_b branch (nodes not in sink_a’s ancestor set).
3. Call `CheckpointCompatibilityValidator.validate(checkpoint, modified_graph)`.

## Expected Behavior

- Resume should be rejected because the pipeline configuration changed for a branch that can still process unprocessed rows, breaking run-level configuration consistency.

## Actual Behavior

- Validator returns `can_resume=True` because it only compares the upstream topology for the checkpoint’s sink branch.

## Evidence

- `src/elspeth/core/checkpoint/compatibility.py:76` computes the topology hash using `checkpoint.node_id`, scoping validation to a single node’s ancestors.
- `src/elspeth/core/canonical.py:188` uses `nx.ancestors` to build the upstream subgraph, excluding other branches not leading to the checkpoint node.
- `src/elspeth/engine/orchestrator.py:150` documents checkpoints are created after sink writes and `node_id` is the sink node, so the checkpoint is tied to a single sink branch.

## Impact

- User-facing impact: Resume can proceed despite config changes on other branches, producing inconsistent outputs within the same run_id.
- Data integrity / security impact: Auditability is compromised because a single run contains decisions made under different pipeline configurations.
- Performance or cost impact: Potential rework and reprocessing if inconsistent results are detected later.

## Root Cause Hypothesis

- Compatibility validation compares only the upstream topology for the checkpoint’s sink node, which omits other sink branches in multi-sink DAGs.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/core/checkpoint/compatibility.py`: Validate full DAG topology (or all sink branches) rather than only ancestors of `checkpoint.node_id`.
  - `src/elspeth/core/checkpoint/manager.py`: Persist a full-graph topology hash (or per-sink hashes) at checkpoint creation.
  - `src/elspeth/core/canonical.py`: Add a `compute_full_topology_hash` (or per-sink hash aggregation) helper.
- Config or schema changes: Add a new checkpoint column for full-graph topology hash (or a structured per-sink hash map).
- Tests to add/update:
  - Add a test where checkpoint is at sink_a and a change occurs only on sink_b branch; validation must fail.
- Risks or migration steps:
  - Existing checkpoints without the new hash should be rejected (consistent with No Legacy Code Policy).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:13`
- Observed divergence: Resume validation allows a run to continue even though parts of the pipeline configuration differ from the original run.
- Reason (if known): Compatibility check is scoped to a single sink’s ancestor subgraph rather than the full DAG.
- Alignment plan or decision needed: Require a full-DAG topology hash in checkpoints or reject resume when other sink branches exist and are not validated.

## Acceptance Criteria

- Resume is rejected if any non-ancestor branch (e.g., another sink path) changes after the checkpoint.
- A new test covering multi-sink branch changes fails on current behavior and passes after the fix.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/checkpoint/test_compatibility_validator.py`
- New tests required: yes, add multi-sink branch change detection case

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:13`
