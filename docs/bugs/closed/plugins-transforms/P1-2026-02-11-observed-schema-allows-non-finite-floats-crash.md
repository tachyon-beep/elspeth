# Bug Report: Observed Schema Allows Non-Finite Floats, Crashing Contract Inference

## Summary

- Observed schemas created by `schema_factory` perform no value validation, so NaN/Infinity can pass source validation and then trigger a `ValueError` during contract inference, crashing the run instead of quarantining at the Tier 3 boundary.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: JSONL blob line containing `NaN` or `Infinity` with `schema: {mode: observed}`

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit of `src/elspeth/plugins/schema_factory.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a source (e.g., Azure Blob JSONL) with `schema: {mode: observed}`.
2. Provide a JSONL row containing `NaN` or `Infinity` (Python `json.loads` accepts these by default).
3. Run the pipeline so the first valid row triggers contract inference.

## Expected Behavior

- Non-finite floats are rejected during schema validation at the source boundary, the row is quarantined, and the run continues without crashing.

## Actual Behavior

- The observed schema accepts the row, then `ContractBuilder.process_first_row()` calls `normalize_type_for_contract()` which raises `ValueError`, crashing the run.

## Evidence

- `src/elspeth/plugins/schema_factory.py:70-91` shows observed schemas are created with no field validation, only `extra="allow"`.
- `src/elspeth/contracts/type_normalization.py:61-64` raises `ValueError` for NaN/Infinity during type inference.
- `src/elspeth/contracts/contract_builder.py:46-98` calls `with_field()` for each value without catching `ValueError`.
- `src/elspeth/plugins/azure/blob_source.py:645-699` uses `json.loads()` without `parse_constant`, then calls `process_first_row()` while only catching `ValidationError`.

## Impact

- User-facing impact: Runs can crash on the first row when non-finite floats appear in observed schemas.
- Data integrity / security impact: Audit trail lacks a terminal row state (quarantine/failed), violating traceability.
- Performance or cost impact: Run failures force retries and manual intervention.

## Root Cause Hypothesis

- `_create_dynamic_schema()` in `schema_factory` skips value validation entirely, so non-finite floats bypass the Tier 3 boundary and are only rejected later during contract inference.

## Proposed Fix

- Code changes (modules/files): Add a model-level validator in `_create_dynamic_schema()` to scan incoming dict values for non-finite floats (including numpy/pandas float types) and raise a validation error; optionally reuse the same validator for explicit schemas to cover `any` fields.
- Config or schema changes: None.
- Tests to add/update: Add a unit test that `create_schema_from_config(..., mode=observed)` rejects NaN/Infinity; add an integration test where BlobSource observed mode quarantines a NaN row instead of crashing.
- Risks or migration steps: Observed schemas will now quarantine rows with non-finite floats instead of crashing or passing them through.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:631-642` mandates NaN/Infinity rejection at canonical JSON boundary.
- Observed divergence: Observed schemas accept NaN/Infinity and allow a downstream crash instead of boundary rejection.
- Reason (if known): Dynamic schemas are built without validators.
- Alignment plan or decision needed: Enforce non-finite float rejection in observed schema creation.

## Acceptance Criteria

- Observed schemas raise `ValidationError` on NaN/Infinity values.
- Source plugins quarantine such rows rather than crashing.
- Contract inference is never invoked on invalid rows.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_schemas.py -k observed`
- New tests required: yes, add observed-schema NaN/Infinity rejection coverage and a BlobSource integration case.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:631-642`

## Closure Update (2026-02-11)

- Status: Closed after re-verification against current code.
- Verification summary: observed-mode schemas now reject non-finite float values at validation time via a shared model validator.
- Evidence:
  - `src/elspeth/plugins/schema_factory.py:77` adds `_ObservedPluginSchema` with a `model_validator(mode=\"before\")`.
  - `src/elspeth/plugins/schema_factory.py:123` creates dynamic observed schemas using `__base__=_ObservedPluginSchema`.
  - `tests/unit/plugins/test_schema_factory.py` passes with observed-schema non-finite rejection coverage.
