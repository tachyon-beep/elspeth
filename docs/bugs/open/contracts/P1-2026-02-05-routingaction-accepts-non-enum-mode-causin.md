# Bug Report: RoutingAction Accepts Non-Enum `mode`, Causing Uncaught TypeError and OPEN NodeState

## Summary

- `RoutingAction.__post_init__` does not validate that `mode` is a `RoutingMode` enum, so `RoutingAction.route(..., mode="move")` succeeds; later `record_routing_event` builds a `RoutingEvent` that strictly validates enums and raises `TypeError`, which is **not** caught by `GateExecutor`, leaving the node_state OPEN and routing_events missing.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074e (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline with a gate plugin returning `RoutingAction.route(..., mode="move")` (string mode)

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/contracts/routing.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a gate plugin that returns `RoutingAction.route("review", mode="move")` (string, not `RoutingMode.MOVE`).
2. Run any pipeline that executes this gate.
3. Observe the run crash during routing event recording and inspect the audit DB: the gate `node_state` remains OPEN and no `routing_events` are recorded for the decision.

## Expected Behavior

- Invalid `mode` types are rejected at `RoutingAction` construction time (within gate evaluation), so `GateExecutor` can mark the node_state as FAILED with a clear error and no OPEN node_states remain.

## Actual Behavior

- `RoutingAction` accepts `mode="move"` because `__post_init__` only checks copy/move invariants and not type.
- `LandscapeRecorder.record_routing_event()` builds a `RoutingEvent` that validates `mode` and raises `TypeError`.
- `GateExecutor` does not catch `TypeError`, so the node_state is left OPEN and routing events are not recorded.

## Evidence

- `RoutingAction.__post_init__` has invariant checks but **no enum type validation** for `mode`.
  `src/elspeth/contracts/routing.py:63-83`
- `RoutingEvent.__post_init__` enforces enum type and raises `TypeError` on non-enum.
  `src/elspeth/contracts/audit.py:324-327` and `_validate_enum` at `src/elspeth/contracts/audit.py:31-39`
- `GateExecutor.execute_gate()` only catches `MissingEdgeError`, `RuntimeError`, and `ValueError`, **not** `TypeError`.
  `src/elspeth/engine/executors.py:628-709`

## Impact

- User-facing impact: Pipeline crashes during gate routing when a plugin passes a string `mode`.
- Data integrity / security impact: Audit trail integrity violation—node_state remains OPEN with no terminal status or routing_events, violating “no silent drops / complete audit trail.”
- Performance or cost impact: Run aborts; potential re-run cost.

## Root Cause Hypothesis

- `RoutingAction` does not validate `mode` is a `RoutingMode` enum. Invalid values (e.g., `"move"`) pass through and trigger a `TypeError` inside `RoutingEvent` construction, which is not caught in `GateExecutor`, leaving OPEN node_states.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/contracts/routing.py`: add strict enum validation in `RoutingAction.__post_init__` (e.g., `if not isinstance(self.mode, RoutingMode): raise TypeError(...)`) so invalid modes fail during gate evaluation and are recorded as node_state failures.
- Config or schema changes: None.
- Tests to add/update:
  - `tests/contracts/test_routing.py`: add test that `RoutingAction.route("x", mode="move")` raises `TypeError`.
  - Optional: test for `RoutingAction(kind=..., mode="move")` raising `TypeError`.
- Risks or migration steps:
  - Any plugins passing string `mode` must be fixed to pass `RoutingMode` enums (intentional strictness per audit rules).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:32` (“wrong type = crash” for audit-trail data)
- Observed divergence: `RoutingAction` allows non-enum `mode` values to proceed past contract boundaries, leading to unhandled type errors and incomplete audit state.
- Reason (if known): Missing enum type validation in `RoutingAction.__post_init__`.
- Alignment plan or decision needed: Enforce `RoutingMode` type at `RoutingAction` construction.

## Acceptance Criteria

- Constructing `RoutingAction` with non-`RoutingMode` `mode` raises immediately.
- A gate that returns invalid `RoutingAction` triggers a FAILED node_state (not OPEN) with a recorded error.
- No OPEN node_states are left due to invalid routing action types.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_routing.py`
- New tests required: yes, add explicit invalid-mode tests.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Data Manifesto: type violations must crash).
