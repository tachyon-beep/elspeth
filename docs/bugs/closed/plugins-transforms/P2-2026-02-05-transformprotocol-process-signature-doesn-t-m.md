# Bug Report: TransformProtocol.process Signature Doesn’t Match Batch-Aware Execution

## Summary

- `TransformProtocol.process()` is typed to accept a single `PipelineRow`, but batch-aware transforms are invoked with `list[dict[str, Any]]` during aggregation. This contract mismatch forces `type: ignore` overrides and can lead to runtime failures for batch transforms that follow the protocol signature.

## Severity

- Severity: minor
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
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/protocols.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement a batch-aware transform with `is_batch_aware = True` and `process(self, row: PipelineRow, ctx)` per `TransformProtocol`.
2. Configure an aggregation node that uses this transform and run the pipeline so aggregation flush executes.

## Expected Behavior

- The protocol signature should match the engine’s call pattern for batch-aware transforms, or the engine should pass `list[PipelineRow]` (if that is the intended contract), so batch transforms can be implemented without type ignores or runtime type mismatches.

## Actual Behavior

- The engine passes `list[dict[str, Any]]` to `transform.process()` for aggregation flush, but the protocol signature only allows `PipelineRow`, producing a contract mismatch and potential runtime errors for batch-aware transforms that follow the protocol type.

## Evidence

- `TransformProtocol.process()` is typed to accept a single `PipelineRow` only. `src/elspeth/plugins/protocols.py:211-215`.
- Aggregation flush calls `transform.process(buffered_rows, ctx)` where `buffered_rows` is `list[dict[str, Any]]`. `src/elspeth/engine/executors.py:1299-1302`.
- The protocol docstring explicitly mentions batch mode with `list[dict]`, but the signature does not reflect it. `src/elspeth/plugins/protocols.py:146-158`.

## Impact

- User-facing impact: Batch-aware transforms can crash at runtime if implemented strictly to the protocol signature.
- Data integrity / security impact: Failed batch transforms can mark batches as failed and block pipeline completion, risking dropped or quarantined outputs.
- Performance or cost impact: Repeated retries or failures in aggregation increase processing time and operational cost.

## Root Cause Hypothesis

- The protocol signature was not updated after aggregation refactoring and now diverges from the engine’s batch execution path.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/plugins/protocols.py` to model batch-aware input types, e.g., use `@overload` or a union like `PipelineRow | list[dict[str, Any]]` in `TransformProtocol.process()`, and align docstring and type hints.
- Config or schema changes: None.
- Tests to add/update: Add a lightweight typing or contract test that asserts batch-aware transforms can type-check without `type: ignore`.
- Risks or migration steps: Low risk; type-only change. Ensure it matches the current engine behavior.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): docs/plans/2026-02-03-pipelinerow-migration.md
- Observed divergence: Protocol signature only allows `PipelineRow`, while aggregation execution passes `list[dict]`.
- Reason (if known): Incomplete protocol update after aggregation refactor.
- Alignment plan or decision needed: Decide whether batch transforms should accept `list[PipelineRow]` or `list[dict]`, then update protocol accordingly and keep engine behavior aligned.

## Acceptance Criteria

- `TransformProtocol.process()` accepts the actual batch input type used by the engine.
- Batch-aware transforms no longer need `type: ignore` to satisfy protocol typing.
- Aggregation execution path remains unchanged or is updated to match the protocol contract.

## Tests

- Suggested tests to run: `.venv/bin/python -m mypy src/`
- New tests required: yes, a typing/contract check for batch-aware transform signatures.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/2026-02-03-pipelinerow-migration.md`
