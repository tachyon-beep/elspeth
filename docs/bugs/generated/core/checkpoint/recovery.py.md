# Bug Report: Recovery skips rows routed to later/failed sinks due to row_index checkpoint boundary

## Summary

- get_unprocessed_rows uses a single row_index boundary from the latest checkpoint, which is ordered by sink write sequence across sinks, so multi-sink failures can cause rows routed to a later/failed sink to be skipped on resume.

## Severity

- Severity: critical
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: Unknown

## Environment

- Commit/branch: 8635789 (fix/rc1-bug-burndown-session-4)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: Multi-sink pipeline with checkpoint frequency every_row
- Data set or fixture: Rows routed to multiple sinks with a forced sink failure

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit on /home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): Unknown
- Notable tool calls or steps: reviewed recovery.py, orchestrator.py, executors.py, checkpoint/manager.py, contracts/enums.py, CLAUDE.md

## Steps To Reproduce

1. Configure a pipeline with two sinks (default sink_a plus gate-routed sink_b) and checkpoint frequency every_row.
2. Run the pipeline, let sink_a flush successfully, and force sink_b.write() to raise before any checkpoint is created for sink_b.
3. Call RecoveryManager.get_unprocessed_rows(run_id) and resume; observe missing outputs for rows routed to sink_b.

## Expected Behavior

- Recovery should include rows whose tokens never reached a completed sink node_state and resume should emit their sink artifacts.

## Actual Behavior

- get_unprocessed_rows uses the latest checkpoint token row_index as a single boundary and returns only rows with row_index greater than that, skipping rows routed to the failed/later sink.

## Evidence

- `src/elspeth/core/checkpoint/recovery.py:239`
- `src/elspeth/core/checkpoint/recovery.py:266`
- `src/elspeth/core/checkpoint/manager.py:129`
- `src/elspeth/engine/orchestrator.py:1079`
- `src/elspeth/engine/executors.py:1498`

## Impact

- User-facing impact: Resume can complete while missing outputs for rows routed to a failed sink.
- Data integrity / security impact: Audit trail claims sink outputs were produced, but artifacts are missing; violates auditability guarantees.
- Performance or cost impact: Operators may rerun or backfill, risking duplicate writes and extra compute.

## Root Cause Hypothesis

- Recovery assumes a single monotonic row_index boundary from the latest checkpoint sequence, but checkpoint order is by sink write sequence, not by row_index across multiple sinks.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/core/checkpoint/recovery.py` to compute unprocessed rows by querying sink completion (node_states or token_outcomes) instead of using a single row_index boundary; keep the current boundary only as an optimization for single-sink pipelines.
- Config or schema changes: None
- Tests to add/update:
  - Add a multi-sink recovery test where sink_b fails after sink_a succeeds and assert rows routed to sink_b are returned by get_unprocessed_rows.
- Risks or migration steps:
  - May reprocess some rows and create duplicate sink outputs if sinks are not idempotent; document expected behavior or add idempotency keys.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:23`
- Observed divergence: Resume can mark runs completed while some sink outputs are missing for routed rows.
- Reason (if known): Recovery uses a row_index boundary based on the last checkpoint rather than actual sink completion per token.
- Alignment plan or decision needed: Switch recovery to sink-completion-based selection of unprocessed rows.

## Acceptance Criteria

- Multi-sink resume returns rows routed to the failed sink and emits their outputs; no missing sink artifacts after resume.

## Tests

- Suggested tests to run: `pytest tests/core/checkpoint/test_recovery.py -k recovery`
- New tests required: yes, add a multi-sink recovery scenario with a forced sink failure

## Notes / Links

- Related issues/PRs: Unknown
- Related design docs: `CLAUDE.md:23`
---
# Bug Report: can_resume accepts invalid run status instead of failing fast

## Summary

- can_resume treats any status other than RUNNING or COMPLETED as resumable, so invalid or corrupted run statuses are accepted instead of failing fast.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: Unknown

## Environment

- Commit/branch: 8635789 (fix/rc1-bug-burndown-session-4)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: Unknown
- Data set or fixture: Run row with invalid runs.status value and a checkpoint

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit on /home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): Unknown
- Notable tool calls or steps: reviewed recovery.py, contracts/enums.py, CLAUDE.md

## Steps To Reproduce

1. Insert or update a run row with runs.status set to an invalid value (e.g., "paused") and create at least one checkpoint.
2. Call RecoveryManager.can_resume(run_id, graph).

## Expected Behavior

- Invalid run statuses should be rejected or raise immediately; only RunStatus.FAILED should be resumable.

## Actual Behavior

- Any status other than RUNNING or COMPLETED is treated as resumable if a checkpoint exists.

## Evidence

- `src/elspeth/core/checkpoint/recovery.py:76`
- `src/elspeth/core/checkpoint/recovery.py:79`
- `src/elspeth/contracts/enums.py:11`
- `CLAUDE.md:40`

## Impact

- User-facing impact: Resume may proceed on corrupted runs with unpredictable outcomes.
- Data integrity / security impact: Violates Tier 1 audit DB rule to crash on invalid enum values.
- Performance or cost impact: Potential wasted compute on invalid runs.

## Root Cause Hypothesis

- can_resume only checks RUNNING and COMPLETED and never validates that run.status is a valid RunStatus or explicitly FAILED.

## Proposed Fix

- Code changes (modules/files):
  - In `src/elspeth/core/checkpoint/recovery.py`, validate run.status strictly and only allow RunStatus.FAILED; raise or return can_resume=False for invalid enum values per audit policy.
- Config or schema changes: None
- Tests to add/update:
  - Add a test that inserts an invalid runs.status and asserts can_resume rejects or raises.
- Risks or migration steps:
  - None

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:36`
- Observed divergence: Invalid enum values do not cause a crash or explicit failure in recovery checks.
- Reason (if known): Missing strict enum validation in can_resume.
- Alignment plan or decision needed: Enforce RunStatus validation for runs.status in recovery.

## Acceptance Criteria

- can_resume rejects or raises for any runs.status not in RunStatus, and only FAILED is resumable.

## Tests

- Suggested tests to run: `pytest tests/core/checkpoint/test_recovery.py -k can_resume`
- New tests required: yes, invalid-status regression test

## Notes / Links

- Related issues/PRs: Unknown
- Related design docs: `CLAUDE.md:36`
