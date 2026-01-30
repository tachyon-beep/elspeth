# Bug Report: Retention purge excludes failed runs, leaving their payloads undeletable

## Summary

- Purge uses `runs_table.c.status == "completed"` for expired condition, so failed runs are treated as "active" regardless of age.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/retention/purge.py:93` and lines 137-141 - uses `status == "completed"`
- Failed runs older than retention cutoff are excluded from purge

## Impact

- User-facing impact: Unbounded storage growth for failed runs
- Data integrity: None

## Proposed Fix

- Include failed runs (status != "running") in purge eligibility

## Acceptance Criteria

- Failed runs older than retention period are eligible for payload purge
