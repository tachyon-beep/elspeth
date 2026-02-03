# Bug Report: Batch trigger_type not enforced as TriggerType enum (Tier-1 audit integrity gap)

## Summary

- `Batch.trigger_type` is typed as `str | None` and never validated against `TriggerType`, so invalid values from the audit DB can flow into the contract without crashing, violating Tier-1 audit integrity rules.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 3aa2fa93d8ebd2650c7f3de23b318b60498cd81c
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static audit of `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py` for deep bug detection
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Insert or update a `batches` row with `trigger_type='typo'` (or any value not in `TriggerType`) in the audit DB.
2. Call `BatchRepository.load()` or `Recorder.get_batch()` and observe the `Batch.trigger_type` value.

## Expected Behavior

- The load should fail (or convert) if `trigger_type` is not a valid `TriggerType` enum, per Tier-1 audit rules.

## Actual Behavior

- The invalid string is accepted and stored in the `Batch` contract instance without error.

## Evidence

- `Batch.trigger_type` is declared as `str | None` and only `status` is validated. `src/elspeth/contracts/audit.py:329-349`
- Repository loads `trigger_type` from DB without conversion. `src/elspeth/core/landscape/repositories.py:250-263`
- `TriggerType` enum exists for `batches.trigger_type`. `src/elspeth/contracts/enums.py:57-74`

## Impact

- User-facing impact: Audit exports and explain tooling can surface invalid trigger types, confusing operators.
- Data integrity / security impact: Violates Tier-1 rule “invalid enum value = crash,” allowing corrupted audit data to be treated as valid.
- Performance or cost impact: Negligible.

## Root Cause Hypothesis

- The `Batch` contract does not model `trigger_type` as `TriggerType` and lacks enum validation, so repository values pass through unchecked.

## Proposed Fix

- Code changes (modules/files):
  - Update `Batch.trigger_type` to `TriggerType | None` and validate in `__post_init__`. `src/elspeth/contracts/audit.py`
  - Convert `row.trigger_type` to `TriggerType` in `BatchRepository.load()` (or ensure caller only passes enums). `src/elspeth/core/landscape/repositories.py`
- Config or schema changes: None (column already stores the enum string values).
- Tests to add/update:
  - Unit test: invalid `trigger_type` raises on `Batch` construction or repository load.
  - Unit test: valid `TriggerType` values round-trip.
- Risks or migration steps:
  - If any existing DB rows contain invalid trigger_type strings, this will surface immediately (desired Tier-1 crash).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25-32`
- Observed divergence: Tier-1 rule requires crashing on invalid enum values, but `trigger_type` accepts arbitrary strings.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce enum type at contract boundary; convert on load.

## Acceptance Criteria

- Loading a batch with invalid `trigger_type` raises immediately.
- Valid `TriggerType` values load without errors and remain typed as enums in the contract.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k "batch_trigger_type"`
- New tests required: yes, contract/repository validation test for `trigger_type`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
---
# Bug Report: TokenOutcome allows is_terminal/outcome mismatch (buffered can be treated as terminal)

## Summary

- `TokenOutcome` validates only that `is_terminal` is a bool, not that it matches `RowOutcome.is_terminal`, allowing inconsistent audit records (e.g., `BUFFERED` with `is_terminal=True`) to pass without crashing.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 3aa2fa93d8ebd2650c7f3de23b318b60498cd81c
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static audit of `/home/john/elspeth-rapid/src/elspeth/contracts/audit.py` for deep bug detection
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Insert a `token_outcomes` row with `outcome='buffered'` and `is_terminal=1` (or `outcome='completed'` and `is_terminal=0`).
2. Call `TokenOutcomeRepository.load()` or `Recorder.get_token_outcome()` for that token.

## Expected Behavior

- The load should fail because `is_terminal` must match `RowOutcome.is_terminal` for Tier-1 audit integrity.

## Actual Behavior

- The inconsistent record is accepted and returned, and `get_token_outcome()` can prefer a non-terminal outcome as terminal because it orders by `is_terminal`.

## Evidence

- `TokenOutcome.__post_init__` only checks bool type and does not enforce consistency with `RowOutcome.is_terminal`. `src/elspeth/contracts/audit.py:568-598`
- Repository converts `outcome` to `RowOutcome` and `is_terminal` to bool but does not cross-check them. `src/elspeth/core/landscape/repositories.py:467-503`
- `get_token_outcome()` prefers `is_terminal` in ordering, so mismatched data changes observed outcome. `src/elspeth/core/landscape/recorder.py:2855-2874`

## Impact

- User-facing impact: Explain output and lineage queries can report a buffered token as terminal or miss a true terminal outcome.
- Data integrity / security impact: Violates Tier-1 audit guarantees; inconsistent terminal flags undermine the “exactly one terminal state” invariant.
- Performance or cost impact: Negligible.

## Root Cause Hypothesis

- The audit contract does not enforce the semantic constraint `is_terminal == outcome.is_terminal`.

## Proposed Fix

- Code changes (modules/files):
  - In `TokenOutcome.__post_init__`, raise if `self.is_terminal != self.outcome.is_terminal`. `src/elspeth/contracts/audit.py`
- Config or schema changes: None.
- Tests to add/update:
  - Unit test: `TokenOutcome` raises on mismatched outcome/is_terminal.
  - Repository test: `TokenOutcomeRepository.load()` rejects inconsistent DB rows.
- Risks or migration steps:
  - Any corrupted rows will surface immediately and stop execution (intended for Tier-1 integrity).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25-32`
- Observed divergence: Tier-1 rule requires crashing on invalid values, but semantic mismatch passes silently.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Enforce semantic validation at contract boundary.

## Acceptance Criteria

- Loading a token outcome with mismatched `is_terminal` and `outcome` raises immediately.
- `get_token_outcome()` can no longer return buffered outcomes as terminal due to inconsistent flags.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k "token_outcome_is_terminal"`
- New tests required: yes, contract/repository validation test for outcome/terminal consistency.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
