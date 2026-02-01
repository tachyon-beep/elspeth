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

- `src/elspeth/core/retention/purge.py:94-96` and `137-141` - uses `status == "completed"` to define expired runs.
- Failed runs older than retention cutoff are excluded from purge

## Impact

- User-facing impact: Unbounded storage growth for failed runs
- Data integrity: None

## Proposed Fix

- Include failed runs (status != "running") in purge eligibility

## Acceptance Criteria

- Failed runs older than retention period are eligible for payload purge

## Verification (2026-02-01)

**Status: STILL VALID**

- Expired-run checks still require `status == "completed"`, and `status != "completed"` is treated as active. (`src/elspeth/core/retention/purge.py:94-96`, `src/elspeth/core/retention/purge.py:137-152`)
