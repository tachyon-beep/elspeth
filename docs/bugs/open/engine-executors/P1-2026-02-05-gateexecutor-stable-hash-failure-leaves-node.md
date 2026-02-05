# Bug Report: GateExecutor stable_hash Failure Leaves Node State OPEN

## Summary

- GateExecutor computes `stable_hash(result.row)` without error handling; if the gate emits non-canonical data (NaN/Infinity or non-serializable types), an exception is raised after `begin_node_state()`, leaving the node state OPEN with no terminal status.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Gate that outputs non-canonical data (e.g., `float("nan")`) in `GateResult.row`

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/executors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a gate that returns `GateResult(row={"value": float("nan")}, action=RoutingAction.continue_())`.
2. Execute the pipeline and trigger the gate.
3. Inspect `node_states` for the gate state.

## Expected Behavior

- The gate’s node state should be completed with `FAILED` status and an error recorded when non-canonical output is produced.

## Actual Behavior

- `stable_hash(result.row)` raises, and the node state remains OPEN without a terminal status.

## Evidence

- `src/elspeth/engine/executors.py:618-621` calls `stable_hash(result.row)` without try/except or node_state completion.
- `CLAUDE.md:647-657` requires every row to reach exactly one terminal state, disallowing silent drops or open states.

## Impact

- User-facing impact: Pipeline crashes with incomplete audit records.
- Data integrity / security impact: Audit trail contains OPEN node states with no terminal status, violating auditability guarantees.
- Performance or cost impact: None.

## Root Cause Hypothesis

- GateExecutor lacks the same canonicalization error handling used by TransformExecutor/AggregationExecutor, so hash failures bypass node_state completion.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/executors.py`: wrap `stable_hash(result.row)` in try/except, record `NodeStateStatus.FAILED`, and raise a `PluginContractViolation` with context.
- Config or schema changes: None.
- Tests to add/update:
  - Add a GateExecutor test that emits NaN and asserts the node_state is marked FAILED.
- Risks or migration steps:
  - None; change is localized to gate error handling.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:647-657`
- Observed divergence: Node states can be left OPEN when gate output hashing fails.
- Reason (if known): Missing error handling around `stable_hash` for gate outputs.
- Alignment plan or decision needed: Align gate hashing error handling with TransformExecutor’s approach.

## Acceptance Criteria

- Gate outputs that fail canonicalization always result in a FAILED node_state with error details, and no OPEN states are left behind.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_gate_executor.py -k non_canonical`
- New tests required: yes, add a gate canonicalization failure test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
