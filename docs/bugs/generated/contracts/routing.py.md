# Bug Report: RoutingAction allows CONTINUE with COPY mode, violating routing contract and audit semantics

## Summary

- `RoutingAction.__post_init__` does not reject `RoutingKind.CONTINUE` with `RoutingMode.COPY`, despite the contract stating COPY is only valid for `FORK_TO_PATHS`, allowing invalid actions that record COPY routing without creating child tokens.

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
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit on `src/elspeth/contracts/routing.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. In a gate plugin, construct `RoutingAction(kind=RoutingKind.CONTINUE, destinations=(), mode=RoutingMode.COPY)`.
2. Run the gate through the executor path that records routing events.

## Expected Behavior

- `RoutingAction` should reject `CONTINUE` with `COPY` (or coerce to `MOVE`), since COPY is only valid for `FORK_TO_PATHS`.

## Actual Behavior

- The action is accepted, and the executor records a routing event with COPY mode for a continue edge, without creating child tokens.

## Evidence

- Contract statement that COPY is only valid for `FORK_TO_PATHS`, but no invariant enforces this for CONTINUE: `src/elspeth/contracts/routing.py:35-51,59-76`.
- Executor records routing with `action.mode` even for CONTINUE, so COPY is persisted without any fork: `src/elspeth/engine/executors.py:534-541`.

## Impact

- User-facing impact: Audit and explain outputs can show COPY routing on a continue edge, implying fork semantics that never occurred.
- Data integrity / security impact: Audit trail integrity is degraded; recorded routing mode can contradict actual token lineage.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Missing invariant check in `RoutingAction.__post_init__` to enforce `RoutingKind.CONTINUE` must use `RoutingMode.MOVE` (or to forbid COPY for any kind other than `FORK_TO_PATHS`).

## Proposed Fix

- Code changes (modules/files):
  - Add validation in `src/elspeth/contracts/routing.py` to reject `RoutingKind.CONTINUE` with `RoutingMode.COPY` (or enforce COPY only for `FORK_TO_PATHS`).
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit test in `tests/contracts/test_routing.py` asserting `RoutingAction(kind=CONTINUE, mode=COPY)` raises `ValueError`.
  - Add a property test in `tests/property/engine/test_executor_properties.py` to ensure invariants reject COPY outside forks.
- Risks or migration steps:
  - Potentially breaks any internal plugin currently constructing invalid CONTINUE+COPY; those plugins should be fixed to use `continue_()` or MOVE.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/routing.py:35-38`
- Observed divergence: COPY is allowed for CONTINUE by omission of validation.
- Reason (if known): Missing invariant enforcement for CONTINUE in `__post_init__`.
- Alignment plan or decision needed: Add explicit validation to enforce COPY only for `FORK_TO_PATHS`.

## Acceptance Criteria

- Creating `RoutingAction` with `kind=CONTINUE` and `mode=COPY` raises `ValueError`.
- No routing event is recorded with COPY mode for continue edges.
- Tests added/updated to cover this invariant.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_routing.py`
- New tests required: yes, add a unit test for CONTINUE+COPY rejection and a property test for invariants.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/routing.py`
