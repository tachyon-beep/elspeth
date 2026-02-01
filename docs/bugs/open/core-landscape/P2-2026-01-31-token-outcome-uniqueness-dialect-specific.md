# Bug Report: token_outcomes terminal uniqueness only enforced on SQLite/Postgres

## Summary

- The partial unique index for terminal token outcomes uses dialect-specific clauses (`sqlite_where`, `postgresql_where`). Other backends won't enforce terminal uniqueness.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/landscape/schema.py:157-165` - partial unique index uses dialect-specific clauses (`sqlite_where`, `postgresql_where`).
- Only SQLite and PostgreSQL get the constraint
- MySQL and other backends have no enforcement

## Impact

- User-facing impact: Could have duplicate terminal outcomes on non-SQLite/Postgres
- Data integrity: Uniqueness constraint not portable

## Proposed Fix

- Document SQLite/Postgres as only supported backends, or add application-level uniqueness check

## Acceptance Criteria

- Terminal uniqueness enforced on all supported backends

## Verification (2026-02-01)

**Status: STILL VALID**

- The terminal-uniqueness constraint remains dialect-specific to SQLite/Postgres. (`src/elspeth/core/landscape/schema.py:157-165`)
