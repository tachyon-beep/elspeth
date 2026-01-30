# Bug Report: Quarantined outcomes recorded before sink durability

## Summary

- Orchestrator records `QUARANTINED` outcomes before the quarantine sink write/flush completes, so a sink failure leaves a terminal outcome in the audit trail without durable sink output.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/RC1-RC2-bridge (290716a2563735271d162f1fac7d40a7690e6ed6)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/engine/orchestrator.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a source with `on_validation_failure` pointing to a quarantine sink and force at least one invalid row to be yielded as `SourceRow.quarantined(...)`.
2. Configure the quarantine sink to fail (e.g., unwritable path or intentional exception in `write()`).
3. Run the pipeline.

## Expected Behavior

- `QUARANTINED` outcomes are recorded only after the quarantine sink write/flush succeeds, so a sink failure prevents the terminal outcome from being persisted.

## Actual Behavior

- The `QUARANTINED` outcome is recorded immediately, before sink durability. If the sink write fails, the audit trail still shows the row as quarantined even though no durable quarantine output exists.

## Evidence

- `src/elspeth/engine/orchestrator.py:1036-1038` notes outcomes are recorded by `SinkExecutor.write()` after sink durability.
- `src/elspeth/engine/orchestrator.py:1160-1173` records `RowOutcome.QUARANTINED` before any sink write/flush occurs.
- `src/elspeth/engine/orchestrator.py:1458-1518` performs sink writes later, meaning the outcome is persisted before durability.

## Impact

- User-facing impact: Runs can report quarantined rows that never actually reached the quarantine sink.
- Data integrity / security impact: Audit trail integrity is compromised (terminal outcome without durable sink node_state), violating traceability guarantees.
- Performance or cost impact: None direct, but remediation and reprocessing cost increases.

## Root Cause Hypothesis

- Orchestrator records `QUARANTINED` outcomes early to attach `error_hash`, but does so before sink write/flush, which breaks the sink durability contract for terminal outcomes.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/orchestrator.py`: Defer `record_token_outcome(QUARANTINED)` until after `SinkExecutor.write()` succeeds. Carry `error_hash` alongside pending tokens and record outcomes post-write.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test that simulates a failing quarantine sink and asserts no `QUARANTINED` outcome is recorded when the sink write raises.
  - Add a test that verifies `QUARANTINED` outcomes are recorded only after successful sink flush.
- Risks or migration steps:
  - Ensure post-write outcome recording still includes `error_hash` and does not double-record outcomes.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:637-647` (Terminal Row States: every row reaches exactly one terminal state, tied to sink completion semantics).
- Observed divergence: Terminal outcome recorded before sink durability, allowing an outcome without a completed sink node_state on failure.
- Reason (if known): Early outcome recording to capture `error_hash` without passing it through sink write flow.
- Alignment plan or decision needed: Align quarantined outcome recording with sink durability by recording after successful sink write/flush.

## Acceptance Criteria

- `QUARANTINED` outcomes are recorded only after successful sink write/flush.
- On sink write failure, no `QUARANTINED` outcome is persisted for the affected token(s).
- Audit trail shows consistent terminal outcomes with corresponding sink node_states.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, quarantine sink failure + delayed outcome recording verification

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Terminal Row States)
---
# Bug Report: Quarantined rows silently dropped when quarantine destination is invalid

## Summary

- Orchestrator silently skips quarantined rows if `quarantine_destination` is missing or not in `config.sinks`, resulting in no token, no outcome, and no audit trail entry.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/RC1-RC2-bridge (290716a2563735271d162f1fac7d40a7690e6ed6)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/engine/orchestrator.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement or modify a source to yield `SourceRow.quarantined(...)` with a destination name that is not present in `config.sinks` (e.g., typo).
2. Run a pipeline that triggers at least one quarantined row.

## Expected Behavior

- The run should crash with a clear error (system-owned plugin bug), or at minimum record a terminal `QUARANTINED` outcome and fail the run to avoid silent data loss.

## Actual Behavior

- The row is counted as quarantined but is otherwise dropped: no token is created, no outcome is recorded, and the pipeline continues.

## Evidence

- `src/elspeth/engine/orchestrator.py:1136-1141` checks `if quarantine_sink and quarantine_sink in config.sinks:` and skips handling otherwise.
- `src/elspeth/engine/orchestrator.py:1160-1173` shows the only outcome recording happens inside the conditional branch, so invalid destinations yield no audit records.
- `CLAUDE.md:637-647` requires “every row reaches exactly one terminal state - no silent drops.”

## Impact

- User-facing impact: Quarantined rows can disappear without a trace.
- Data integrity / security impact: Violates auditability guarantees and terminal state invariants.
- Performance or cost impact: None direct, but increases forensic and remediation costs.

## Root Cause Hypothesis

- Defensive guard around `quarantine_destination` treats invalid destinations as a soft failure, contrary to the “system-owned plugin bugs must crash” policy.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/orchestrator.py`: Replace the conditional with a hard invariant check. If `quarantine_destination` is missing or not a configured sink, raise `OrchestrationInvariantError` (or `RouteValidationError`) instead of skipping.
- Config or schema changes: None.
- Tests to add/update:
  - Test that a quarantined row with an invalid destination raises an error and does not silently drop the row.
- Risks or migration steps:
  - May surface latent source bugs that were previously hidden.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:637-647` (Terminal Row States: no silent drops).
- Observed divergence: Silent drop when quarantine destination is invalid.
- Reason (if known): Defensive check intended to avoid crashing on missing sink.
- Alignment plan or decision needed: Enforce invariant and crash on invalid quarantine destination.

## Acceptance Criteria

- Any quarantined row with an invalid destination causes the run to fail loudly.
- No quarantined rows are silently skipped; each reaches a terminal state with an audit trail entry.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, invalid quarantine destination should raise and leave no silent drop

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Terminal Row States)
