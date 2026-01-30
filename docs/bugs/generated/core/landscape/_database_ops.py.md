# Bug Report: execute_fetchone silently truncates multi-row results, hiding audit DB anomalies

## Summary

- `DatabaseOps.execute_fetchone()` uses `result.fetchone()`, which returns the first row even if the query yields multiple rows, masking data corruption or query bugs in the Tier‑1 audit database instead of crashing.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: de0ca01d55d988eca8b20f7aec17af733f8ad8b5
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/core/landscape/_database_ops.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Execute `DatabaseOps.execute_fetchone()` with a query that returns multiple rows (e.g., a SELECT missing a uniqueness filter or a join that multiplies rows).
2. Observe that no error is raised and only the first row is returned.

## Expected Behavior

- The call should raise on multiple rows (e.g., `MultipleResultsFound`) to crash immediately on audit DB anomalies, per Tier‑1 trust rules.

## Actual Behavior

- The first row is returned silently; extra rows are ignored, hiding corruption or query bugs.

## Evidence

- `src/elspeth/core/landscape/_database_ops.py:25-29` uses `result.fetchone()` without enforcing single-row semantics.
- `CLAUDE.md:34-41` mandates that bad data in the audit trail must crash immediately with no silent recovery.

## Impact

- User-facing impact: Incorrect or inconsistent lineage/explain output if a query unexpectedly returns multiple rows.
- Data integrity / security impact: Silent corruption is possible in the audit trail, violating legal/auditability guarantees.
- Performance or cost impact: Low direct cost, but can lead to expensive forensic/debugging effort later.

## Root Cause Hypothesis

- `execute_fetchone()` uses `fetchone()` instead of `one_or_none()`/`one()`, so it never detects multi-row results.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/core/landscape/_database_ops.py` to use `result.one_or_none()` in `execute_fetchone()` (or raise on `MultipleResultsFound`).
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit test that verifies `execute_fetchone()` raises when a query returns more than one row.
- Risks or migration steps:
  - Low risk if callers expect uniqueness; if any caller relied on “first row wins,” it should be updated to use `execute_fetchall()` or an explicit `.limit(1)`.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:34-41`
- Observed divergence: Silent truncation of multi-row results instead of crashing on Tier‑1 audit DB anomalies.
- Reason (if known): Convenience use of `fetchone()` without enforcing uniqueness.
- Alignment plan or decision needed: Enforce single-row semantics in `execute_fetchone()` and add a targeted test.

## Acceptance Criteria

- `execute_fetchone()` raises on multi-row results.
- Existing callers that expect zero-or-one row continue to work.
- New test passes and demonstrates the crash on multi-row results.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, add a unit test for multi-row detection in `execute_fetchone()`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier‑1 trust model)
