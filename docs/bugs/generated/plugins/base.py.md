# Bug Report: BaseTransform Batch Contract Mismatch

## Summary

- BaseTransform documents batch-aware list input but its abstract `process()` signature only allows a dict, causing type ignores and mismatched implementations when aggregation passes lists.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-01-25
- Related run/issue ID: N/A

## Environment

- Commit/branch: 8635789 (fix/rc1-bug-burndown-session-4)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/plugins/base.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Implement or inspect a batch-aware transform that overrides `process(self, rows: list[dict[str, Any]], ...)` (e.g., `BatchStats`).
2. Run a type checker (mypy) or observe the required `# type: ignore[override]` to satisfy the BaseTransform signature.
3. Inspect aggregation execution where the engine calls `transform.process(buffered_rows, ctx)` with a list.

## Expected Behavior

- The BaseTransform contract should explicitly accept `dict[str, Any] | list[dict[str, Any]]` for batch-aware usage so type checking and implementations align without ignores.

## Actual Behavior

- BaseTransform.process only declares `dict[str, Any]`, forcing incompatible overrides and `# type: ignore` annotations in batch-aware transforms and aggregation execution.

## Evidence

- BaseTransform describes list input but declares a dict-only signature: `src/elspeth/plugins/base.py:29`, `src/elspeth/plugins/base.py:77`.
- Aggregation executes `transform.process(buffered_rows, ctx)` with list input and suppresses typing: `src/elspeth/engine/executors.py:941`.
- Batch-aware transforms require `# type: ignore[override]` due to the mismatch: `src/elspeth/plugins/transforms/batch_stats.py:108`, `src/elspeth/plugins/transforms/batch_replicate.py:101`.

## Impact

- User-facing impact: Developers implementing batch-aware transforms can follow the dict-only signature and hit runtime errors or incorrect behavior when aggregation passes lists.
- Data integrity / security impact: Failed or mis-processed batch aggregates can cause rows to be marked FAILED/QUARANTINED, reducing audit completeness for those runs.
- Performance or cost impact: Type ignores reduce static safety and can delay detection of integration mistakes.

## Root Cause Hypothesis

- The BaseTransform interface was not updated when batch-aware aggregation switched to passing `list[dict]`, leaving the contract narrower than actual runtime behavior.

## Proposed Fix

- Code changes (modules/files):
  - Update `BaseTransform.process` to accept `dict[str, Any] | list[dict[str, Any]]` and clarify the docstring in `src/elspeth/plugins/base.py`.
  - Align `TransformProtocol.process` with the same union type and update batch-aware transforms to use the union signature (remove `# type: ignore[override]`).
  - Remove `# type: ignore[arg-type]` in `src/elspeth/engine/executors.py` once types align.
- Config or schema changes: None.
- Tests to add/update:
  - Optional: add/extend static type checking to ensure batch-aware signatures pass without ignores.
- Risks or migration steps:
  - Ensure any custom transforms are updated to accept both single-row and batch inputs; document the union signature in plugin docs.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `PLUGIN.md:163`, `PLUGIN.md:257`.
- Observed divergence: Docs describe batch-aware transforms receiving `list[dict]`, but the BaseTransform signature only permits `dict`, forcing type ignores and mismatched typing.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Update the BaseTransform contract (and protocols) to reflect batch input and remove type ignores in engine and transforms.

## Acceptance Criteria

- BaseTransform and TransformProtocol accept `dict | list[dict]` inputs.
- Batch-aware transforms compile without `# type: ignore[override]`.
- Aggregation execution no longer needs `# type: ignore[arg-type]` when calling `transform.process`.

## Tests

- Suggested tests to run: `.venv/bin/python -m mypy src/`, `.venv/bin/python -m ruff check src/`.
- New tests required: no (optional: type-checking coverage for batch-aware signatures).

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `PLUGIN.md`
