# Bug Report: FilesystemPayloadStore.store Skips Integrity Check for Existing Payloads

## Summary

- `FilesystemPayloadStore.store()` returns a hash without verifying that an existing on-disk payload actually matches that hash, allowing corrupted blobs to persist undetected at write time.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Temp filesystem payload store with a manually corrupted payload file

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/core/payload_store.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `FilesystemPayloadStore(tmp_path)` and call `store(b"original")`, capturing the returned hash.
2. Manually overwrite the stored file at `tmp_path/<hash[:2]>/<hash>` with different bytes.
3. Call `store(b"original")` again.
4. Call `retrieve(<hash>)`.

## Expected Behavior

- `store()` should detect that the existing file’s content does not match the expected hash and raise `IntegrityError` (or otherwise force a verified rewrite) so corrupted payloads are not silently reused.

## Actual Behavior

- `store()` returns the hash without any integrity verification if the file already exists, leaving corrupted payloads in place. A later `retrieve()` raises `IntegrityError`, revealing that audit data already referenced a corrupted blob.

## Evidence

- `src/elspeth/core/payload_store.py:79-88` — `store()` skips writing when `path.exists()` is true and performs no hash verification of the existing content.

## Impact

- User-facing impact: Resume/replay or audit inspection can fail later with `IntegrityError` because payloads referenced in the audit trail are corrupted.
- Data integrity / security impact: Silent data loss at write time; audit trail can point to blobs that are already invalid, violating traceability expectations.
- Performance or cost impact: Low; integrity check would add one read+hash for pre-existing blobs only.

## Root Cause Hypothesis

- The idempotent optimization in `store()` treats existence as equivalence, but does not verify that existing bytes actually match the content hash.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/core/payload_store.py` — if `path.exists()` is true, read the file and verify its SHA-256 equals `content_hash`; if mismatch, raise `payload_contracts.IntegrityError` (or replace the file atomically after verification decision).
- Config or schema changes: None.
- Tests to add/update: Add a test to `tests/core/test_payload_store.py` that corrupts an existing payload file and asserts `store(original_bytes)` raises `IntegrityError` (or rewrites and succeeds if that is the chosen policy).
- Risks or migration steps: If environments currently tolerate corrupted payloads, this will surface them immediately; that is aligned with Tier 1 “crash on corruption.”

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:11-19` (audit integrity “hashes survive payload deletion”), `CLAUDE.md:25-32` (Tier 1 data must be pristine; crash on anomalies).
- Observed divergence: `store()` accepts pre-existing payload files without verifying integrity, allowing corrupted blobs to persist and be referenced.
- Reason (if known): Optimization assumes existence implies correctness.
- Alignment plan or decision needed: Enforce integrity verification when reusing existing payloads; treat mismatch as corruption and crash.

## Acceptance Criteria

- `store()` detects an existing corrupted payload and does not return successfully without either raising `IntegrityError` or rewriting the correct content (chosen policy documented and tested).

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_payload_store.py -v`
- New tests required: yes, add corruption-on-store test as described above.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Auditability Standard, Three-Tier Trust Model)
