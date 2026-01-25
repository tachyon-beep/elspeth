# Bug Report: token_outcomes lacks DB constraints for outcome/is_terminal enum integrity

## Summary

- `token_outcomes` allows invalid `outcome` values and non-boolean `is_terminal`, enabling audit records that violate Tier 1 invariants and can be silently misclassified on read

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: 86357898ee109a1dbb8d60f3dc687983fa22c1f0
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `/home/john/elspeth-rapid/src/elspeth/core/landscape/schema.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Insert a `token_outcomes` row with `outcome='not_a_real_outcome'` or `is_terminal=2` (using valid `run_id` and `token_id`).
2. Observe the insert succeeds because the schema lacks a check constraint.
3. Fetch via `LandscapeRecorder.get_token_outcome()` and note either a `ValueError` on invalid `outcome` or a silent misclassification of `is_terminal`.

## Expected Behavior

- Database rejects invalid `outcome` values and non-boolean `is_terminal` at insert time, preventing invalid audit records from existing.

## Actual Behavior

- Database accepts invalid values; invalid `outcome` crashes on read, and invalid `is_terminal` is silently treated as non-terminal.

## Evidence

- `token_outcomes` defines `outcome` and `is_terminal` without any check constraints: `src/elspeth/core/landscape/schema.py:123`, `src/elspeth/core/landscape/schema.py:124`
- Design doc shows expected `CheckConstraint` for `outcome`: `docs/plans/completed/2026-01-21-AUD-001-token-outcomes-design.md:70`
- Tier 1 trust requires invalid enum values to be treated as audit integrity violations: `CLAUDE.md:40`
- Recorder comment asserts `is_terminal` must be 0 or 1 but no enforcement exists: `src/elspeth/core/landscape/recorder.py:2299`

## Impact

- User-facing impact: explain/export may crash or misreport token terminality when bad values exist.
- Data integrity / security impact: audit DB can contain invalid terminal state records, violating “no inference” standards.
- Performance or cost impact: Unknown

## Root Cause Hypothesis

- `token_outcomes` schema was added without enforcing enum/boolean constraints; `is_terminal` shifted to Integer for SQLite but no range constraint was added.

## Proposed Fix

- Code changes (modules/files):
  - Add `CheckConstraint` to `token_outcomes.outcome` for `RowOutcome` values in `src/elspeth/core/landscape/schema.py`.
  - Add `CheckConstraint` enforcing `is_terminal IN (0, 1)` (or use Boolean with equivalent constraint) in `src/elspeth/core/landscape/schema.py`.
- Config or schema changes: add/extend Alembic migration to introduce these constraints.
- Tests to add/update:
  - Add a schema test that attempts inserts with invalid `outcome` and `is_terminal` and asserts `IntegrityError`.
- Risks or migration steps:
  - Existing DBs may contain invalid values; migration should validate and fail or remediate before enforcing constraints.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/completed/2026-01-21-AUD-001-token-outcomes-design.md:70`
- Observed divergence: `token_outcomes` lacks the documented check constraint for `outcome`, and `is_terminal` has no boolean-range enforcement.
- Reason (if known): Unknown
- Alignment plan or decision needed: add check constraints and migration, then validate existing DBs.

## Acceptance Criteria

- Inserts with invalid `outcome` or `is_terminal` values are rejected by the database.
- `token_outcomes` rows always map cleanly to `RowOutcome` and boolean terminality without silent coercion.

## Tests

- Suggested tests to run: `pytest tests/core/test_token_outcomes.py`
- New tests required: yes, add constraint enforcement tests for `token_outcomes`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-01-21-AUD-001-token-outcomes-design.md`
