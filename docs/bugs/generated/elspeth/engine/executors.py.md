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
---
# Bug Report: SinkExecutor Leaves ctx.contract Stale for Sink Writes

## Summary

- SinkExecutor does not update `ctx.contract` to reflect the contract of the tokens being written, so sinks that rely on `ctx.contract` (e.g., CSV/JSON headers in ORIGINAL mode) can use stale contracts when upstream transforms change schema.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Pipeline with a schema-changing transform and a sink configured with `headers: original`

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/executors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Use a transform that changes schema and sets `TransformResult.contract` to the new contract.
2. Configure a CSV sink with `headers: original` (or other sink behavior that depends on `ctx.contract`).
3. Run the pipeline and observe the sink output headers.

## Expected Behavior

- Sink writes should use the contract associated with the tokens being written, so header resolution reflects the transformed schema.

## Actual Behavior

- `ctx.contract` remains whatever was set by the last transform’s input, so the sink resolves headers using a stale contract.

## Evidence

- `src/elspeth/engine/executors.py:2019-2074` shows SinkExecutor writes rows without setting `ctx.contract` to the tokens’ contracts.
- `src/elspeth/engine/executors.py:251-253` sets `ctx.contract` only before transform execution (input contract) and never updates it after transform success.
- `src/elspeth/plugins/sinks/csv_sink.py:481-510` shows sinks use `ctx.contract` to set `_output_contract` for ORIGINAL header resolution.

## Impact

- User-facing impact: Sink output headers can be incorrect or incomplete when transforms change schema.
- Data integrity / security impact: Output schema provenance can diverge from actual transformed data, reducing audit reliability.
- Performance or cost impact: None.

## Root Cause Hypothesis

- SinkExecutor assumes `ctx.contract` is already correct at sink time, but it is only set pre-transform and never synchronized to token output contracts.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/executors.py`: before `sink.write()`, set `ctx.contract` to the contract of the tokens being written, and assert or merge if contracts differ.
- Config or schema changes: None.
- Tests to add/update:
  - Add a sink test that verifies ORIGINAL headers match a transform-modified contract.
- Risks or migration steps:
  - If batches can include mixed contracts, decide on enforcement or merge strategy.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Sink relies on `ctx.contract` but executor never updates it for sink writes.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Define sink-time contract propagation rule (single-contract batch or merge).

## Acceptance Criteria

- Sinks configured for ORIGINAL headers emit output headers consistent with the post-transform contract for the tokens written.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/sinks/test_csv_sink.py -k original`
- New tests required: yes, add a sink contract propagation test through TransformExecutor and SinkExecutor.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
---
# Bug Report: GateExecutor stable_hash Failure Leaves Node State OPEN

## Summary

- GateExecutor computes `stable_hash(result.row)` without error handling; if the gate emits non-canonical data (NaN/Infinity or non-serializable types), an exception is raised after `begin_node_state()`, leaving the node state OPEN with no terminal status.

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
- Data set or fixture: Gate that outputs non-canonical data (e.g., `float("nan")`) in `GateResult.row`

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/executors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a gate that returns `GateResult(row={"value": float("nan")}, action=RoutingAction.continue_())`.
2. Execute the pipeline and trigger the gate.
3. Inspect `node_states` for the gate state.

## Expected Behavior

- The gate’s node state should be completed with `FAILED` status and an error recorded when non-canonical output is produced.

## Actual Behavior

- `stable_hash(result.row)` raises, and the node state remains OPEN without a terminal status.

## Evidence

- `src/elspeth/engine/executors.py:618-621` calls `stable_hash(result.row)` without try/except or node_state completion.
- `CLAUDE.md:647-657` requires every row to reach exactly one terminal state, disallowing silent drops or open states.

## Impact

- User-facing impact: Pipeline crashes with incomplete audit records.
- Data integrity / security impact: Audit trail contains OPEN node states with no terminal status, violating auditability guarantees.
- Performance or cost impact: None.

## Root Cause Hypothesis

- GateExecutor lacks the same canonicalization error handling used by TransformExecutor/AggregationExecutor, so hash failures bypass node_state completion.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/executors.py`: wrap `stable_hash(result.row)` in try/except, record `NodeStateStatus.FAILED`, and raise a `PluginContractViolation` with context.
- Config or schema changes: None.
- Tests to add/update:
  - Add a GateExecutor test that emits NaN and asserts the node_state is marked FAILED.
- Risks or migration steps:
  - None; change is localized to gate error handling.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:647-657`
- Observed divergence: Node states can be left OPEN when gate output hashing fails.
- Reason (if known): Missing error handling around `stable_hash` for gate outputs.
- Alignment plan or decision needed: Align gate hashing error handling with TransformExecutor’s approach.

## Acceptance Criteria

- Gate outputs that fail canonicalization always result in a FAILED node_state with error details, and no OPEN states are left behind.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_gate_executor.py -k non_canonical`
- New tests required: yes, add a gate canonicalization failure test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
