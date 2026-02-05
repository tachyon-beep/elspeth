# Bug Report: TransformExecutor Drops Input Contract When TransformResult.contract Is None

## Summary

- TransformExecutor replaces the input contract with a new contract derived from `transform.output_schema` when `TransformResult.contract` is `None`, which discards original header mappings and breaks PipelineRow dual-name access, contrary to the PipelineRow migration plan.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Pipeline with source headers needing original-name resolution and a transform that does not set `TransformResult.contract`

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/executors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Use a source with original headers (e.g., CSV header `"Amount USD"` normalized to `amount_usd`) so the initial `SchemaContract` stores original names.
2. Add a pass-through transform that returns `TransformResult.success(row_dict, ...)` without setting `TransformResult.contract`.
3. Add a downstream transform or sink that relies on original header access (e.g., `row["Amount USD"]` or a sink with `headers: original`).
4. Run the pipeline.

## Expected Behavior

- The output contract should preserve original header mappings when a transform does not explicitly supply a new contract, so original-name access continues to work.

## Actual Behavior

- The contract is replaced by one built from `transform.output_schema` with `original_name == normalized_name`, so original-name resolution is lost after the first transform that omits `TransformResult.contract`.

## Evidence

- `src/elspeth/engine/executors.py:408-419` shows fallback to `create_output_contract_from_schema(transform.output_schema)` when `result.contract` is `None`, replacing the input contract.
- `src/elspeth/contracts/transform_contract.py:63-118` shows `create_output_contract_from_schema()` sets `original_name=name`, which discards source header mappings.
- `src/elspeth/contracts/schema_contract.py:518-538` shows `PipelineRow.__getitem__()` relies on `contract.resolve_name()` for original-name access.
- `docs/plans/2026-02-03-pipelinerow-migration.md:734-773` specifies the intended executor behavior: `output_contract = result.contract if result.contract else token.row_data.contract`.

## Impact

- User-facing impact: Original header names stop resolving after the first transform that omits `TransformResult.contract`; templates or sink output headers can be wrong.
- Data integrity / security impact: Contract lineage no longer preserves source header provenance, weakening audit traceability.
- Performance or cost impact: None.

## Root Cause Hypothesis

- TransformExecutor defaults to a schema-derived contract instead of preserving the input contract, so original-name metadata is lost unless every transform explicitly sets `TransformResult.contract`.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/executors.py`: change fallback to `token.row_data.contract`, or merge input contract with output schema using `contracts/contract_propagation.merge_contract_with_output()` when `result.contract` is `None`.
- Config or schema changes: None.
- Tests to add/update:
  - Add a test in `tests/engine/test_executors.py` asserting original-name access still works after a transform that does not supply a contract.
- Risks or migration steps:
  - If any transforms relied on output-schema-derived contracts to narrow fields, they should start providing `TransformResult.contract` explicitly.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/2026-02-03-pipelinerow-migration.md:734-773`
- Observed divergence: Executor uses `transform.output_schema` fallback instead of preserving `token.row_data.contract`.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Align TransformExecutor with the migration plan’s contract propagation rule.

## Acceptance Criteria

- A pipeline with a pass-through transform (no `TransformResult.contract`) preserves original header resolution in downstream transforms and sinks.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_executors.py -k contract`
- New tests required: yes, add a transform contract propagation test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/2026-02-03-pipelinerow-migration.md`
