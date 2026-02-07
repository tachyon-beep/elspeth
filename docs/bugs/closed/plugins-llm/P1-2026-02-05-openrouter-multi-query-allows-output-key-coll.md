# Bug Report: OpenRouter multi-query allows output key collisions and silent overwrites

## Summary

- `OpenRouterMultiQueryConfig` does not validate duplicate case_study/criterion names or reserved suffix collisions, allowing output keys to collide and be silently overwritten by later results or metadata.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 0282d1b441fe23c5aaee0de696917187e1ceeb9b
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Pipeline config with duplicate case_study/criterion names or output_mapping suffix collision (e.g., `usage`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/llm/openrouter_multi_query.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `openrouter_multi_query_llm` with duplicate criterion names (e.g., two criteria named `diagnosis`), or set an output_mapping suffix to a reserved LLM suffix like `usage`.
2. Run the pipeline for any row.
3. Inspect the output row: fields from one query or the output_mapping field are silently overwritten.

## Expected Behavior

- Config validation should reject duplicate case_study/criterion names and output_mapping suffix collisions with reserved LLM suffixes.
- Output fields from each query should remain distinct and not be overwritten by metadata.

## Actual Behavior

- The config is accepted and collisions occur at runtime, causing silent overwrites in the output row and loss of earlier query results or metadata.

## Evidence

- `OpenRouterMultiQueryConfig` only validates `output_mapping` is non-empty and provides no collision checks. `src/elspeth/plugins/llm/openrouter_multi_query.py:100-189`
- `output_prefix` is derived directly from case_study and criterion names with no uniqueness enforcement. `src/elspeth/plugins/llm/openrouter_multi_query.py:175-186`
- Output fields are written and later metadata fields with fixed suffixes are added, which will overwrite if suffix collides (e.g., `usage`). `src/elspeth/plugins/llm/openrouter_multi_query.py:882-915`
- Results are merged with `output.update(...)`, so collisions overwrite earlier values. `src/elspeth/plugins/llm/openrouter_multi_query.py:1089-1096`
- The Azure multi-query config includes the missing collision validator for duplicates and reserved suffixes. `src/elspeth/plugins/llm/multi_query.py:245-288`

## Impact

- User-facing impact: Output rows lose fields or contain incorrect values without error.
- Data integrity / security impact: Audit trail is corrupted by silent overwrites; lineage becomes unreliable.
- Performance or cost impact: N/A

## Root Cause Hypothesis

- `OpenRouterMultiQueryConfig` omits the `validate_no_output_key_collisions` model validator present in `MultiQueryConfig`, so invalid configurations are not rejected.

## Proposed Fix

- Code changes (modules/files): Add a `@model_validator` in `OpenRouterMultiQueryConfig` mirroring `MultiQueryConfig.validate_no_output_key_collisions`, enforcing unique case_study/criterion names and reserved suffix collision checks.
- Config or schema changes: None.
- Tests to add/update: Add config validation tests for duplicate case_study/criterion names and reserved suffix collisions in `openrouter_multi_query`.
- Risks or migration steps: Existing configs relying on collisions will now fail validation and must be fixed.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md#L9-L18` (Auditability Standard: “No inference - if it's not recorded, it didn't happen.”)
- Observed divergence: Silent overwrites cause loss of recorded data without an error, violating auditability guarantees.
- Reason (if known): Missing config validator in OpenRouter variant.
- Alignment plan or decision needed: Add the validator to block invalid configs at load time.

## Acceptance Criteria

- Duplicate case_study or criterion names are rejected by config validation.
- Output_mapping suffixes that collide with reserved LLM suffixes are rejected.
- A unit test confirms collisions are blocked and no silent overwrites occur.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_openrouter_multi_query_config.py`
- New tests required: yes, add validation coverage for duplicates and reserved suffix collisions.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Auditability Standard)
