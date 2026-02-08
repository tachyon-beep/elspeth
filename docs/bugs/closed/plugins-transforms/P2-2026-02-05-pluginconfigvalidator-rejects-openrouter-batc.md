# Bug Report: PluginConfigValidator Rejects OpenRouter Batch/Multi-Query Transforms as “Unknown”

## Summary

- `PluginConfigValidator._get_transform_config_model()` does not include `openrouter_batch_llm` or `openrouter_multi_query_llm`, so valid pipelines using these built-in transforms fail validation with “Unknown transform type”.

## Severity

- Severity: moderate
- Priority: P2
- Downgrade rationale: Functionality gap (validator incomplete), not audit/data integrity issue

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b / RC2.3-pipeline-row
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: `examples/openrouter_sentiment/settings_batched.yaml` and `examples/openrouter_multi_query_assessment/settings.yaml`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/plugins/validation.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `PluginConfigValidator().validate_transform_config("openrouter_batch_llm", valid_config_dict)` using any valid config.
2. Observe it raises `ValueError: Unknown transform type: openrouter_batch_llm`.

## Expected Behavior

- Validator should return an empty error list (or structured field errors) for a valid `openrouter_batch_llm` or `openrouter_multi_query_llm` configuration.

## Actual Behavior

- Validator raises `ValueError` for both `openrouter_batch_llm` and `openrouter_multi_query_llm` because the transform type is not mapped in `_get_transform_config_model()`.

## Evidence

- Missing mappings in `src/elspeth/plugins/validation.py` for OpenRouter batch/multi-query transforms: `src/elspeth/plugins/validation.py:235-295`.
- Built-in transform exists with name `openrouter_batch_llm`: `src/elspeth/plugins/llm/openrouter_batch.py:114-129`.
- Built-in transform exists with name `openrouter_multi_query_llm`: `src/elspeth/plugins/llm/openrouter_multi_query.py:269-279`.
- Example configs reference these plugin names:
  - `examples/openrouter_sentiment/settings_batched.yaml:42-55` (`openrouter_batch_llm`)
  - `examples/openrouter_multi_query_assessment/settings.yaml:31-33` (`openrouter_multi_query_llm`)

## Impact

- User-facing impact: Pipelines using `openrouter_batch_llm` or `openrouter_multi_query_llm` cannot validate or run via `PluginManager.create_transform()`.
- Data integrity / security impact: None directly.
- Performance or cost impact: None directly, but blocks batch/multi-query workflows.

## Root Cause Hypothesis

- `PluginConfigValidator` uses a hardcoded transform mapping and was not updated when OpenRouter batch and multi-query transforms were added, so validation rejects valid built-in plugins.

## Proposed Fix

- Code changes (modules/files):
  - Add mappings in `src/elspeth/plugins/validation.py` for:
    - `openrouter_batch_llm` → `OpenRouterBatchConfig`
    - `openrouter_multi_query_llm` → `OpenRouterMultiQueryConfig`
- Config or schema changes: None.
- Tests to add/update:
  - Add validation tests in `tests/plugins/test_validation.py` for `openrouter_batch_llm` and `openrouter_multi_query_llm` valid configs.
- Risks or migration steps:
  - None; change is additive and aligns validator with existing plugins.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- `validate_transform_config("openrouter_batch_llm", valid_config)` returns `[]`.
- `validate_transform_config("openrouter_multi_query_llm", valid_config)` returns `[]`.
- Validation tests cover both transforms.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_validation.py -k openrouter`
- New tests required: yes, add tests for OpenRouter batch and multi-query validator mapping.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
