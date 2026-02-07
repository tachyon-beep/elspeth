# Bug Report: Per-criterion `max_tokens` ignored in OpenRouter multi-query

## Summary

- `CriterionConfig.max_tokens` is validated but never propagated to `QuerySpec` in `OpenRouterMultiQueryConfig`, so per-criterion token limits are ignored.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 0282d1b441fe23c5aaee0de696917187e1ceeb9b
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Pipeline config with `criteria[].max_tokens` set

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/llm/openrouter_multi_query.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `openrouter_multi_query_llm` with `criteria` entries that set `max_tokens` (e.g., 64).
2. Run the pipeline for any row and inspect the recorded request body in the audit trail or payload store.
3. Observe that `max_tokens` uses the transform default, not the per-criterion value.

## Expected Behavior

- Per-criterion `max_tokens` should be applied when building requests (override transform default).

## Actual Behavior

- `spec.max_tokens` is always `None`, so `effective_max_tokens` always falls back to the transform-level `max_tokens`.

## Evidence

- `CriterionConfig` defines `max_tokens`. `src/elspeth/plugins/llm/multi_query.py:174-178`
- `OpenRouterMultiQueryConfig.expand_queries()` does not pass `criterion.max_tokens` into `QuerySpec`. `src/elspeth/plugins/llm/openrouter_multi_query.py:175-186`
- `_process_single_query()` uses `spec.max_tokens` to set `effective_max_tokens`, so the missing mapping makes the override unreachable. `src/elspeth/plugins/llm/openrouter_multi_query.py:734-736`
- Azure multi-query correctly propagates `criterion.max_tokens`. `src/elspeth/plugins/llm/multi_query.py:339-346`

## Impact

- User-facing impact: Per-criterion token budgeting is ignored, leading to unexpected truncation or cost.
- Data integrity / security impact: N/A
- Performance or cost impact: Potentially higher token usage and latency.

## Root Cause Hypothesis

- Missing settings→runtime mapping in `OpenRouterMultiQueryConfig.expand_queries()`.

## Proposed Fix

- Code changes (modules/files): Add `max_tokens=criterion.max_tokens` when building `QuerySpec` in `OpenRouterMultiQueryConfig.expand_queries()`.
- Config or schema changes: None.
- Tests to add/update: Add unit test verifying `criteria[].max_tokens` is reflected in request body for OpenRouter multi-query.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md#L665-L682` (Settings→Runtime Field Mapping)
- Observed divergence: A validated settings field is never used at runtime.
- Reason (if known): OpenRouter variant did not carry over the mapping from the Azure multi-query configuration.
- Alignment plan or decision needed: Align OpenRouter multi-query config mapping with `MultiQueryConfig`.

## Acceptance Criteria

- `criteria[].max_tokens` overrides are applied per query in OpenRouter multi-query.
- A unit test confirms the override is reflected in request payloads.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_openrouter_multi_query.py`
- New tests required: yes, add coverage for per-criterion max_tokens propagation.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Settings→Runtime Field Mapping)
