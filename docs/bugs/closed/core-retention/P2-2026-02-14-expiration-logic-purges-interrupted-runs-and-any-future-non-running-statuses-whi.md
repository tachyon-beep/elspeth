## Summary

Expiration logic purges `interrupted` runs (and any future non-`running` statuses), which conflicts with resume semantics for interrupted runs.

## Severity

- Severity: critical
- Priority: P1 (upgraded from P2 — silent irreversible data loss; purged payloads permanently break resume for interrupted runs; code contradicts its own documentation)

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/retention/purge.py
- Line(s): 145-149, 156-160 (also 98-101 in `find_expired_row_payloads`)
- Function/Method: `find_expired_payload_refs` (and `find_expired_row_payloads`)

## Evidence

Purge eligibility is defined as `runs.status != "running"`:

```python
run_expired_condition = and_(
    runs_table.c.status != "running",
    runs_table.c.completed_at.isnot(None),
    runs_table.c.completed_at < cutoff,
)
```

Source: `/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py:145-149`.

But nearby comments claim only completed/failed are eligible:
`/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py:143-144` and `:89-90`.

Resume logic explicitly treats `INTERRUPTED` as resumable:
`/home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py:103-104`, and orchestrator marks interrupted runs as resumable:
`/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:869-871`, `:1953-1955`.

If payloads are purged, resume fails:
`/home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py:243`.

## Root Cause Hypothesis

The filter uses a broad negative predicate (`!= "running"`) instead of an explicit allowlist of purge-eligible terminal statuses, likely predating `INTERRUPTED` run-state semantics.

## Suggested Fix

Use explicit purge-eligible statuses in `purge.py` (for example `completed` and `failed`) and treat `interrupted` as active/non-purgeable until resumed or explicitly finalized another way.
Also add a test covering interrupted-run retention behavior in `tests/unit/core/retention/test_purge.py`.

## Impact

Payloads for interrupted runs can be deleted by retention, causing resumable runs to become non-resumable and breaking recovery workflows unexpectedly.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/retention/purge.py.md`
- Finding index in source report: 2
- Beads: pending
