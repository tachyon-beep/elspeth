# Bug Report: Resume does not verify payload integrity against stored source_data_hash

## Summary

- RecoveryManager.get_unprocessed_row_data() retrieves payloads by source_data_ref but never checks that the payload content hash matches rows.source_data_hash, allowing silent resume on mismatched/corrupted row data.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any run with payload_store enabled

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit for /home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a run with payload_store enabled so rows have both source_data_hash and source_data_ref.
2. Manually alter rows.source_data_ref to point to a different payload (or swap payload files so the ref resolves to different content).
3. Call RecoveryManager.get_unprocessed_row_data(...) for that run.
4. Observe that row data is returned without any integrity error.

## Expected Behavior

- Resume should verify that retrieved payload content matches rows.source_data_hash and raise an audit-integrity error if it does not.

## Actual Behavior

- Resume accepts the payload unverified, allowing reprocessing of incorrect row data.

## Evidence

- Recovery uses only row_index and source_data_ref; no integrity check against source_data_hash. `src/elspeth/core/checkpoint/recovery.py:188-207`
- rows_table stores source_data_hash explicitly for integrity tracking. `src/elspeth/core/landscape/schema.py:100-108`
- Recorder writes source_data_hash at ingest (stable_hash of data). `src/elspeth/core/landscape/recorder.py:652-669`

## Impact

- User-facing impact: Resumed runs can silently process the wrong row payloads if refs are stale or corrupted.
- Data integrity / security impact: Audit trail integrity is compromised; hash-to-payload mismatch is not detected.
- Performance or cost impact: Potentially wasted compute on incorrect data; possible downstream rework.

## Root Cause Hypothesis

- RecoveryManager.get_unprocessed_row_data() does not retrieve rows.source_data_hash or compare it to the hash of the retrieved payload, so integrity mismatches go unnoticed.

## Proposed Fix

- Code changes (modules/files):
  - Add rows_table.c.source_data_hash to the row metadata query in `src/elspeth/core/checkpoint/recovery.py`.
  - After payload retrieval and json.loads, compute stable_hash(degraded_data) and compare to source_data_hash; raise ValueError (or AuditIntegrityError) on mismatch.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test in `tests/core/checkpoint/test_recovery_row_data.py` that corrupts source_data_ref/payload and asserts get_unprocessed_row_data raises on hash mismatch.
- Risks or migration steps:
  - Existing corrupted runs will fail fast on resume (intended per audit-integrity policy).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): CLAUDE.md “Auditability Standard” and “Data Manifesto: Tier 1 (Audit Database / Landscape) – crash on any anomaly”.
- Observed divergence: Resume path does not verify payload integrity against the recorded hash, allowing audit-trail corruption to pass silently.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce hash check during resume payload retrieval.

## Acceptance Criteria

- When source_data_ref points to a payload whose content hash does not match rows.source_data_hash, get_unprocessed_row_data() raises an integrity error and does not return row data.
- Existing resume behavior remains unchanged for valid payloads.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/checkpoint/test_recovery_row_data.py`
- New tests required: yes, corruption/mismatch detection test

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: CLAUDE.md (Auditability Standard; Three-Tier Trust Model)
