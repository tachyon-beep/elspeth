# Bug Report: PipelineRow Shallow Copy Allows Nested Mutation of Audit Data

## Summary

- `PipelineRow` only shallow-copies input data, so nested mutable values remain shared and can be mutated after creation, violating the intended immutability for audit integrity.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: 7a155997ad574d2a10fa3838dd0079b0d67574ff (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Synthetic row with nested list/dict values

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/contracts/schema_contract.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `SchemaContract` and a `PipelineRow` with nested data, e.g. `data = {"items": [1, 2]}`.
2. Mutate the nested list in the original `data` after creating the `PipelineRow`.
3. Read `row["items"]`.

## Expected Behavior

- `PipelineRow` should remain immutable; nested mutations to the original input should not be reflected in `PipelineRow`.

## Actual Behavior

- `PipelineRow` reflects the mutated nested value because only the top-level dict is copied.

## Evidence

- `src/elspeth/contracts/schema_contract.py:501-503` shows only a shallow `dict(data)` copy before wrapping with `MappingProxyType`, leaving nested references shared.
- `tests/contracts/test_pipeline_row.py:213-227` asserts immutability against top-level mutation, indicating intended immutability but does not cover nested values.

## Impact

- User-facing impact: Silent data drift across pipeline stages if nested structures are mutated after creation.
- Data integrity / security impact: Audit trail can be altered post-recording via shared nested references, undermining immutability guarantees.
- Performance or cost impact: Potentially minor unless deep copy is added; then increased CPU/memory per row.

## Root Cause Hypothesis

- `PipelineRow.__init__` performs a shallow copy, so nested mutables are not isolated.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/contracts/schema_contract.py` to deep copy `data` (e.g., `copy.deepcopy`) before wrapping with `MappingProxyType`, or recursively freeze nested structures.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/contracts/test_pipeline_row.py` that mutates a nested list/dict in the original input and asserts `PipelineRow` does not change.
- Risks or migration steps: Deep copy adds overhead; verify pipeline data is JSON-like and copyable to avoid unexpected exceptions.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:25-32` (Tier 1 audit data must be pristine).
- Observed divergence: `PipelineRow` claims immutability but allows nested mutation via shared references.
- Reason (if known): Shallow copy used for performance.
- Alignment plan or decision needed: Decide between deep copy vs. recursive freeze to ensure full immutability.

## Acceptance Criteria

- Mutating nested values in the original input does not affect `PipelineRow`.
- New immutability test for nested structures passes.
- No regressions in existing `PipelineRow` tests.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_pipeline_row.py -k immutability`
- New tests required: yes, nested mutation immutability test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`, `tests/contracts/test_pipeline_row.py`
---
# Bug Report: Optional Datetime Fields Reject `pd.NaT` in SchemaContract.validate

## Summary

- `SchemaContract.validate()` only treats literal `None` as “missing,” so optional datetime fields with `pd.NaT` are flagged as type mismatches, contradicting the canonicalization spec that treats `pd.NaT` as `None`.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-03
- Related run/issue ID: N/A

## Environment

- Commit/branch: 7a155997ad574d2a10fa3838dd0079b0d67574ff (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Row with optional datetime field set to `pd.NaT`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/contracts/schema_contract.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `SchemaContract` with an optional datetime field, e.g. `FieldContract("ts", "Timestamp", datetime, False, "declared")`.
2. Call `validate()` with `{"ts": pd.NaT}`.
3. Observe the returned violations.

## Expected Behavior

- Optional datetime fields should accept `pd.NaT` as missing (equivalent to `None`) with no violation.

## Actual Behavior

- `pd.NaT` bypasses the `None` check and is compared against `datetime`, producing a `TypeMismatchViolation`.

## Evidence

- `src/elspeth/contracts/schema_contract.py:242-249` only treats literal `None` as optional-missing before type normalization.
- `docs/architecture/landscape-system.md:392-401` specifies `pd.NaT` converts to `None` in canonicalization, implying it should be treated as a valid missing value.

## Impact

- User-facing impact: Optional datetime fields with missing values are incorrectly quarantined or flagged.
- Data integrity / security impact: Inconsistent handling of missing values across validation and canonicalization stages.
- Performance or cost impact: Minimal; validation failures can increase quarantine volume.

## Root Cause Hypothesis

- `SchemaContract.validate()` does not treat `pd.NaT` as a missing sentinel prior to type comparison.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/contracts/schema_contract.py`, treat “None-like” values as missing for optional fields, e.g., compute `actual_type = normalize_type_for_contract(value)` and skip when `actual_type is type(None)` and `not fc.required`.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/contracts/test_schema_contract.py` that validates an optional datetime field with `pd.NaT` produces no violations.
- Risks or migration steps: Ensure this does not inadvertently allow non-finite floats (NaN/Infinity) to slip through; keep existing non-finite rejection intact.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/architecture/landscape-system.md:392-401` (pd.NaT treated as None).
- Observed divergence: Validation rejects `pd.NaT` even when canonicalization treats it as a valid missing value.
- Reason (if known): Optional-missing check only covers literal `None`.
- Alignment plan or decision needed: Align validation semantics with canonicalization for missing pandas values.

## Acceptance Criteria

- `SchemaContract.validate()` accepts `pd.NaT` for optional datetime fields without violations.
- New test for optional `pd.NaT` passes.
- No change in behavior for required fields or non-finite values.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/contracts/test_schema_contract.py -k \"optional.*NaT\"`
- New tests required: yes, optional `pd.NaT` validation test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/architecture/landscape-system.md`
