# Bug Report: NodeStateRepository does not enforce OPEN/PENDING invariant “forbidden fields”

## Summary

- NodeStateRepository returns OPEN/PENDING states even when audit rows include forbidden fields (e.g., output_hash/completed_at/duration_ms), violating declared invariants and Tier‑1 crash rules.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 17f72938 (branch unknown)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/landscape/repositories.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Construct a `node_states` row with `status="open"` but set `output_hash` or `completed_at` or `duration_ms` to non-null values.
2. Call `NodeStateRepository.load(row)`.

## Expected Behavior

- The repository raises a `ValueError` because OPEN states must not have `output_hash`, `completed_at`, or `duration_ms`.

## Actual Behavior

- The repository returns `NodeStateOpen` without validating those forbidden fields, allowing corrupted audit data to pass silently.

## Evidence

- `src/elspeth/core/landscape/repositories.py:297-308` returns `NodeStateOpen` with no invariant checks for forbidden fields.
- `src/elspeth/core/landscape/repositories.py:310-330` validates PENDING only for required fields but does not reject `output_hash` (must be absent per contract).
- `src/elspeth/contracts/audit.py:151-182` documents invariants for OPEN and PENDING that explicitly disallow `output_hash` and require `completed_at/duration_ms` for PENDING.

## Impact

- User-facing impact: Incorrect lineage/explain results can be produced from corrupted audit rows without detection.
- Data integrity / security impact: Violates Tier‑1 “crash on bad audit data,” enabling silent audit corruption.
- Performance or cost impact: Minimal direct impact; risks hidden integrity issues.

## Root Cause Hypothesis

- Missing invariant validation in `NodeStateRepository.load()` for fields that must be NULL in OPEN/PENDING states.

## Proposed Fix

- Code changes (modules/files):
  - Add explicit checks in `src/elspeth/core/landscape/repositories.py` to reject OPEN rows with non-null `output_hash`, `completed_at`, or `duration_ms`.
  - Add explicit check to reject PENDING rows with non-null `output_hash`.
- Config or schema changes: None.
- Tests to add/update:
  - Add tests in `tests/core/landscape/test_node_state_repository.py` to assert OPEN/PENDING rows with forbidden fields raise `ValueError`.
- Risks or migration steps:
  - Existing corrupted audit rows will now hard-fail reads; operators may need to fix or purge bad data.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:34-41` (Tier‑1 crash on bad data), `src/elspeth/contracts/audit.py:151-182` (NodeState invariants).
- Observed divergence: Repository does not enforce documented invariants for OPEN/PENDING states.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce invariants at repository boundary as intended.

## Acceptance Criteria

- OPEN rows with any of `output_hash`, `completed_at`, or `duration_ms` set cause `NodeStateRepository.load()` to raise `ValueError`.
- PENDING rows with `output_hash` set cause `NodeStateRepository.load()` to raise `ValueError`.
- New tests cover these cases and pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_node_state_repository.py`
- New tests required: yes, add OPEN/PENDING forbidden-field validation tests.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:34-41`, `src/elspeth/contracts/audit.py:151-182`
---
# Bug Report: TokenOutcomeRepository coerces invalid is_terminal values instead of crashing

## Summary

- `TokenOutcomeRepository.load()` converts `is_terminal` with `row.is_terminal == 1`, silently treating any non‑1 value (including invalid integers or NULL) as `False`, which violates Tier‑1 audit integrity rules.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: 17f72938 (branch unknown)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/core/landscape/repositories.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a token_outcomes row with `is_terminal=2` (or `None`).
2. Call `TokenOutcomeRepository.load(row)`.

## Expected Behavior

- The repository raises a `ValueError` because audit data is Tier‑1 and `is_terminal` must be strictly boolean/0/1.

## Actual Behavior

- The repository returns `TokenOutcome(is_terminal=False)` for any non‑1 value, silently masking data corruption.

## Evidence

- `src/elspeth/core/landscape/repositories.py:473-479` uses `is_terminal=row.is_terminal == 1`, which coerces invalid values to `False`.
- `src/elspeth/core/landscape/schema.py:140-142` defines `is_terminal` as an Integer used as boolean (expects 0/1).
- `CLAUDE.md:34-41` mandates Tier‑1 “crash on bad audit data; no coercion.”

## Impact

- User-facing impact: Terminal outcomes can be misclassified as non-terminal, breaking lineage and recovery logic.
- Data integrity / security impact: Silent corruption of audit semantics; violates audit trail invariants.
- Performance or cost impact: Potential downstream reprocessing and debugging cost.

## Root Cause Hypothesis

- Repository uses a coercive comparison instead of strict validation for Tier‑1 audit data.

## Proposed Fix

- Code changes (modules/files):
  - In `src/elspeth/core/landscape/repositories.py`, validate `row.is_terminal` is exactly 0 or 1 (or boolean) and raise `ValueError` otherwise.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test in `tests/core/landscape/test_error_repositories.py` asserting invalid `is_terminal` values raise `ValueError`.
- Risks or migration steps:
  - Corrupted rows will now trigger hard failures on read; may require data cleanup.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:34-41` (Tier‑1 no coercion), `src/elspeth/core/landscape/schema.py:140-142` (is_terminal stored as integer boolean).
- Observed divergence: Repository coerces invalid `is_terminal` values instead of crashing.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce strict 0/1 validation at repository boundary.

## Acceptance Criteria

- `TokenOutcomeRepository.load()` raises `ValueError` when `is_terminal` is not 0 or 1 (or True/False).
- New test covers invalid `is_terminal` values and passes.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_error_repositories.py`
- New tests required: yes, invalid `is_terminal` validation test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:34-41`, `src/elspeth/core/landscape/schema.py:140-142`
