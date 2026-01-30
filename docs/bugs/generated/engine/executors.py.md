# Bug Report: Sink flush failures leave sink node_states OPEN

## Summary

- If `sink.flush()` raises, `SinkExecutor.write()` propagates the exception without completing the per-token node_states, leaving OPEN states and no terminal outcomes.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic tokens with a sink whose `flush()` raises

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/executors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a sink whose `write()` succeeds but `flush()` raises (e.g., `RuntimeError("flush failed")`).
2. Call `SinkExecutor.write()` with at least one token.
3. Inspect node_states for those tokens in Landscape.

## Expected Behavior

- On `flush()` failure, all sink node_states are completed with `FAILED` status and error context; no artifact/outcome is recorded.

## Actual Behavior

- `flush()` exceptions bubble without any node_state completion, leaving OPEN states and no terminal outcomes.

## Evidence

- `sink.flush()` is called outside any try/except; only `sink.write()` failures are handled. `src/elspeth/engine/executors.py:1674-1698`
- This violates the “every row reaches exactly one terminal state” requirement. `CLAUDE.md:637-647`

## Impact

- User-facing impact: Run crashes with an exception but leaves rows in limbo.
- Data integrity / security impact: Audit trail gaps (OPEN states with no terminal outcome) contradict auditability guarantees.
- Performance or cost impact: Potential replay on resume with duplicated writes if the sink partially persisted data.

## Root Cause Hypothesis

- `SinkExecutor.write()` does not guard `sink.flush()` with failure recording logic, unlike `sink.write()`.

## Proposed Fix

- Code changes (modules/files):
  - Wrap `sink.flush()` in a try/except that completes all token node_states with `FAILED` and includes error details, then re-raises. `src/elspeth/engine/executors.py`
- Config or schema changes: None
- Tests to add/update:
  - Add a test in `tests/engine/test_sink_executor.py` to assert `flush()` exceptions mark all sink node_states as `FAILED` and do not register artifact/outcome.
- Risks or migration steps:
  - Ensure error path does not register artifacts or outcomes on flush failure.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:637-647` (Terminal Row States)
- Observed divergence: Rows can be left without any terminal state when flush fails.
- Reason (if known): Missing error handling around `sink.flush()`.
- Alignment plan or decision needed: Treat flush failure as a sink failure and complete node_states as `FAILED`.

## Acceptance Criteria

- A `sink.flush()` exception results in `NodeStateStatus.FAILED` for every token’s sink node_state.
- No OPEN node_states remain after a flush failure.
- No artifact or token outcomes are recorded when flush fails.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_sink_executor.py -k flush`
- New tests required: yes, add flush-failure coverage

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:637-647`
---
# Bug Report: Config gate MissingEdgeError leaves node_state OPEN

## Summary

- `execute_config_gate()` can raise `MissingEdgeError` from `_record_routing()` after opening a node_state but before completion, leaving an OPEN state and no terminal status.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Config gate with routes + empty edge_map

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/executors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate `GateExecutor` with an empty `edge_map`.
2. Call `execute_config_gate()` for a config gate whose routes resolve to a sink.
3. Observe `MissingEdgeError` and inspect node_states for the token.

## Expected Behavior

- The node_state is completed as `FAILED` with error context before the exception is raised.

## Actual Behavior

- The node_state remains OPEN because `_record_routing()` raises before completion.

## Evidence

- `_record_routing()` is called without guarding `MissingEdgeError` in config gate routing paths. `src/elspeth/engine/executors.py:741-801`
- `_record_routing()` raises `MissingEdgeError` when edge_map lacks a label. `src/elspeth/engine/executors.py:847-866`
- Test comment acknowledges OPEN state for config gates in this scenario. `tests/engine/test_gate_executor.py:622-624`

## Impact

- User-facing impact: Failure cases leave partial audit records; operators see OPEN states without terminal outcomes.
- Data integrity / security impact: Violates audit trail completeness requirement.
- Performance or cost impact: Minimal direct cost, but complicates recovery and audit explanations.

## Root Cause Hypothesis

- `execute_config_gate()` does not catch `MissingEdgeError` from `_record_routing()` to complete the node_state.

## Proposed Fix

- Code changes (modules/files):
  - Wrap `_record_routing()` calls in `execute_config_gate()` with `try/except MissingEdgeError` to complete the node_state as `FAILED` before re-raising. `src/elspeth/engine/executors.py`
- Config or schema changes: None
- Tests to add/update:
  - Update `tests/engine/test_gate_executor.py` to assert config-gate missing-edge errors mark node_state `FAILED`.
- Risks or migration steps:
  - Ensure error path preserves current exception behavior (still raises) while closing node_state.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:637-647` (Terminal Row States)
- Observed divergence: Node_state remains OPEN on MissingEdgeError for config gates.
- Reason (if known): Exception thrown after begin_node_state with no completion in the error path.
- Alignment plan or decision needed: Treat missing edges as failures with explicit node_state completion.

## Acceptance Criteria

- `MissingEdgeError` in config gate routing results in `NodeStateStatus.FAILED` for the gate’s node_state.
- No OPEN node_states remain after missing-edge errors.
- Existing MissingEdgeError behavior (exception type/message) remains unchanged.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_gate_executor.py -k missing_edge`
- New tests required: yes, enforce FAILED status for config gate missing-edge case

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:637-647`
