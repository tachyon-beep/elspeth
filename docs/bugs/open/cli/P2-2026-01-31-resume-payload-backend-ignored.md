# Bug Report: Resume ignores payload_store.backend and always uses FilesystemPayloadStore

## Summary

- `elspeth resume` instantiates `FilesystemPayloadStore` without validating `payload_store.backend`, so non-filesystem backends are ignored and resume may read the wrong storage or fail unexpectedly.

## Severity

- Severity: moderate
- Priority: P2

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31

## Evidence

- `src/elspeth/cli.py:1717-1725` - `resume()` instantiates `FilesystemPayloadStore` without checking `payload_store.backend`.
- `src/elspeth/cli.py:526-534` - `run()` explicitly validates `payload_store.backend == "filesystem"` before instantiating the payload store.

## Impact

- User-facing impact: Confusing resume failures when backend is not filesystem
- Data integrity: Could resume against incorrect payloads if local directory exists

## Proposed Fix

- Add backend validation guard in `resume()` mirroring the `run()` check

## Acceptance Criteria

- `elspeth resume` exits with explicit error if `payload_store.backend` is not `filesystem`

## Verification (2026-02-01)

**Status: STILL VALID**

- `resume()` still skips backend validation and always constructs `FilesystemPayloadStore`. (`src/elspeth/cli.py:1717-1725`)
