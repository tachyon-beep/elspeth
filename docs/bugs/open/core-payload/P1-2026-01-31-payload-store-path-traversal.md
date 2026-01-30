# Bug Report: Unvalidated content_hash enables path traversal

## Summary

- FilesystemPayloadStore constructs filesystem paths directly from `content_hash` without validating that it is a SHA-256 hex digest, allowing path traversal and non-hash strings to reach `exists()`/`delete()`/`retrieve()`.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31
- Related run/issue ID: N/A

## Evidence

- Path construction uses raw `content_hash` without validation: `src/elspeth/core/payload_store.py:39-42`
- `exists()` and `delete()` call `_path_for_hash()` directly with no validation: `src/elspeth/core/payload_store.py:77-90`
- Contract requires `content_hash` to be a SHA-256 hex digest: `src/elspeth/contracts/payload_store.py:44-75`
- Audit tier rules require crashing on invalid audit data: `CLAUDE.md:34-41`

## Impact

- User-facing impact: Potentially misleading behavior (payload reported missing/purged when the ref is malformed)
- Data integrity / security impact: Path traversal allows `exists()`/`delete()` to touch files outside the payload store; violates audit integrity and trust assumptions
- Performance or cost impact: Minor

## Root Cause Hypothesis

- Missing validation and containment checks for `content_hash` in `_path_for_hash()` and the public methods that call it.

## Proposed Fix

- Code changes (modules/files):
  - Add strict validation (length 64, lowercase hex) for `content_hash` in `src/elspeth/core/payload_store.py`
  - Enforce `base_path` containment (e.g., `resolve()` and parent check) before filesystem access
- Tests to add/update:
  - New unit tests in `tests/core/test_payload_store.py` to assert invalid hashes raise immediately and cannot traverse outside the base path

## Acceptance Criteria

- Invalid `content_hash` values raise immediately without touching the filesystem
- Path traversal attempts cannot access or delete files outside `base_path`
- Tests for invalid hashes/path traversal pass
