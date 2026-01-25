# Bug Report: Checkpoint Contract Allows NULL Topology Hashes

## Summary

- Checkpoint schema allows `topology_hash: str | None`, but NULL hash is never valid and masks audit database corruption.

## Severity

- Severity: trivial
- Priority: P3

## Reporter

- Name or handle: Branch Bug Scan
- Date: 2026-01-25
- Related run/issue ID: BUG-AUDIT-01

## Evidence

- `src/elspeth/contracts/audit.py` - Schema allows Optional topology hash

## Impact

- Schema tightening: NULL should be rejected at schema level

## Proposed Fix

- Change schema to `topology_hash: str` (required, not Optional)
- Add Alembic migration: `ALTER TABLE checkpoints ALTER COLUMN upstream_topology_hash SET NOT NULL`

## Acceptance Criteria

- Topology hash required in schema and database

## Tests

- New tests required: no (already covered by Bug #7 in consensus)

## Notes

- This bug is duplicate of Consensus Bug #7
- Already planned for Week 3 fixes
