# Bug Report: OpenRouter LLM Template Rendering Ignores Schema Contract (Original Header Names Fail)

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- OpenRouter LLM transform calls `PromptTemplate.render_with_metadata()` without passing the schema contract, so templates that use original header names (supported by PipelineRow/contract) fail with `TemplateError` and are routed to `on_error`.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: CSV/source with headers that normalize (e.g., `"Amount USD"` → `amount_usd`) and an OpenRouter template referencing original header name.

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/plugins/llm/openrouter.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Use a source schema that includes original header names (e.g., original `"Amount USD"` normalized to `amount_usd`) and produces a `PipelineRow`.
2. Configure `openrouter_llm` with a template like `Amount: {{ row["Amount USD"] }}` (or `{{ row["'Amount USD'"] }}`) and run the pipeline.
3. Observe the OpenRouter transform’s template rendering.

## Expected Behavior

- Template rendering should resolve original header names via the schema contract and complete successfully.

## Actual Behavior

- Template rendering fails with `TemplateError` (undefined variable), and the transform returns `TransformResult.error`, routing the row to `on_error` if configured.

## Evidence

- `src/elspeth/plugins/llm/openrouter.py:500-506` calls `render_with_metadata(row_data)` without `contract=...`, so original-name resolution is unavailable.
- `src/elspeth/plugins/context.py:106-111` documents that `ctx.contract` exists specifically to enable templates to resolve original header names.
- `docs/plans/2026-02-03-pipelinerow-migration.md:18-23` states that transforms receiving `PipelineRow` should use `row.contract`, with `ctx.contract` as a valid fallback.

## Impact

- User-facing impact: Templates that legitimately reference original header names fail at runtime, causing unexpected row errors.
- Data integrity / security impact: Rows are incorrectly routed to error handling; audit trail reflects processing failures that are actually integration bugs.
- Performance or cost impact: Additional retries/error handling overhead; potential wasted LLM calls if failures occur after partial processing.

## Root Cause Hypothesis

- The OpenRouter transform does not pass the available schema contract (`row.contract` or `ctx.contract`) into `PromptTemplate.render_with_metadata()`, so original header names cannot be resolved.

## Proposed Fix

- Code changes (modules/files):
- Pass `contract=row.contract` (or `ctx.contract` as fallback) into `render_with_metadata()` in `src/elspeth/plugins/llm/openrouter.py`.
- Config or schema changes: None.
- Tests to add/update:
- Add a test that exercises `OpenRouterLLMTransform` with a template referencing an original header name and verifies successful rendering (mock HTTP call).
- Risks or migration steps:
- None; change is additive and aligns with existing contract-aware template behavior.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/2026-02-03-pipelinerow-migration.md:18-23`, `src/elspeth/plugins/context.py:106-111`.
- Observed divergence: OpenRouter transform ignores the contract when rendering templates.
- Reason (if known): Likely missed during PipelineRow migration for LLM transforms.
- Alignment plan or decision needed: Use `row.contract` (or `ctx.contract`) when rendering templates in OpenRouter transform.

## Acceptance Criteria

- Templates that use original header names render successfully in `openrouter_llm`.
- No `TemplateError` occurs for valid original-name references when `PipelineRow` carries a contract.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/integration/test_llm_transforms.py -k openrouter`
- New tests required: yes, add a contract-aware template rendering test for `openrouter_llm`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/2026-02-03-pipelinerow-migration.md`

## Resolution (2026-02-12)

- Status: CLOSED
- Fixed by commit: `62ea627f`
- Fix summary: Refactor selected plugins to PipelineRow-first access
- Ticket moved from `docs/bugs/open/` to `docs/bugs/closed/` on 2026-02-12.

