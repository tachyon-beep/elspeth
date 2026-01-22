# Bug Report: Recovery skips rows for sinks written later due to row_index checkpoint boundary

## Summary

`RecoveryManager.get_unprocessed_rows` uses the row_index of the latest checkpointed token as a single boundary. Because checkpoints are created after sink writes in sink order, the latest checkpoint can correspond to an earlier row than some rows written to other sinks, causing resume to skip rows routed to a later/failed sink and leaving outputs missing.

## Severity

- Severity: critical
- Priority: P1

## Reporter

- Name or handle: Codex (static analysis agent)
- Date: 2026-01-22
- Related run/issue ID: Unknown

## Environment

- Commit/branch: main (d8df733)
- OS: Linux
- Python version: 3.12+
- Config profile / env vars: Pipeline with multiple sinks and checkpoint frequency `every_row`
- Data set or fixture: Rows routed to multiple sinks

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `src/elspeth/core/checkpoint/recovery.py`
- Model/version: GPT-5 (Codex CLI)
- Tooling and permissions (sandbox/approvals): Read-only sandbox, approvals never
- Determinism details (seed, run ID): Unknown
- Notable tool calls or steps: Read recovery.py, manager.py, orchestrator.py, executors.py, enums.py, CLAUDE.md

## Steps To Reproduce

1. Configure a pipeline with two sinks (`sink_a` default, `sink_b` via gate) and checkpoint frequency `every_row`
2. Run with rows routed to both sinks; force `sink_b.write()` to raise after `sink_a` succeeds (simulate sink failure)
3. Call `RecoveryManager.get_unprocessed_rows(run_id)` and resume
4. Observe rows routed to `sink_b` are not returned/resumed

## Expected Behavior

- Recovery should include rows whose tokens never reached a completed sink node_state (including rows routed to `sink_b`)
- Resume should write the missing sink outputs

## Actual Behavior

- `get_unprocessed_rows` uses the latest checkpoint's token row_index and returns only rows with row_index greater than that
- Rows routed to the failed/later sink are skipped, leaving their outputs missing

## Evidence

- Logs or stack traces: Unknown
- Artifacts (paths, IDs, screenshots):
  - `src/elspeth/core/checkpoint/recovery.py:223`
  - `src/elspeth/core/checkpoint/recovery.py:250`
  - `src/elspeth/core/checkpoint/manager.py:93`
  - `src/elspeth/engine/orchestrator.py:132`
  - `src/elspeth/engine/orchestrator.py:885`
  - `src/elspeth/engine/executors.py:1337`
- Minimal repro input (attach or link): Multi-sink pipeline with forced sink failure

## Impact

- User-facing impact: Resume can finish without emitting outputs for some sinks, even though the run reports completion
- Data integrity / security impact: Audit trail implies sink outputs were produced, but artifacts are missing for routed rows; violates auditability guarantees
- Performance or cost impact: Operators may rerun or manually backfill, risking duplicate writes and extra compute

## Root Cause Hypothesis

Recovery assumes a single monotonic row_index boundary derived from the latest checkpoint, but checkpoints are ordered by sequence_number (token write order) which is not aligned with row_index across multiple sinks. This causes rows routed to later/failed sinks to be skipped.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/core/checkpoint/recovery.py`, compute unprocessed rows by identifying tokens lacking a completed sink node_state (join `tokens_table`, `node_states_table`, and `nodes_table` where node_type="sink") and map those tokens to row_ids, instead of using a single row_index boundary from the latest checkpoint. Optionally keep the current boundary as an optimization only when there is a single sink.
- Config or schema changes: None
- Tests to add/update: Add a multi-sink recovery test where one sink fails after another succeeds; verify rows routed to the failed sink are returned by `get_unprocessed_rows`
- Risks or migration steps: May reprocess some rows and create duplicate sink outputs if sinks are not idempotent; document expected behavior or add idempotency keys

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:28` - Sink output is a non-negotiable data storage point
- Observed divergence: Resume can mark runs completed while some sink outputs are missing for routed rows
- Reason (if known): Recovery uses a row_index boundary based on the last checkpoint rather than actual sink completion per token
- Alignment plan or decision needed: Decide whether recovery should be token/sink-state-based (accurate) or enforce per-row sink write ordering/checkpointing

## Acceptance Criteria

- A multi-sink recovery test (with sink failure) returns rows routed to the failed sink
- Resume emits their outputs
- No missing sink artifacts after resume

## Tests

- Suggested tests to run: `tests/core/checkpoint/test_recovery.py`, `tests/integration/test_checkpoint_recovery.py`
- New tests required: Yes, multi-sink recovery scenario with a forced sink failure

## Notes / Links

- Related issues/PRs: Unknown
- Related design docs: `CLAUDE.md:28`

## Verification Status

- [ ] Bug confirmed via reproduction
- [ ] Root cause verified
- [ ] Fix implemented
- [ ] Tests added
- [ ] Fix verified
