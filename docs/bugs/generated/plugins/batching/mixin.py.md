# Bug Report: Release loop exception path uses uninitialized token/state_id, causing UnboundLocalError and waiter timeouts

## Summary

- `_release_loop` assumes `token`/`state_id` are set in its exception handler, but exceptions from `wait_for_next_release()` can occur before assignment, triggering `UnboundLocalError` and leaving waiters to time out instead of surfacing the real bug.

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
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/plugins/batching/mixin.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a batch transform using `BatchTransformMixin` whose worker `processor` returns `None` (or otherwise causes `RowReorderBuffer.wait_for_next_release()` to raise a non-Timeout/Shutdown exception).
2. Call `accept()` and wait via `SharedBatchAdapter.RowWaiter.wait()`.

## Expected Behavior

- The buffer invariant violation should surface as an immediate exception (crash) or be propagated to the waiter; no secondary `UnboundLocalError`, no misleading timeout.

## Actual Behavior

- `_release_loop` catches the exception, then references `token`/`state_id` that were never assigned, raising `UnboundLocalError`. The release thread dies, and the waiter times out, masking the real error.

## Evidence

- Exception handler uses `token`/`state_id` even when `wait_for_next_release()` fails before assignment: `src/elspeth/plugins/batching/mixin.py:262`, `src/elspeth/plugins/batching/mixin.py:287`, `src/elspeth/plugins/batching/mixin.py:299`.

## Impact

- User-facing impact: Transforms appear to “hang” and eventually time out; root cause is obscured.
- Data integrity / security impact: Audit trail records a timeout instead of the real failure, breaking “no inference” traceability.
- Performance or cost impact: Retry/timeout loops waste time and compute.

## Root Cause Hypothesis

- The exception handler in `_release_loop` assumes `token` and `state_id` are always available, but exceptions from `wait_for_next_release()` can occur before `entry.result` is unpacked.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/batching/mixin.py`: split the `try` block so `wait_for_next_release()` exceptions are handled separately; only emit `ExceptionResult` when `token`/`state_id` are known. Otherwise re-raise to crash fast.
- Config or schema changes: Unknown
- Tests to add/update:
  - Unit test that forces `wait_for_next_release()` to raise (e.g., processor returns `None`), asserting the error propagates and no `UnboundLocalError` occurs.
- Risks or migration steps:
  - Low; behavior becomes fail-fast for internal invariants.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` (Plugin ownership: plugin bugs must crash)
- Observed divergence: Release loop turns internal invariant failures into timeouts due to secondary `UnboundLocalError`.
- Reason (if known): Exception handler assumes `entry.result` is always available.
- Alignment plan or decision needed: Ensure fail-fast behavior for internal invariant violations.

## Acceptance Criteria

- Exceptions from `wait_for_next_release()` propagate without `UnboundLocalError`.
- Waiters do not time out when a buffer invariant is violated; the original exception is surfaced.

## Tests

- Suggested tests to run: `./.venv/bin/python -m pytest tests/ -k batch_release_loop`
- New tests required: yes, cover release-loop exception path when no `token`/`state_id` is available.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
