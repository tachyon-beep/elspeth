# Bug Report: expand_token records EXPANDED outcome before validating output contract lock

## Summary

- `TokenManager.expand_token()` calls `LandscapeRecorder.expand_token()` (which creates child tokens and records parent EXPANDED) before checking `output_contract.locked`, so an invalid (unlocked) contract can still produce audit-side effects before the method raises.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic pipeline with a transform returning `TransformResult.success_multi(..., contract=SchemaContract(..., locked=False))`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/tokens.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement or configure a transform that returns `TransformResult.success_multi(rows, contract=SchemaContract(mode="OBSERVED", fields=..., locked=False))`.
2. Run a pipeline in output_mode `transform` so `TokenManager.expand_token()` is called for multi-row outputs.
3. Observe the run raises `ValueError` about unlocked contract and inspect the audit DB: child tokens and parent EXPANDED outcome exist.

## Expected Behavior

- `expand_token()` should validate `output_contract.locked` before any database writes; if invalid, no child tokens or parent EXPANDED outcome should be recorded.

## Actual Behavior

- `expand_token()` records child tokens and parent EXPANDED outcome, then raises `ValueError` due to `output_contract.locked=False`, leaving partial audit artifacts.

## Evidence

- `src/elspeth/engine/tokens.py:341-356` shows `self._recorder.expand_token(...)` is called before the locked-contract guard, so side effects occur prior to validation.
- `src/elspeth/core/landscape/recorder.py:1180-1278` shows `expand_token()` inserts child tokens and records parent EXPANDED outcome in the database.

## Impact

- User-facing impact: Runs can fail with an exception while still recording expansion artifacts, complicating postmortem and recovery.
- Data integrity / security impact: Audit trail records EXPANDED outcomes and child tokens for a step that should have been rejected, violating audit precision expectations.
- Performance or cost impact: Minor additional DB writes and potential recovery overhead due to orphaned tokens.

## Root Cause Hypothesis

- Precondition (`output_contract.locked`) is validated after DB side effects, rather than before, allowing invalid state to be recorded.

## Proposed Fix

- Code changes (modules/files): Move the `output_contract.locked` check to the top of `TokenManager.expand_token()` in `src/elspeth/engine/tokens.py` before calling `self._recorder.expand_token(...)`.
- Config or schema changes: None.
- Tests to add/update: Add a unit test in `tests/engine/test_token_manager_pipeline_row.py` asserting that when `output_contract.locked` is `False`, `recorder.expand_token` is not called and no tokens/outcomes are created.
- Risks or migration steps: Low risk; behavior becomes stricter by preventing side effects on invalid contracts.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:11-19` (audit trail is source of truth; no inference).
- Observed divergence: Audit artifacts are recorded for an expansion that should be rejected by contract validation.
- Reason (if known): Validation occurs after DB writes.
- Alignment plan or decision needed: Validate all preconditions before recording audit artifacts.

## Acceptance Criteria

- `expand_token()` raises before any recorder calls when `output_contract.locked` is `False`.
- No child tokens or EXPANDED outcomes are present in the audit DB after the failure.
- Existing expansion behavior for valid, locked contracts is unchanged.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_token_manager_pipeline_row.py -k expand_token`
- New tests required: yes, add a regression test for unlocked-contract expansion.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` auditability principles
