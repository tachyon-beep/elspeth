# Bug Report: Gate/config gate/sink executions do not initialize PluginContext state_id for call recording

## Summary

- GateExecutor.execute_gate/execute_config_gate and SinkExecutor.write never set `ctx.state_id`/`ctx.node_id`/`ctx._call_index` before plugin execution, so `ctx.record_call()` either raises or records against a stale transform state, breaking external call auditability.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/rc1-bug-burndown-session-4 @ 8635789
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: Unknown
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/engine/executors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: static inspection only

## Steps To Reproduce

1. Implement a gate or sink that calls `ctx.record_call(...)` during execution.
2. Run a pipeline that executes the gate/sink after any transform.
3. Observe a `RuntimeError` when `ctx.state_id` is None, or a call recorded against the previous transform’s state when `ctx.state_id` is stale.

## Expected Behavior

- Gate/sink executions should initialize `ctx.state_id`/`ctx.node_id` and reset `ctx._call_index`, enabling correct call recording per node_state.

## Actual Behavior

- `ctx.state_id` is never set for gates/sinks, so `ctx.record_call()` raises or misattributes calls to the last transform’s node_state.

## Evidence

- Transform executor sets context state before execution: `src/elspeth/engine/executors.py:161`, `src/elspeth/engine/executors.py:170`, `src/elspeth/engine/executors.py:172`, `src/elspeth/engine/executors.py:174`.
- Gate executor opens node_state and calls `gate.evaluate(...)` without setting ctx state: `src/elspeth/engine/executors.py:360`, `src/elspeth/engine/executors.py:368`, `src/elspeth/engine/executors.py:371`.
- Config gate similarly omits ctx state before evaluation: `src/elspeth/engine/executors.py:517`, `src/elspeth/engine/executors.py:526`, `src/elspeth/engine/executors.py:530`.
- Sink executor opens node_states and calls `sink.write(...)` without setting ctx state: `src/elspeth/engine/executors.py:1434`, `src/elspeth/engine/executors.py:1444`, `src/elspeth/engine/executors.py:1448`.
- `ctx.record_call()` raises when `state_id` is None: `src/elspeth/plugins/context.py:223`.

## Impact

- User-facing impact: gates/sinks that attempt external calls via `ctx.record_call()` crash or misrecord calls.
- Data integrity / security impact: external calls are missing or misattributed in the audit trail.
- Performance or cost impact: failed runs when gates/sinks call external services.

## Root Cause Hypothesis

- Context initialization for call recording was implemented for TransformExecutor/AggregationExecutor but not for gates or sinks.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/executors.py`: set `ctx.state_id`, `ctx.node_id`, and reset `ctx._call_index` in `GateExecutor.execute_gate()` before `gate.evaluate(...)`.
  - `src/elspeth/engine/executors.py`: set `ctx.state_id`, `ctx.node_id`, and reset `ctx._call_index` in `GateExecutor.execute_config_gate()` before expression evaluation.
  - `src/elspeth/engine/executors.py`: set `ctx.state_id`/`ctx.node_id` for `SinkExecutor.write()` (choose a representative state_id, or define per-token call recording semantics).
- Config or schema changes: Unknown
- Tests to add/update:
  - Add gate and sink tests that call `ctx.record_call()` and verify calls recorded against the correct node_state.
- Risks or migration steps:
  - Decide and document sink call attribution policy when writing multiple tokens.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md`
- Observed divergence: gate/sink external calls cannot be recorded via PluginContext.
- Reason (if known): context state initialization only exists in transform/aggregation paths.
- Alignment plan or decision needed: define node_state ownership for sink-level call records.

## Acceptance Criteria

- Gates and sinks can call `ctx.record_call()` without raising.
- Call records are attached to the correct node_state with per-state call_index reset.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_executors.py -k record_call`
- New tests required: yes, gate/sink call-recording coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
---
# Bug Report: Aggregation flush input hash mismatch between node_state and TransformResult

## Summary

- `AggregationExecutor.execute_flush()` hashes `buffered_rows` for `result.input_hash` but records the node_state input hash from `{"batch_rows": buffered_rows}`, so the two hashes disagree for the same logical input.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/rc1-bug-burndown-session-4 @ 8635789
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: Unknown
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/engine/executors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: static inspection only

## Steps To Reproduce

1. Configure a batch aggregation and trigger a flush.
2. Inspect `node_states.input_hash` for the flush state.
3. Compare it to `TransformResult.input_hash` returned by `execute_flush()`.

## Expected Behavior

- The node_state input hash and the TransformResult input hash match for the same aggregation input.

## Actual Behavior

- The node_state input hash is computed from `{"batch_rows": buffered_rows}` while the TransformResult uses `buffered_rows`, producing different hashes.

## Evidence

- `input_hash` computed from list of rows: `src/elspeth/engine/executors.py:907`.
- Node state input is wrapped dict: `src/elspeth/engine/executors.py:922`, `src/elspeth/engine/executors.py:923`.
- `begin_node_state()` hashes the provided input_data: `src/elspeth/core/landscape/recorder.py:1045`.
- Result uses the list-derived hash: `src/elspeth/engine/executors.py:996`.

## Impact

- User-facing impact: explain/export views show inconsistent hashes for the same aggregation flush.
- Data integrity / security impact: hash-based verification and audit consistency are broken for aggregation inputs.
- Performance or cost impact: none direct.

## Root Cause Hypothesis

- Two different representations of the batch input are hashed in the same operation.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/executors.py`: compute `input_hash` from the same `batch_input` dict passed to `begin_node_state()`, or pass `buffered_rows` directly to `begin_node_state()` so both hashes align.
- Config or schema changes: Unknown
- Tests to add/update:
  - Add a test asserting `result.input_hash == node_state.input_hash` for aggregation flushes.
- Risks or migration steps:
  - None; deterministic hash alignment only.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md`
- Observed divergence: aggregation input hashes are inconsistent between audit state and result.
- Reason (if known): hashing two different input shapes.
- Alignment plan or decision needed: standardize aggregation input representation for hashing.

## Acceptance Criteria

- Aggregation flush node_state and TransformResult share identical input_hash values.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_executors.py -k aggregation_input_hash`
- New tests required: yes, hash consistency check.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
---
# Bug Report: Aggregation flushes emit transform spans without batch_id

## Summary

- `AggregationExecutor.execute_flush()` uses `transform_span` instead of `aggregation_span`, so aggregation flushes are indistinguishable from normal transforms and omit `batch.id` attributes.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/rc1-bug-burndown-session-4 @ 8635789
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: Unknown
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/engine/executors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: static inspection only

## Steps To Reproduce

1. Run a pipeline with an aggregation that flushes while tracing is enabled.
2. Inspect spans emitted during flush.
3. Observe they are `transform:*` spans without `batch.id`.

## Expected Behavior

- Aggregation flushes emit `aggregation:*` spans and include `batch.id` metadata.

## Actual Behavior

- Flushes emit `transform:*` spans with no batch_id.

## Evidence

- Aggregation flush uses transform_span: `src/elspeth/engine/executors.py:937`, `src/elspeth/engine/executors.py:938`.
- aggregation_span exists and supports batch_id: `src/elspeth/engine/spans.py:193`, `src/elspeth/engine/spans.py:198`, `src/elspeth/engine/spans.py:213`.

## Impact

- User-facing impact: traces cannot distinguish aggregation flushes from normal transforms.
- Data integrity / security impact: observability cannot correlate spans with batch audit records.
- Performance or cost impact: harder diagnosis of batch behavior and backpressure.

## Root Cause Hypothesis

- execute_flush reuses transform_span instead of the aggregation-specific span.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/executors.py`: replace `transform_span` with `aggregation_span`, passing `batch_id`.
- Config or schema changes: Unknown
- Tests to add/update:
  - Add span tests verifying aggregation flush spans include `batch.id`.
- Risks or migration steps:
  - None; tracing-only change.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/engine/spans.py:193`
- Observed divergence: aggregation spans are defined but never used for flushes.
- Reason (if known): execute_flush calls transform_span.
- Alignment plan or decision needed: use aggregation_span in flush execution.

## Acceptance Criteria

- Aggregation flush spans are labeled as aggregation operations and include `batch.id`.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_spans.py -k aggregation`
- New tests required: yes, aggregation span coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/engine/spans.py`
---
# Bug Report: Sink flush failures leave sink node_states OPEN

## Summary

- `SinkExecutor.write()` calls `sink.flush()` outside any error handling; if flush raises, per-token node_states are never completed or marked failed, leaving OPEN audit records.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: fix/rc1-bug-burndown-session-4 @ 8635789
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: Unknown
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/engine/executors.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: static inspection only

## Steps To Reproduce

1. Implement a sink whose `flush()` raises (simulate disk/full I/O failure).
2. Run a pipeline that writes at least one token to the sink.
3. Inspect `node_states` for the sink node and see OPEN states with no completion.

## Expected Behavior

- Flush failures should complete all sink node_states with status `failed` and error details before raising.

## Actual Behavior

- Flush exceptions propagate without completing node_states.

## Evidence

- Sink node_states opened per token: `src/elspeth/engine/executors.py:1434`, `src/elspeth/engine/executors.py:1436`.
- `sink.flush()` called without try/except: `src/elspeth/engine/executors.py:1466`, `src/elspeth/engine/executors.py:1468`.

## Impact

- User-facing impact: failed sink flushes leave incomplete audit trails.
- Data integrity / security impact: tokens lack terminal states on flush failure.
- Performance or cost impact: manual recovery required; retries may be unsafe.

## Root Cause Hypothesis

- Flush is treated as “must crash” but error paths do not complete node_states.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/executors.py`: wrap `sink.flush()` in try/except, call `complete_node_state(status="failed", error=...)` for all token states, then re-raise.
- Config or schema changes: Unknown
- Tests to add/update:
  - Add a sink flush failure test that asserts failed node_state completion.
- Risks or migration steps:
  - Ensure artifact registration does not run when flush fails.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md`
- Observed divergence: sink failures leave OPEN node_states (no terminal audit state).
- Reason (if known): missing error handling around flush.
- Alignment plan or decision needed: enforce terminal node_state on flush errors.

## Acceptance Criteria

- Flush failures always produce failed node_state records for each token.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/engine/test_executors.py -k sink_flush_failure`
- New tests required: yes, sink flush failure audit tests.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
