# Bug Report: Operations I/O Payloads Lack Hashes, Breaking Audit Integrity After Purge

## Summary

- The `operations` table stores `input_data_ref`/`output_data_ref` without corresponding hashes, so once payloads are purged there is no way to verify the integrity of source/sink operation inputs or outputs, violating the audit rule that hashes must survive payload deletion.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any source/sink operation with `input_data`/`output_data` recorded via payload store

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/landscape/schema.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Run a pipeline where a source or sink calls `track_operation()` with `input_data` or `output_data` so payloads are stored in the payload store.
2. Purge payloads (or let retention policies delete them).
3. Attempt to verify the integrity of those operation inputs/outputs from the audit DB.

## Expected Behavior

- Operation inputs/outputs should remain verifiable after payload deletion via stored hashes (consistent with audit integrity requirements).

## Actual Behavior

- The audit DB only records `input_data_ref`/`output_data_ref` without hashes, so integrity cannot be verified once payloads are purged.

## Evidence

- `src/elspeth/core/landscape/schema.py:225-241` shows `operations` columns include `input_data_ref` and `output_data_ref` but no hash fields.
- `src/elspeth/core/landscape/recorder.py:2335-2430` stores only refs for operation input/output and never computes/stores hashes.
- `CLAUDE.md:15-16` mandates that hashes survive payload deletion so integrity remains verifiable.

## Impact

- User-facing impact: Auditors cannot verify what was sent to or produced by source/sink operations after payload retention policies delete the blobs.
- Data integrity / security impact: Violates auditability guarantees; operation I/O becomes unverifiable evidence.
- Performance or cost impact: None directly; potential investigation time increases.

## Root Cause Hypothesis

- The operations schema and recorder were implemented with payload refs only, omitting hash persistence despite the audit standard requiring hashes to survive payload deletion.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/core/landscape/schema.py` add `input_data_hash` and `output_data_hash` columns; `src/elspeth/core/landscape/recorder.py` compute `stable_hash` for operation input/output and persist; update `src/elspeth/core/landscape/exporter.py` to include new fields in exports.
- Config or schema changes: Add nullable hash columns (non-null when corresponding data present) and provide migration/backfill strategy for existing DBs.
- Tests to add/update: Add unit test ensuring begin/complete operation persists hashes; add export test verifying new fields appear.
- Risks or migration steps: Requires DB migration; existing rows without hashes should remain NULL and be treated as legacy/invalid for integrity verification.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:15-16` (hashes survive payload deletion).
- Observed divergence: Operations table stores refs without hashes, so integrity is lost when payloads are deleted.
- Reason (if known): Likely oversight during operations-table design/implementation.
- Alignment plan or decision needed: Add hash fields and enforce hashing on operation input/output recording.

## Acceptance Criteria

- Operations table includes `input_data_hash` and `output_data_hash` columns.
- Recorder persists hashes whenever input/output data is recorded.
- Exporter includes hash fields.
- Post-purge, integrity verification can still be performed using stored hashes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/test_landscape_operations_hashes.py`
- New tests required: yes, tests validating hash persistence and export coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/analysis/2026-01-31-source-sink-audit-design.md`, `CLAUDE.md`
