# Bug Report: Resume silently infers missing run contract (violates Tier‑1 trust + no‑legacy)

## Summary

- Resume accepts a missing run contract from the audit DB and fabricates an OBSERVED contract from payloads, masking Tier‑1 corruption and violating the no‑legacy policy.

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
- Data set or fixture: Audit DB run with `run_contract` missing (pre‑PipelineRow run or manually nulled)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/engine/orchestrator/core.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create or load a run where `LandscapeRecorder.get_run_contract(run_id)` returns `None` (e.g., a pre‑migration run or a DB update that nulls the contract).
2. Call `Orchestrator.resume(...)` for that run.
3. Observe resume proceeds with an inferred OBSERVED contract instead of failing fast.

## Expected Behavior

- Resume should crash immediately on missing run contract (Tier‑1 data anomaly) and refuse to continue.

## Actual Behavior

- Resume fabricates a contract from the first unprocessed row and continues, silently masking audit‑trail corruption.

## Evidence

- `src/elspeth/engine/orchestrator/core.py:1729` retrieves the run contract from the audit DB.
- `src/elspeth/engine/orchestrator/core.py:1731` explicitly enters a backward‑compatibility path when the contract is missing.
- `CLAUDE.md:29` requires a crash on any audit‑DB anomaly (Tier‑1 trust).
- `CLAUDE.md:843` forbids backward‑compatibility code and migration helpers.

## Impact

- User-facing impact: Resume can complete with a fabricated contract, producing output inconsistent with the original run’s schema metadata.
- Data integrity / security impact: Violates audit‑trail integrity by inferring missing Tier‑1 data instead of failing.
- Performance or cost impact: Minor extra DB reads for inference; primary impact is integrity.

## Root Cause Hypothesis

- Backward‑compatibility logic was added to resume to handle pre‑PipelineRow runs, but it conflicts with Tier‑1 trust guarantees and the no‑legacy policy.

## Proposed Fix

- Code changes (modules/files): Remove the backward‑compatibility inference block in `src/elspeth/engine/orchestrator/core.py:1731` and raise `OrchestrationInvariantError` if the contract is missing; ensure resume uses only the recorded contract.
- Config or schema changes: None.
- Tests to add/update: Add a resume test that asserts a missing run contract raises immediately.
- Risks or migration steps: Existing pre‑migration runs must be re‑run instead of resumed.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:29` (Tier‑1 crash on audit‑DB anomalies) and `CLAUDE.md:843` (No Legacy Code Policy).
- Observed divergence: Resume path includes backward‑compatibility inference instead of failing on missing Tier‑1 data.
- Reason (if known): Attempt to keep pre‑migration runs resumable.
- Alignment plan or decision needed: Remove legacy fallback and enforce failure on missing contract; document that pre‑migration runs must be re‑run.

## Acceptance Criteria

- Resume raises a clear invariant error when `get_run_contract(run_id)` returns `None`.
- No legacy inference paths remain in resume.
- Tests cover the missing‑contract scenario.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine -k resume`
- New tests required: yes, a resume‑missing‑contract test case.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/2026-02-03-pipelinerow-migration.md`
---
# Bug Report: Quarantined row telemetry hash can crash on malformed data

## Summary

- Quarantined rows compute `stable_hash(source_item.row)` for telemetry, which can raise on non‑canonical data (NaN/Infinity or non‑serializable), crashing the run instead of quarantining the row.

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
- Data set or fixture: Source that yields `SourceRow.quarantined(row={"bad": float("nan")}, ...)`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/engine/orchestrator/core.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a source that yields `SourceRow.quarantined` with `row` containing `float("nan")` or another non‑canonical value.
2. Run a pipeline that reads from that source.
3. Observe the run fails during telemetry hashing before the row is routed to the quarantine sink.

## Expected Behavior

- Quarantined rows should never crash the pipeline; telemetry should tolerate non‑canonical external data (use `repr_hash` or skip hash).

## Actual Behavior

- `stable_hash` throws, aborting the run on malformed external data even though it was already marked quarantined.

## Evidence

- `src/elspeth/engine/orchestrator/core.py:1115` computes `stable_hash(source_item.row)` for quarantined rows.
- `src/elspeth/core/canonical.py:9` states NaN/Infinity are strictly rejected.
- `src/elspeth/core/canonical.py:12` instructs using `repr_hash()` for non‑canonical Tier‑3 data.

## Impact

- User-facing impact: Pipelines crash on bad input that should be quarantined.
- Data integrity / security impact: Audit trail loses expected quarantine records for malformed rows.
- Performance or cost impact: None beyond the crash.

## Root Cause Hypothesis

- Telemetry hashing reused strict canonical hashing on Tier‑3 data without fallback.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/engine/orchestrator/core.py:1115`, wrap `stable_hash` with a fallback to `repr_hash` on `ValueError` or `TypeError`, or use `repr_hash` directly for quarantined rows.
- Config or schema changes: None.
- Tests to add/update: Add a quarantine‑row test that includes NaN and asserts the run continues and routes to quarantine sink.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:59` (Tier‑3 data should be quarantined, not crash) and `src/elspeth/core/canonical.py:12` (repr_hash for non‑canonical external data).
- Observed divergence: Quarantined rows still use strict canonical hashing.
- Reason (if known): Telemetry hash reuse without Tier‑3 fallback.
- Alignment plan or decision needed: Use `repr_hash` or guarded hashing for quarantined data.

## Acceptance Criteria

- A quarantined row containing NaN or other non‑canonical values does not crash the run.
- The row reaches the quarantine sink and is recorded in the audit trail.
- Telemetry hashing uses a safe fallback.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine -k quarantine`
- New tests required: yes, quarantined row with NaN or non‑serializable payload.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
