## Summary

`GateExecutor.execute_config_gate()` can leave gate node states `OPEN` when non-`MissingEdgeError` exceptions occur during routing/dispatch.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/engine/executors/gate.py`
- Function/Method: `GateExecutor.execute_config_gate`

## Evidence

- Source report: `docs/bugs/generated/engine/executors/gate.py.md`
- `begin_node_state()` is called, but only narrow exception paths guarantee `complete_node_state(...FAILED...)`.

## Root Cause Hypothesis

Failure handling was hardened for missing edges but not generalized across dispatch/routing failures.

## Suggested Fix

Ensure any exception after state-open closes state as terminal failed before re-raise.

## Impact

Audit trail can contain non-terminal gate states with incomplete attribution.

## Triage

- Status: open
- Source report: `docs/bugs/generated/engine/executors/gate.py.md`
- Beads: elspeth-rapid-r826
