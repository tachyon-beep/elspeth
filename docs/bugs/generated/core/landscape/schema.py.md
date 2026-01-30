# Bug Report: token_outcomes terminal uniqueness only enforced on SQLite/Postgres

## Summary

- The schema enforces “one terminal outcome per token” only via a partial unique index limited to SQLite/Postgres, leaving other backends without the required constraint and breaking the token outcome contract (BUFFERED → terminal).

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 17f7293805c0c36aa59bf5fad0f09e09c3035fc9
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any run with aggregation that records BUFFERED then terminal outcomes

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for /home/john/elspeth-rapid/src/elspeth/core/landscape/schema.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Use a non-SQLite/Postgres backend (e.g., MySQL) and create the Landscape schema from `metadata`.
2. Insert a BUFFERED outcome for a token (is_terminal=0).
3. Insert the terminal outcome for the same token (is_terminal=1).
4. Observe that the constraint either blocks the terminal insert (if the index is created as a full unique index) or allows multiple terminal outcomes (if no partial enforcement is created).

## Expected Behavior

- The database should allow exactly one non-terminal (BUFFERED) outcome and exactly one terminal outcome per token, and should always prevent multiple terminal outcomes across all supported backends.

## Actual Behavior

- On backends that do not support partial indexes, the “terminal only” uniqueness is not enforced as intended, which can either block valid BUFFERED → terminal transitions or allow multiple terminal outcomes, violating the audit contract.

## Evidence

- `src/elspeth/core/landscape/schema.py:156-163` — Partial unique index is scoped only to SQLite/Postgres via `sqlite_where`/`postgresql_where`.
- `docs/audit-trail/tokens/00-token-outcome-contract.md:29-33` — Contract requires BUFFERED to be followed by exactly one terminal outcome and notes enforcement via partial unique index.
- `src/elspeth/core/landscape/recorder.py:2097-2119` — Recorder explicitly records a second (terminal) outcome after BUFFERED and expects DB-level enforcement to prevent duplicate terminals.

## Impact

- User-facing impact: Aggregation workflows can fail at terminal outcome recording or produce ambiguous terminal states on non-SQLite/Postgres backends.
- Data integrity / security impact: Violates the audit invariant “exactly one terminal outcome per token,” weakening audit trail integrity.
- Performance or cost impact: Potential retry storms or failed runs due to IntegrityError in aggregation paths.

## Root Cause Hypothesis

- The uniqueness constraint is implemented as a dialect-specific partial index, but the schema provides no cross-dialect fallback. For backends lacking partial index support, the constraint is either too strict (full unique) or absent, breaking the contract.

## Proposed Fix

- Code changes (modules/files):
  - Add a backend-agnostic constraint in `src/elspeth/core/landscape/schema.py` to enforce uniqueness across `(token_id, is_terminal)` for all DBs, or split terminal outcomes into a separate table with a strict unique constraint on `token_id`.
  - Keep or remove the partial index as appropriate; if retained, ensure it doesn’t conflict with the cross-dialect constraint.
- Config or schema changes: Add a migration to enforce the new uniqueness guarantee on existing databases.
- Tests to add/update:
  - Add a schema-level test that inserts BUFFERED then terminal outcomes for the same token and asserts success, while inserting a second terminal outcome fails.
  - Add a backend-agnostic test (or at least one additional backend) to ensure the constraint works outside SQLite/Postgres.
- Risks or migration steps:
  - Existing data with multiple terminal outcomes must be remediated before adding the new constraint.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/audit-trail/tokens/00-token-outcome-contract.md:29-33`
- Observed divergence: Contract requires a single terminal outcome per token and depends on a partial unique index; schema only enforces this on SQLite/Postgres.
- Reason (if known): Dialect-specific index definition without a cross-dialect fallback.
- Alignment plan or decision needed: Decide on a backend-agnostic uniqueness strategy for token outcomes and apply it universally.

## Acceptance Criteria

- Recording BUFFERED then terminal outcomes succeeds across all supported backends.
- Attempting a second terminal outcome for the same token fails with a constraint violation across all supported backends.
- No backend-specific behavior diverges from the token outcome contract.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_token_outcomes.py` (or equivalent audit/landscape test suite)
- New tests required: yes, add cross-backend or schema-level tests for token_outcomes uniqueness

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/audit-trail/tokens/00-token-outcome-contract.md`
