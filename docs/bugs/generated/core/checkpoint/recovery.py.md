# Bug Report: RecoveryManager.can_resume blocks resume for interrupted runs left in RUNNING status

## Summary

- `can_resume()` refuses to resume runs with status `running`, which prevents crash/interruption recovery for runs that never reached `completed_at`, contradicting the runbook guidance to resume such runs.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 064e84a6165894fcc52cb48d407ea52dd4285a97 (branch: fix/P2-aggregation-metadata-hardcoded)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Interrupted run with checkpoint (status=running, completed_at NULL)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit for /home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Execute a pipeline with checkpointing enabled and terminate the process abruptly (e.g., kill -9) after at least one checkpoint is created.
2. Confirm the run has `status = "running"` and `completed_at` is NULL in `runs`.
3. Run `elspeth resume <RUN_ID>` (dry run or execute).

## Expected Behavior

- Resume should be allowed for interrupted runs that are still marked `running` but have valid checkpoints, matching the runbook guidance for crash recovery.

## Actual Behavior

- `can_resume()` returns `can_resume=False` with reason “Run is still in progress,” so resume is blocked.

## Evidence

- `src/elspeth/core/checkpoint/recovery.py:87-91` explicitly blocks status `RUNNING`, returning “Run is still in progress.”
- `docs/runbooks/resume-failed-run.md:40-62` instructs operators to resume runs with status `running` and no `completed_at` timestamp (crash/interruption scenario).

## Impact

- User-facing impact: Operators cannot resume interrupted runs, even when checkpoints exist, forcing full re-runs or manual recovery.
- Data integrity / security impact: None directly, but recovery gaps undermine auditability guarantees.
- Performance or cost impact: Potentially high—reprocessing from the beginning for long pipelines.

## Root Cause Hypothesis

- `can_resume()` assumes only `FAILED` runs are resumable and treats `RUNNING` as truly active, but the system lacks heartbeat/staleness checks and the runbook explicitly expects resuming `RUNNING` runs after crashes.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/core/checkpoint/recovery.py` to allow resuming `RUNNING` runs when checkpoints exist (optionally with a warning reason or an explicit “stale-running allowed” check).
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit/integration test where a run is `RUNNING` with no `completed_at` and has a checkpoint; assert `can_resume=True`.
  - Add CLI test ensuring `elspeth resume <RUN_ID>` proceeds for a `RUNNING` run with checkpoints.
- Risks or migration steps:
  - Risk of resuming a truly active run; if needed, require operator acknowledgement at CLI level rather than blocking in `can_resume()`.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/runbooks/resume-failed-run.md:40-62`
- Observed divergence: Code blocks `RUNNING` status while runbook instructs resuming `RUNNING` runs with no `completed_at`.
- Reason (if known): Likely conservative gating without a staleness signal.
- Alignment plan or decision needed: Decide whether `RUNNING` should be resumable by default and codify the operator-staleness check.

## Acceptance Criteria

- `can_resume()` returns `can_resume=True` for `RUNNING` runs with checkpoints (or provides a structured warning and allows resume).
- CLI `elspeth resume` works for interrupted `RUNNING` runs in the runbook scenario.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k "resume and running"`
- New tests required: yes, resume for `RUNNING` + checkpoint scenario

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/runbooks/resume-failed-run.md`
---
# Bug Report: can_resume propagates IncompatibleCheckpointError instead of returning ResumeCheck

## Summary

- `can_resume()` does not catch `IncompatibleCheckpointError` from `CheckpointManager.get_latest_checkpoint()`, causing resume checks to crash instead of returning a structured “cannot resume” reason.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 064e84a6165894fcc52cb48d407ea52dd4285a97 (branch: fix/P2-aggregation-metadata-hardcoded)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Run with legacy/incompatible checkpoint format

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit for /home/john/elspeth-rapid/src/elspeth/core/checkpoint/recovery.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create or load a run whose latest checkpoint has an incompatible `format_version` (or is pre-versioned older than the cutoff).
2. Call `RecoveryManager.can_resume(run_id, graph)` (CLI `elspeth resume` invokes this).
3. Observe exception.

## Expected Behavior

- `can_resume()` returns `ResumeCheck(can_resume=False, reason=...)` explaining the incompatibility.

## Actual Behavior

- `IncompatibleCheckpointError` is raised and propagates, leading to an unhandled error path in callers like the CLI.

## Evidence

- `src/elspeth/core/checkpoint/recovery.py:93-99` calls `get_latest_checkpoint()` without exception handling.
- `src/elspeth/core/checkpoint/manager.py:122-159` and `209-249` show `get_latest_checkpoint()` validates compatibility and raises `IncompatibleCheckpointError`.

## Impact

- User-facing impact: CLI resume can crash with a stack trace instead of a clear “cannot resume” message.
- Data integrity / security impact: None.
- Performance or cost impact: Minimal, but increases operational friction.

## Root Cause Hypothesis

- `can_resume()` assumes `get_latest_checkpoint()` returns `None` for non-resumable cases, but it can raise on incompatible format.

## Proposed Fix

- Code changes (modules/files):
  - Catch `IncompatibleCheckpointError` in `src/elspeth/core/checkpoint/recovery.py` and return `ResumeCheck(can_resume=False, reason=str(e))`.
- Config or schema changes: None.
- Tests to add/update:
  - Add test for `can_resume()` with an incompatible checkpoint verifying `can_resume=False` and a reason message.
- Risks or migration steps:
  - None; this only improves error reporting.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: `can_resume()` contract says it returns `ResumeCheck` explaining why not, but incompatible checkpoints raise instead of returning a reason.
- Reason (if known): Missing exception handling.
- Alignment plan or decision needed: Align `can_resume()` behavior with `ResumeCheck` contract.

## Acceptance Criteria

- `can_resume()` never raises `IncompatibleCheckpointError`; it returns `ResumeCheck(can_resume=False, reason=...)` for incompatible checkpoints.
- CLI `elspeth resume` reports a clear incompatibility message instead of a stack trace.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k "resume and incompatible_checkpoint"`
- New tests required: yes, resume check on incompatible checkpoint

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
