# Bug Report: Azure LLM Template Rendering Ignores PipelineRow Contract (Dual-Name Resolution Broken)

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- `AzureLLMTransform._process_row()` calls `PromptTemplate.render_with_metadata()` without passing the row contract, so templates cannot resolve original header names and contract-based dual-name access fails.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: `0282d1b441fe23c5aaee0de696917187e1ceeb9b` on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline with templates referencing original (non-normalized) field names

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/llm/azure.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a pipeline that ingests data with original headers and a schema contract (e.g., CSV with `"Amount USD"`), and set an Azure LLM template referencing the original name like `{{ row["'Amount USD'"] }}`.
2. Run the pipeline through `azure_llm`.

## Expected Behavior

- Template rendering should succeed using dual-name resolution when a `PipelineRow` contract is present.

## Actual Behavior

- Template rendering fails with `template_rendering_failed` because the contract is not passed to the template renderer, so original-name access is undefined.

## Evidence

- `src/elspeth/plugins/llm/azure.py:413-420` calls `render_with_metadata(row_data)` without passing a contract.
- `src/elspeth/plugins/llm/base.py:296-305` demonstrates the expected behavior: pass `contract=input_contract` for dual-name access.
- `src/elspeth/plugins/llm/templates.py:141-194` documents that the contract enables original-name access and contract hashing.
- `docs/plans/2026-02-03-pipelinerow-migration.md:5-23` explicitly calls out dual-name field resolution and using `row.contract`.

## Impact

- User-facing impact: Templates referencing original header names fail at runtime even when those fields exist.
- Data integrity / security impact: Rows are diverted into error handling (or quarantined) due to a transform bug, not input data issues.
- Performance or cost impact: Retries or repeated failures waste LLM calls if misconfigured templates are common.

## Root Cause Hypothesis

- The contract from `PipelineRow` is never passed into `PromptTemplate.render_with_metadata()`, so dual-name resolution is unavailable in Azure LLM templates.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/plugins/llm/azure.py` to pass `contract=row.contract` into `render_with_metadata()`.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test that uses a `PipelineRow` with a contract and a template referencing original field names, asserting successful render.
- Risks or migration steps:
  - Low risk. Aligns Azure LLM behavior with `LLMBase` and documented template behavior.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/2026-02-03-pipelinerow-migration.md:5-23`, `src/elspeth/plugins/llm/templates.py:141-194`
- Observed divergence: Azure LLM template rendering ignores the contract, preventing dual-name resolution.
- Reason (if known): Likely an incomplete PipelineRow migration in this transform implementation.
- Alignment plan or decision needed: Pass `row.contract` through to the template renderer to restore dual-name support.

## Acceptance Criteria

- Templates referencing original field names render successfully when `PipelineRow.contract` is present.
- Azure LLM behavior matches the base LLM implementation for contract-aware rendering.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k azure_llm_template_contract`
- New tests required: yes, add a contract-aware template rendering test for Azure LLM

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/2026-02-03-pipelinerow-migration.md`
