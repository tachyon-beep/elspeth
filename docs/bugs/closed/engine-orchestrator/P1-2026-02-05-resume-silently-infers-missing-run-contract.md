# Bug Report: Resume silently infers missing run contract (violates Tier‑1 trust + no‑legacy)

**Status: FIXED** (2026-02-06)

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

## Fix Details (2026-02-06)

### Changes Made

1. **`src/elspeth/engine/orchestrator/core.py` (line ~1740)**
   - Changed error type from `RuntimeError` to `OrchestrationInvariantError` when schema contract is missing
   - Error message retained with clear explanation of why resume cannot proceed

2. **`src/elspeth/core/checkpoint/recovery.py` (method `verify_contract_integrity`)**
   - Changed return type from `SchemaContract | None` to `SchemaContract`
   - Now raises `CheckpointCorruptionError` when contract is missing (previously returned None)
   - Updated docstring to reflect new behavior: missing contract = audit trail corruption

3. **`tests/core/checkpoint/test_checkpoint_contracts.py`**
   - Renamed `test_resume_without_contract` to `test_resume_without_contract_raises`
   - Updated to expect `CheckpointCorruptionError` instead of success
   - Renamed `test_verify_contract_integrity_returns_none_without_contract` to `test_verify_contract_integrity_raises_without_contract`
   - Updated to expect `CheckpointCorruptionError` instead of returning None
   - Updated module docstring to reflect new behavior (no backward compatibility)

4. **`tests/engine/test_orchestrator_resume.py`**
   - Added new test class `TestOrchestratorResumeMissingContract`
   - Added test `test_resume_raises_on_missing_contract` that verifies `OrchestrationInvariantError` is raised
   - Test bypasses `can_resume()` to specifically test the orchestrator's own contract check

### Verification

```bash
# All 9 checkpoint contract tests pass
.venv/bin/python -m pytest tests/core/checkpoint/test_checkpoint_contracts.py -v

# All 8 orchestrator resume tests pass (1 pre-existing failure in test_orchestrator_recovery.py unrelated to this fix)
.venv/bin/python -m pytest tests/engine/test_orchestrator_resume.py -v
```

### Breaking Change

Pre-contract runs can no longer be resumed. This is intentional per the NO LEGACY CODE POLICY. Such runs must be re-run from scratch.
