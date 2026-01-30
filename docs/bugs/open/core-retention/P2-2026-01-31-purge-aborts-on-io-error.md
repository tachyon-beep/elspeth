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

- `src/elspeth/core/retention/purge.py:343-350` - no try/except around I/O operations
- Code has `failed_refs` list but exceptions abort before populating it

## Impact

- User-facing impact: Partial purge with inconsistent grade updates
- Data integrity: Some refs purged, others not, grade not updated

## Proposed Fix

- Wrap I/O operations in try/except, collect failures, update grade for successful deletions

## Acceptance Criteria

- I/O errors don't abort entire purge
- Grade updates reflect actual state
