# Bug Report: Unvalidated content_hash enables path traversal and violates PayloadStore contract

## Summary

- FilesystemPayloadStore constructs filesystem paths directly from `content_hash` without validating that it is a SHA-256 hex digest, allowing path traversal and non-hash strings to reach `exists()`/`delete()`/`retrieve()`.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/P2-aggregation-metadata-hardcoded @ 17f7293805c0c36aa59bf5fad0f09e09c3035fc9
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: temp filesystem path (payload base dir + file outside base)

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/payload_store.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a temp base path (e.g., `/tmp/payloads`) and create a file outside it (e.g., `/tmp/outside.txt`).
2. Instantiate `FilesystemPayloadStore(base_path=/tmp/payloads)`.
3. Call `payload_store.exists("../outside.txt")` or `payload_store.delete("../outside.txt")`.

## Expected Behavior

- `content_hash` must be validated as a SHA-256 hex digest before any filesystem access; invalid hashes should raise an error and never access paths outside `base_path`.

## Actual Behavior

- `content_hash` is used directly in path construction, allowing path traversal to locations outside `base_path`. `exists()` and `delete()` can operate on arbitrary filesystem paths if given a crafted `content_hash`.

## Evidence

- Path construction uses raw `content_hash` without validation: `src/elspeth/core/payload_store.py:39-42`.
- `exists()` and `delete()` call `_path_for_hash()` directly with no validation: `src/elspeth/core/payload_store.py:77-90`.
- Contract requires `content_hash` to be a SHA-256 hex digest: `src/elspeth/contracts/payload_store.py:44-75`.
- Audit tier rules require crashing on invalid audit data rather than silently tolerating anomalies: `CLAUDE.md:34-41`.

## Impact

- User-facing impact: Potentially misleading behavior (payload reported missing/purged when the ref is malformed); possible failures during explain/resume flows.
- Data integrity / security impact: Path traversal allows `exists()`/`delete()` to touch files outside the payload store; violates audit integrity and trust assumptions.
- Performance or cost impact: Minor.

## Root Cause Hypothesis

- Missing validation and containment checks for `content_hash` in `_path_for_hash()` and the public methods that call it.

## Proposed Fix

- Code changes (modules/files):
  - Add strict validation (length 64, lowercase hex) for `content_hash` in `src/elspeth/core/payload_store.py`.
  - Enforce `base_path` containment (e.g., `resolve()` and parent check) before filesystem access.
- Config or schema changes: None.
- Tests to add/update:
  - New unit tests in `tests/core/test_payload_store.py` to assert invalid hashes raise immediately and cannot traverse outside the base path.
- Risks or migration steps:
  - None expected; invalid hashes should be treated as fatal audit corruption.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:34-41` (Tier 1 must crash on bad audit data); `src/elspeth/contracts/payload_store.py:44-75` (SHA-256 hex digest contract).
- Observed divergence: Implementation accepts arbitrary `content_hash` strings and performs filesystem operations without validating the contract.
- Reason (if known): Missing validation in `_path_for_hash()` and public methods.
- Alignment plan or decision needed: Enforce contract at the boundary by validating hashes and ensuring `base_path` containment.

## Acceptance Criteria

- Invalid `content_hash` values raise immediately without touching the filesystem.
- Path traversal attempts cannot access or delete files outside `base_path`.
- Tests for invalid hashes/path traversal pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_payload_store.py`
- New tests required: yes, invalid-hash and path-traversal prevention cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Tier 1 trust rules); `src/elspeth/contracts/payload_store.py`
---
# Bug Report: Backwards compatibility re-export violates No Legacy Code Policy

## Summary

- `payload_store.py` explicitly re-exports symbols “for backwards compatibility,” which conflicts with the repository’s strict prohibition on legacy compatibility code.

## Severity

- Severity: trivial
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/P2-aggregation-metadata-hardcoded @ 17f7293805c0c36aa59bf5fad0f09e09c3035fc9
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/payload_store.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Open `src/elspeth/core/payload_store.py`.
2. Observe the explicit “Re-export for backwards compatibility” comment and `__all__` definition.

## Expected Behavior

- No backwards compatibility shims or re-exports; old APIs should be removed and call sites updated.

## Actual Behavior

- The file declares compatibility re-exports.

## Evidence

- `src/elspeth/core/payload_store.py:17-18` (“Re-export for backwards compatibility” and `__all__`).
- No-legacy policy forbids compatibility layers: `CLAUDE.md:797-841`.

## Impact

- User-facing impact: Encourages continued use of legacy import paths, delaying cleanup.
- Data integrity / security impact: None directly.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Legacy compatibility export left in place despite “No Legacy Code Policy.”

## Proposed Fix

- Code changes (modules/files):
  - Remove compatibility re-export in `src/elspeth/core/payload_store.py`.
  - Update internal imports/tests to import `IntegrityError`/`PayloadStore` from `elspeth.contracts.payload_store` (or `elspeth.contracts`) directly.
- Config or schema changes: None.
- Tests to add/update:
  - Update any tests that import from `elspeth.core.payload_store` solely for compatibility.
- Risks or migration steps:
  - Requires updating all call sites in a single change to avoid broken imports.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:797-841` (No Legacy Code Policy).
- Observed divergence: Compatibility re-export present in core payload store module.
- Reason (if known): Legacy API retention.
- Alignment plan or decision needed: Remove compatibility layer and update call sites.

## Acceptance Criteria

- No compatibility re-exports remain in `payload_store.py`.
- All internal imports/tests updated to use the canonical contract module.
- Test suite passes without legacy import paths.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_payload_store.py`
- New tests required: no, but existing import-based tests may need updates.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (No Legacy Code Policy)
