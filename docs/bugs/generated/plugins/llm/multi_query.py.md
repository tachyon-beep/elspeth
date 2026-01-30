# Bug Report: Multi-query config allows output-key collisions that silently overwrite LLM results

## Summary

- MultiQueryConfig does not validate uniqueness of generated output prefixes or suffixes, so colliding keys overwrite earlier results and/or metadata without any error, causing silent data loss.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any row containing the configured input_fields

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of /home/john/elspeth-rapid/src/elspeth/plugins/llm/multi_query.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `azure_multi_query_llm` with duplicate case study names (or names that collide when joined with `_`), e.g. two case_studies named `cs1`, and any criterion.
2. Alternatively, configure `output_mapping` with two fields sharing the same `suffix`, or with `suffix: usage`.
3. Run the pipeline on a row containing the required input fields and inspect the output row.

## Expected Behavior

- Configuration validation should reject any configuration that would generate duplicate output keys (including collisions with reserved metadata fields), or the transform should raise an explicit error before emitting a row.

## Actual Behavior

- Output keys collide and later values overwrite earlier ones during merge, so some LLM results or user-mapped fields are silently lost.

## Evidence

- `src/elspeth/plugins/llm/multi_query.py:215-303` defines case studies/criteria and builds `output_prefix` as `f"{case_study.name}_{criterion.name}"` with no uniqueness or collision validation; the only output_mapping validation is non-empty.
- `src/elspeth/plugins/llm/azure_multi_query.py:446-610` constructs output keys as `f"{spec.output_prefix}_{field_config.suffix}"` and then merges results via `output.update(...)`, which overwrites on key collision; metadata fields like `*_usage`/`*_model` are written after output_mapping and will overwrite any user-mapped field with the same suffix.

## Impact

- User-facing impact: Missing or incorrect output fields with no error surfaced.
- Data integrity / security impact: Silent data loss in audited outputs undermines traceability and correctness.
- Performance or cost impact: None.

## Root Cause Hypothesis

- MultiQueryConfig lacks validation to ensure uniqueness of generated output prefixes and output field suffixes, and to guard against collisions with reserved metadata suffixes.

## Proposed Fix

- Code changes (modules/files):
  - Add a `@model_validator(mode="after")` in `src/elspeth/plugins/llm/multi_query.py` to:
    - enforce unique `case_study.name` and `criterion.name`,
    - compute `output_prefix` for all pairs and ensure uniqueness (including collisions from `_` concatenation),
    - enforce unique `OutputFieldConfig.suffix` values,
    - reject suffixes that collide with reserved metadata suffixes (`usage`, `model`, `template_hash`, `variables_hash`, `template_source`, `lookup_hash`, `lookup_source`, `system_prompt_source`).
- Config or schema changes: None.
- Tests to add/update:
  - Add config validation tests that assert MultiQueryConfig rejects:
    - duplicate case study names,
    - duplicate criterion names,
    - duplicate suffixes in output_mapping,
    - suffixes that collide with metadata fields,
    - output_prefix collisions caused by `_` concatenation.
- Risks or migration steps:
  - Existing configs with colliding names/suffixes will start failing validation; document required renames.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- Invalid configurations that would generate duplicate output keys are rejected at config load time.
- For valid configurations, each output key maps to exactly one source field and is never overwritten by metadata.
- Unit tests cover all collision cases listed above.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/`
- New tests required: yes, config validation tests for multi-query output key collisions

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
