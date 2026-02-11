# Bug Report: Missing `state_id` Is Silently Treated as Row Error Instead of Crash

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- When `ctx.state_id` is `None`, the plugin returns a row-level error instead of crashing, which hides a framework bug and allows the batch to complete without required audit linkage.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: `0282d1b441fe23c5aaee0de696917187e1ceeb9b` on `RC2.3-pipeline-row`
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Any batch row (e.g., `{"text": "Test"}`)

## Agent Context (if relevant)

- Goal or task prompt: Deep bug audit of `src/elspeth/plugins/llm/openrouter_batch.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `OpenRouterBatchLLMTransform` and a `PluginContext` with `state_id=None`.
2. Call `process()` with any batch row.
3. Observe a successful result with an error marker instead of an exception.

## Expected Behavior

- The transform should raise a `RuntimeError` or `FrameworkBugError` when `ctx.state_id` is missing, because this is a framework-owned invariant.

## Actual Behavior

- The transform returns `{"error": {"reason": "missing_state_id"}}` and the batch completes with `success_multi`, hiding the invariant failure.

## Evidence

- Missing `state_id` is handled by returning an error dict: `src/elspeth/plugins/llm/openrouter_batch.py:573`
- Batch path converts this into a success row with error markers: `src/elspeth/plugins/llm/openrouter_batch.py:473`
- Test currently codifies this behavior: `tests/plugins/llm/test_openrouter_batch.py:468`
- Defensive-programming prohibition requires crashing on framework bugs: `CLAUDE.md:972`

## Impact

- User-facing impact: Pipeline may appear to succeed while silently skipping external call recording.
- Data integrity / security impact: Audit trail loses required call linkage (no `state_id`), violating audit invariants.
- Performance or cost impact: None direct, but debugging cost increases due to hidden framework bugs.

## Root Cause Hypothesis

- The plugin treats missing `ctx.state_id` as a recoverable row error instead of a framework invariant breach.

## Proposed Fix

- Code changes (modules/files):
`src/elspeth/plugins/llm/openrouter_batch.py`: replace the `return {"error": {"reason": "missing_state_id"}}` branch with a hard failure (e.g., `RuntimeError`), matching other LLM transforms.
- Config or schema changes: None.
- Tests to add/update:
Update `tests/plugins/llm/test_openrouter_batch.py::test_missing_state_id_returns_error` to assert an exception.
- Risks or migration steps:
Tests will need updating; behavior becomes fail-fast as required by audit rules.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:918`
- Observed divergence: Framework-owned invariants (`ctx.state_id`) are handled defensively instead of crashing.
- Reason (if known): Likely introduced to keep unit tests passing without full context wiring.
- Alignment plan or decision needed: Enforce crash-on-bug invariant and update tests accordingly.

## Acceptance Criteria

- Calling `process()` with `ctx.state_id=None` raises immediately.
- Tests reflect the new invariant and pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/llm/test_openrouter_batch.py`
- New tests required: yes, update existing test to expect an exception.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
