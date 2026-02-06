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
