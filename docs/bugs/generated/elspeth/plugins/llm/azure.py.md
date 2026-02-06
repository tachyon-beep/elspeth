# Bug Report: Azure LLM Template Rendering Ignores PipelineRow Contract (Dual-Name Resolution Broken)

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
---
# Bug Report: Azure LLM Transform Masks Missing `ctx.token` With "unknown" Token ID

## Summary

- `AzureLLMTransform._process_row()` uses `"unknown"` when `ctx.token` is `None`, masking orchestrator bugs and breaking trace correlation.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: `0282d1b441fe23c5aaee0de696917187e1ceeb9b` on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/llm/azure.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Invoke `_process_row()` (or misconfigure execution) with `ctx.token = None`.
2. Observe the Langfuse trace/error recording uses `token_id="unknown"` rather than crashing.

## Expected Behavior

- The transform should raise immediately when `ctx.token` is missing, because batch transforms are supposed to be invoked with a token attached.

## Actual Behavior

- Execution proceeds with `token_id="unknown"`, masking an orchestrator or context synchronization bug.

## Evidence

- `src/elspeth/plugins/llm/azure.py:449` assigns `token_id = ctx.token.token_id if ctx.token else "unknown"`.
- `src/elspeth/engine/executors.py:281-283` sets `ctx.token` before calling `accept()` for batch transforms, so a missing token indicates a system bug.
- `CLAUDE.md:918-975` prohibits defensive patterns that mask system-owned data errors.

## Impact

- User-facing impact: Tracing and correlation data becomes unreliable or misleading.
- Data integrity / security impact: Hidden orchestration bugs can persist undetected, weakening audit confidence.
- Performance or cost impact: Minimal, but debugging time increases due to silent masking.

## Root Cause Hypothesis

- Defensive fallback introduced for token correlation hides a system invariant violation instead of surfacing it.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/plugins/llm/azure.py` to raise a `RuntimeError` (or assert) if `ctx.token` is `None` before using it.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test that ensures `_process_row()` raises when `ctx.token` is missing.
- Risks or migration steps:
  - Low risk. Aligns with the “no defensive programming” rule for system-owned data.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:918-975`
- Observed divergence: The transform hides missing system-owned context rather than crashing.
- Reason (if known): Likely added to avoid runtime crashes in tracing, but violates project guidance.
- Alignment plan or decision needed: Enforce invariant by raising when `ctx.token` is missing.

## Acceptance Criteria

- Missing `ctx.token` causes an immediate, explicit failure with a clear error.
- Langfuse trace correlation always uses a real token ID.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k azure_llm_missing_token`
- New tests required: yes, add a missing-token invariant test

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
