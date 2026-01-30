# Bug Report: Sink flush exceptions leave node_states OPEN and omit terminal outcomes

## Summary

- `SinkExecutor.write()` does not handle exceptions from `sink.flush()`, so a flush failure leaves all previously opened sink node_states in OPEN status with no terminal outcome recorded, violating the audit trail’s terminal-state guarantees.

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
- Data set or fixture: Any pipeline using a sink whose `flush()` can raise (e.g., file fsync error, DB commit error)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/engine/executors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a sink whose `write()` succeeds but `flush()` raises (e.g., simulate I/O or DB commit failure).
2. Run a pipeline that writes at least one token through this sink.
3. Observe that the run crashes on `flush()`.

## Expected Behavior

- On `flush()` failure, all sink node_states opened for the tokens should be completed as FAILED with error details, preserving audit trail completeness (no OPEN states left behind).
- No token outcomes or artifacts should be recorded if durability is not confirmed.

## Actual Behavior

- `flush()` exceptions propagate without completing the sink node_states, leaving them OPEN and missing terminal outcome records.

## Evidence

- `SinkExecutor.write()` opens a node_state per token and only marks them FAILED inside the `sink.write()` try/except, not for `sink.flush()` failures: `src/elspeth/engine/executors.py:1663-1701`.
- `sink.flush()` is called outside any error handling, so an exception exits the method before node_states are completed or outcomes recorded: `src/elspeth/engine/executors.py:1703-1706`.
- This violates the terminal-state requirement in CLAUDE.md (“Every row reaches exactly one terminal state - no silent drops”): `CLAUDE.md` (Terminal Row States section).

## Impact

- User-facing impact: Pipeline crashes on flush failure with incomplete audit trail, making root-cause analysis and explainability harder.
- Data integrity / security impact: Audit trail becomes incomplete (OPEN node_states, no terminal outcome), violating ELSPETH’s auditability standard.
- Performance or cost impact: Potential reprocessing or manual reconciliation due to incomplete audit records.

## Root Cause Hypothesis

- Missing exception handling around `sink.flush()` in `SinkExecutor.write()`; the failure path does not complete node_states or record errors.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/executors.py`: wrap `sink.flush()` in try/except; on exception, complete all pending sink node_states with `NodeStateStatus.FAILED` and error details; then re-raise.
- Config or schema changes: None.
- Tests to add/update:
  - Unit test: `SinkExecutor.write()` with a sink that raises in `flush()` should mark all node_states as FAILED and not record outcomes or artifacts.
  - Integration test: pipeline run with flush failure leaves no OPEN sink node_states.
- Risks or migration steps:
  - Ensure failure path does not accidentally register artifacts or outcomes when `flush()` fails.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` “Terminal Row States” and “Auditability Standard”.
- Observed divergence: A `flush()` failure can leave node_states OPEN with no terminal outcome.
- Reason (if known): Missing error handling around `sink.flush()` in executor.
- Alignment plan or decision needed: Add failure handling to `sink.flush()` path to preserve audit invariants.

## Acceptance Criteria

- When `sink.flush()` raises, all sink node_states created in that call are completed with FAILED status and error details.
- No token outcomes or artifacts are recorded for the failed flush.
- No OPEN sink node_states remain after a flush failure.

## Tests

- Suggested tests to run: ` .venv/bin/python -m pytest tests/engine/test_sink_executor.py -k flush_failure`
- New tests required: yes, add flush-failure unit/integration coverage

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Auditability Standard; Terminal Row States)
