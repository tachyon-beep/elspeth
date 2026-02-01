# Bug Report: Purge aborts on payload-store I/O errors, skipping grade updates

## Summary

- Calls to `payload_store.exists()` and `payload_store.delete()` are not wrapped in try/except. An OSError or PermissionError aborts the purge loop.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/core/retention/purge.py:393-401` - no try/except around `exists()` / `delete()` I/O operations.
- Code has `failed_refs` list but exceptions abort before populating it

## Impact

- User-facing impact: Partial purge with inconsistent grade updates
- Data integrity: Some refs purged, others not, grade not updated

## Proposed Fix

- Wrap I/O operations in try/except, collect failures, update grade for successful deletions

## Acceptance Criteria

- I/O errors don't abort entire purge
- Grade updates reflect actual state

## Verification (2026-02-01)

**Status: STILL VALID**

- `purge_payloads()` still calls `exists()` / `delete()` without exception handling. (`src/elspeth/core/retention/purge.py:393-401`)
