# Bug Report: Operation input/output payloads are never purged

**Status: CLOSED**

## Status Update (2026-02-12)

- Classification: **Resolved**
- Resolution summary:
  - `PurgeManager.find_expired_payload_refs()` now includes `operations.input_data_ref` and `operations.output_data_ref` in both expired-run and active-run unions.
  - `PurgeManager._find_affected_run_ids()` now includes operation input/output payload refs when determining which runs need reproducibility-grade updates.
  - Regression tests now cover operation payload refs in both selection and affected-run detection paths.

## Summary

- `operations.input_data_ref` and `operations.output_data_ref` are stored in the PayloadStore but are omitted from purge selection and run-impact calculations, so these payloads never get deleted by retention and are invisible to reproducibility grade updates.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Run containing operation input/output payloads

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/retention/purge.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a run where `begin_operation(..., input_data=...)` and `complete_operation(..., output_data=...)` persist payloads to the PayloadStore.
2. Run `PurgeManager.find_expired_payload_refs()` for a run older than retention and pass the result into `purge_payloads()`.
3. Inspect the PayloadStore for the `operations.input_data_ref` and `operations.output_data_ref` hashes.

## Expected Behavior

- Operation input/output payload refs should be included in purge selection and deleted once their run is beyond retention, and affected runs should be included in reproducibility grade updates.

## Actual Behavior

- Operation input/output refs are never selected for purge or run impact, so they remain in the PayloadStore indefinitely and are excluded from grade downgrade logic.

## Evidence

- `src/elspeth/core/retention/purge.py` now includes operation input/output refs in both expired/active anti-join query sets and affected-run query union.
- `src/elspeth/core/landscape/schema.py:239-240` defines `operations.input_data_ref` and `operations.output_data_ref` as payload store references.
- `src/elspeth/core/landscape/_call_recording.py:210-213` stores `input_data_ref` via PayloadStore.
- `src/elspeth/core/landscape/_call_recording.py:276-281` stores `output_data_ref` via PayloadStore.

## Impact

- User-facing impact: Retention policy fails to delete operation-level payloads, potentially leaving source/sink context data accessible beyond the configured retention period.
- Data integrity / security impact: Potential privacy/compliance risk if operation payloads contain sensitive data expected to be purged.
- Performance or cost impact: PayloadStore growth over time as operation payloads accumulate without cleanup.

## Root Cause Hypothesis

- Purge queries and affected-run calculations in `purge.py` were updated for operation *calls* but not for operation input/output payload refs, leaving a class of PayloadStore content untracked by retention.

## Proposed Fix

- Code changes (modules/files): Add `operations.input_data_ref` and `operations.output_data_ref` to the expired/active UNION queries in `find_expired_payload_refs()` and to `_find_affected_run_ids()` in `src/elspeth/core/retention/purge.py`.
- Config or schema changes: None.
- Tests to add/update: Add retention tests to ensure operation input/output refs are returned by `find_expired_payload_refs()` and that `purge_payloads()` deletes them and updates affected run IDs.
- Risks or migration steps: Minimal; ensure no legacy compatibility shims are added.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/design/subsystems/00-overview.md:660-690` (Payload Store responsibilities include applying retention and purge policies).
- Observed divergence: Operation payloads are stored in PayloadStore but excluded from purge selection and run impact analysis.
- Reason (if known): Likely oversight during operation audit additions.
- Alignment plan or decision needed: Include operation payload refs in purge selection and affected-run logic.

## Acceptance Criteria

- `find_expired_payload_refs()` includes `operations.input_data_ref` and `operations.output_data_ref` for expired runs and excludes those used by active runs.
- `_find_affected_run_ids()` returns run IDs for deleted operation input/output refs.
- Tests demonstrate deletion of operation input/output payloads after retention and proper grade update behavior.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/core/retention/test_purge.py`
- New tests required: yes, add coverage for operation input/output payload retention and purge.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/design/subsystems/00-overview.md`

## Verification Status

- [x] Bug confirmed via reproduction
- [x] Root cause verified
- [x] Fix implemented
- [x] Tests added
- [x] Fix verified

## Resolution (2026-02-12)

**Fixed by:** Codex (GPT-5)

**Changes:**
- `src/elspeth/core/retention/purge.py`: Added operation input/output payload refs to expired/active selection queries and affected-run lookup.
- `tests/unit/core/retention/test_purge.py`: Added regression coverage for operation input/output refs in both `find_expired_payload_refs()` and `_find_affected_run_ids()`.

**Verification:**
- `.venv/bin/python -m pytest tests/unit/core/retention/test_purge.py`
- `.venv/bin/python -m pytest tests/e2e/audit/test_purge_integrity.py`
