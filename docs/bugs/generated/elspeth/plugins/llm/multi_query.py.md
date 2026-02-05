# Bug Report: Duplicate `output_mapping` suffixes silently overwrite output fields

## Summary

- Multi-query config allows duplicate `output_mapping` suffixes, causing output key collisions and silent data loss at runtime.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b / RC2.3-pipeline-row
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/llm/multi_query.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a multi-query transform with duplicate suffixes in `output_mapping` (e.g., `score: {suffix: value, type: integer}` and `rationale: {suffix: value, type: string}`).
2. Run an `azure_multi_query_llm` (or `openrouter_multi_query_llm`) pipeline with that config.
3. Inspect the output row for the query prefix: only one `{prefix}_value` field is present.

## Expected Behavior

- Config validation rejects duplicate suffixes in `output_mapping` with a clear error before runtime.

## Actual Behavior

- No validation error is raised, and one output field overwrites the other in the output dict, losing data silently.

## Evidence

- `src/elspeth/plugins/llm/multi_query.py:245-287` validates reserved suffix collisions but does not check for duplicate suffixes within `output_mapping`.
- `src/elspeth/plugins/llm/azure_multi_query.py:524-553` builds `output_key = f"{spec.output_prefix}_{field_config.suffix}"` and assigns `output[output_key] = value`, which overwrites on duplicate suffixes.

## Impact

- User-facing impact: Missing expected output fields per query; downstream logic sees incomplete data.
- Data integrity / security impact: Silent data loss violates auditability expectations.
- Performance or cost impact: None direct, but wasted LLM spend for overwritten fields.

## Root Cause Hypothesis

- `MultiQueryConfig.validate_no_output_key_collisions` does not enforce unique `output_mapping` suffixes, allowing configuration that produces identical output keys.

## Proposed Fix

- Code changes (modules/files):
  - Add a uniqueness check for `OutputFieldConfig.suffix` values in `src/elspeth/plugins/llm/multi_query.py` within `validate_no_output_key_collisions`, raising `ValueError` listing duplicates.
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit test that constructs a `MultiQueryConfig` with duplicate suffixes and asserts validation failure.
- Risks or migration steps:
  - Existing configs with duplicates will fail fast; this is desired to prevent silent data loss.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:19` (“No inference - if it's not recorded, it didn't happen”)
- Observed divergence: Duplicate suffixes cause silent overwrite, so a recorded output no longer represents all LLM responses.
- Reason (if known): Missing validation for suffix uniqueness.
- Alignment plan or decision needed: Enforce suffix uniqueness in config validation.

## Acceptance Criteria

- A config with duplicate `output_mapping` suffixes fails validation with a clear error message.
- A config with unique suffixes produces distinct output keys for every mapped field.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, a targeted config validation test for duplicate suffixes.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
