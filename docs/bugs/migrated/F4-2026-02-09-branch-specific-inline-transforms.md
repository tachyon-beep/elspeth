## Summary

Allow branch-specific transform chains within fork paths, enabling per-branch processing before merge. Currently forked children skip directly to coalesce_step (`processor.py:1725`) — no intermediate transforms between fork gate and coalesce.

## Severity

- Severity: minimal
- Priority: P4
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-ya3x

## Details

Ref: `docs/plans/completed/2026-02-07-divert-audit-completeness.md` line 520.

## Blocked By

- `w2q7` — ELSPETH-NEXT (deferred to post-RC3)

## Affected Subsystems

- `engine/processor.py`
- `core/dag/`
