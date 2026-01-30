# Bug Report: Retention purge excludes failed runs, leaving their payloads undeletable

## Summary

- `PurgeManager.find_expired_payload_refs()` (and `find_expired_row_payloads()`) only treats status `"completed"` runs as expired, so payloads from failed runs are never purged and also block deletion of shared refs.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic run with status=failed and completed_at older than retention

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Insert a run with `status="failed"` and `completed_at` older than retention cutoff, and insert a row/call payload ref tied to that run.
2. Call `PurgeManager.find_expired_payload_refs(retention_days=...)` or run `elspeth purge --retention-days ...`.

## Expected Behavior

- Payload refs from failed runs older than the retention cutoff are eligible for purge, consistent with retention policies based on run completion time.

## Actual Behavior

- The refs are treated as “active” because `status != "completed"`, so they are never returned for purge. Shared refs used by an expired completed run are also blocked from deletion.

## Evidence

- `/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py:136-151` limits expired runs to `status == "completed"` and treats `status != "completed"` as active.
- `/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py:83-100` uses the same `"completed"` gate for row payloads.
- `/home/john/elspeth-rapid/docs/design/architecture.md:570-579` defines retention by data type (row/call payloads) after expiry without a success-only carveout.

## Impact

- User-facing impact: Operators cannot purge payloads for failed runs, leading to unexpected storage growth.
- Data integrity / security impact: Retention policy semantics are violated; expired payloads are retained indefinitely.
- Performance or cost impact: Unbounded payload store growth for failed runs and shared content.

## Root Cause Hypothesis

- The retention logic equates “expired” with `status == "completed"`, excluding failed runs from purge eligibility and marking them “active” regardless of age.

## Proposed Fix

- Code changes (modules/files):
  - Update `/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py` to treat failed runs with `completed_at < cutoff` as expired, and define “active” as `completed_at is NULL` or `completed_at >= cutoff` (or explicit `status == "running"`).
  - Apply the same logic in `find_expired_row_payloads()`.
- Config or schema changes: None.
- Tests to add/update:
  - Add retention tests covering `RunStatus.FAILED` older than cutoff, plus a shared-ref case where a failed run should not block purge once past retention.
- Risks or migration steps:
  - None; behavior aligns with retention policy by completion time.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `/home/john/elspeth-rapid/docs/design/architecture.md:570-579`
- Observed divergence: Retention is scoped to data type and expiry, but implementation excludes failed runs.
- Reason (if known): Likely an over-conservative “active run” filter carried forward from an earlier design.
- Alignment plan or decision needed: Confirm retention applies to all completed runs (including failed) and codify in purge queries.

## Acceptance Criteria

- Failed runs older than retention cutoff produce payload refs in `find_expired_payload_refs()` and are purged by `purge_payloads()`.
- Shared refs are not protected solely because a failed run exists beyond the retention window.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/retention/test_purge.py`
- New tests required: yes, failed-run retention coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `/home/john/elspeth-rapid/docs/design/architecture.md`
---
# Bug Report: Purge aborts on payload-store I/O errors, skipping grade updates

## Summary

- `purge_payloads()` does not catch exceptions from `PayloadStore.exists()`/`.delete()`, so a single I/O error aborts the purge and skips reproducibility-grade updates for refs already deleted.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Payload store with at least one ref that triggers an I/O error during delete

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Use a payload store backend that raises `OSError`/`PermissionError` on `delete()` or `exists()` for one ref (e.g., read-only filesystem).
2. Call `PurgeManager.purge_payloads([ref_ok, ref_error])`.

## Expected Behavior

- The purge should record the error ref in `failed_refs`, continue deleting other refs, and still update reproducibility grades for successfully deleted refs.

## Actual Behavior

- An exception aborts the purge loop, so `failed_refs` is not populated and `update_grade_after_purge()` is never called for already-deleted refs.

## Evidence

- `/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py:343-350` calls `exists()` and `delete()` with no exception handling inside the loop.
- `/home/john/elspeth-rapid/src/elspeth/core/payload_store.py:87-90` uses `Path.unlink()` directly, which can raise `OSError`/`PermissionError`.

## Impact

- User-facing impact: `elspeth purge` can fail mid-run with partial deletion and no clear accounting.
- Data integrity / security impact: Runs may retain `REPLAY_REPRODUCIBLE` even after payloads were deleted, overstating replay capability.
- Performance or cost impact: Inconsistent retention behavior; reruns may be required.

## Root Cause Hypothesis

- The purge loop assumes `exists()`/`delete()` never raise, but filesystem backends can raise, so the whole purge aborts before grade updates.

## Proposed Fix

- Code changes (modules/files):
  - In `/home/john/elspeth-rapid/src/elspeth/core/retention/purge.py`, wrap per-ref `exists()`/`delete()` in `try/except` (e.g., `OSError`, `Exception`) and append to `failed_refs` on error so the loop continues.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test payload store that raises on delete and assert: (a) `failed_refs` includes the ref, (b) other refs are deleted, (c) grades update based on `deleted_refs`.
- Risks or migration steps:
  - None; behavior aligns with existing `failed_refs` semantics.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- Purge completes even when a subset of refs raise exceptions; failures are recorded in `failed_refs`.
- Reproducibility grades update for runs tied to refs that were successfully deleted.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/retention/test_purge.py`
- New tests required: yes, exception-handling path for delete/exists.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
