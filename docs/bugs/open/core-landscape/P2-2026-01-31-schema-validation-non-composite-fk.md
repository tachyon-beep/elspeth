# Bug Report: Schema validation accepts non-composite FK to nodes for error tables

## Summary

- `_REQUIRED_FOREIGN_KEYS` only checks single-column FKs, not the composite `(node_id, run_id)` requirement for nodes table references.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/landscape/database.py:39-43` - `_REQUIRED_FOREIGN_KEYS` only checks single-column FKs
- Nodes table has composite PK `(node_id, run_id)` per CLAUDE.md
- Validation doesn't enforce composite FK requirement

## Impact

- User-facing impact: Stale SQLite databases could have invalid schema
- Data integrity: FK validation incomplete

## Proposed Fix

- Add composite FK validation for tables referencing nodes

## Acceptance Criteria

- Schema validation detects missing composite FK to nodes table
