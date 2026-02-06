# Bug Report: Late-arrival coalesce failures miss immediate token outcome recording

## Summary

- Late-arriving tokens after a coalesce merge record a failed node state but do not record a terminal token outcome inside `CoalesceExecutor`, creating an audit gap and a crash window before the caller records the outcome.

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
- Data set or fixture: Any pipeline with coalesce and a late-arriving branch token

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/coalesce_executor.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a coalesce point (e.g., `require_all` or `quorum`) and run a pipeline where a merge completes before all branches arrive.
2. After the merge completes, deliver a late-arriving token for the same `(coalesce_name, row_id)` so it hits the late-arrival path in `CoalesceExecutor.accept()`.

## Expected Behavior

- The late-arriving token should have both a failed node state and a terminal token outcome recorded **immediately in `CoalesceExecutor`**, with `CoalesceOutcome.outcomes_recorded=True` to prevent duplicate recording.

## Actual Behavior

- The late-arrival path records a failed node state but does **not** record a token outcome, relying on the caller to record it later. This creates a crash window where the run can persist a failed node state without a terminal outcome.

## Evidence

- Late-arrival path completes a node state but never calls `record_token_outcome()` and does not set `outcomes_recorded=True`:
  `src/elspeth/engine/coalesce_executor.py:207-235`
- Architecture reference explicitly expects `record_token_outcome(FAILED)` on late arrivals:
  `docs/architecture/landscape-audit-entry-points.md:346-348`

## Impact

- User-facing impact: Late-arriving tokens may appear failed in node state but lack terminal outcomes if a crash occurs before the caller records the outcome.
- Data integrity / security impact: Violates the “every token reaches exactly one terminal state” audit invariant for late arrivals.
- Performance or cost impact: Minimal, but potential reprocessing/diagnosis overhead in audit investigations.

## Root Cause Hypothesis

- The late-arrival branch in `CoalesceExecutor.accept()` omits `record_token_outcome()` and does not flag `outcomes_recorded=True`, unlike other coalesce failure paths.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/coalesce_executor.py`: In the late-arrival branch, compute `error_hash`, call `self._recorder.record_token_outcome(..., outcome=RowOutcome.FAILED, error_hash=error_hash)`, and set `outcomes_recorded=True` in the returned `CoalesceOutcome`.
- Config or schema changes: None.
- Tests to add/update:
  - Add/extend a coalesce executor test to assert that late-arrival failures record a `FAILED` token outcome and set `outcomes_recorded=True`.
- Risks or migration steps:
  - Low risk; ensure processor does not double-record outcomes when `outcomes_recorded=True`.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/architecture/landscape-audit-entry-points.md:346-348`
- Observed divergence: Late-arrival path does not call `record_token_outcome(FAILED)` as documented.
- Reason (if known): Missing implementation in the late-arrival branch.
- Alignment plan or decision needed: Add outcome recording and mark `outcomes_recorded=True`.

## Acceptance Criteria

- Late-arrival tokens produce both a failed node state and a terminal `FAILED` token outcome recorded by `CoalesceExecutor`.
- `CoalesceOutcome.outcomes_recorded` is `True` for late-arrival failures to avoid duplicate recording by the caller.
- Test coverage verifies the audit trail for late arrivals.

## Tests

- Suggested tests to run: `pytest tests/engine/test_coalesce_executor.py -k late_arrival -v`
- New tests required: yes, add a late-arrival outcome recording test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/architecture/landscape-audit-entry-points.md`
