# Bug Report: Azure LLM Transform Masks Missing `ctx.token` With "unknown" Token ID

**Status: CLOSED**

## Status Update (2026-02-12)

- Classification: **Fixed and verified**
- Resolution summary:
  - Removed defensive fallback token ID (`"unknown"`) from `AzureLLMTransform._process_row()`.
  - Added an explicit invariant check that raises when `ctx.token` is missing, so orchestration/context bugs fail fast.
  - Added regression coverage for direct `_process_row()` invocation with `ctx.token=None` to ensure no masked correlation path remains.
- Verification:
  - `.venv/bin/python -m pytest tests/unit/plugins/llm/test_azure.py -q` (37 passed)
  - `.venv/bin/python -m pytest tests/unit/plugins/llm -q` (505 passed, 3 deselected)
  - `.venv/bin/ruff check src/elspeth/plugins/llm/azure.py tests/unit/plugins/llm/test_azure.py` (passed)

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


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
