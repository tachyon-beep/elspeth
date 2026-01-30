# Bug Report: Unhandled canonicalization errors during template rendering crash Azure LLM transform

## Summary

- `AzureLLMTransform` only catches `TemplateError` from `render_with_metadata()`, but that helper can raise `ValueError`/`TypeError` when row data contains NaN/Infinity or non-serializable values; the exception propagates as a plugin bug and aborts the run instead of returning `TransformResult.error()`.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Row with float('nan') / Decimal('NaN') / non-JSON-serializable value in a dynamic schema row

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure `azure_llm` with a dynamic schema and `on_error` sink.
2. Process a row that includes `float("nan")`, `float("inf")`, or another value rejected by canonical JSON.

## Expected Behavior

- The transform should return `TransformResult.error()` with an actionable reason and route the row to `on_error` (row-scoped failure), keeping the run alive.

## Actual Behavior

- `canonical_json(row)` inside `render_with_metadata()` raises `ValueError`/`TypeError`, which is not caught in `AzureLLMTransform._process_row()` and propagates as an exception; the executor records a failed node state and the run aborts rather than quarantining the row.

## Evidence

- `AzureLLMTransform._process_row()` only catches `TemplateError`, not canonicalization errors: `src/elspeth/plugins/llm/azure.py:282-293`.
- `render_with_metadata()` computes `variables_hash = canonical_json(row)` without exception wrapping: `src/elspeth/plugins/llm/templates.py:163-176`.
- `canonical_json()` rejects NaN/Infinity by raising `ValueError`: `src/elspeth/core/canonical.py:39-114`.

## Impact

- User-facing impact: A single row with NaN/Infinity (valid type, invalid value) can crash the entire run instead of being routed to `on_error`.
- Data integrity / security impact: Violates the Tier‑2 rule to wrap operations on row values; error is not recorded as a row-level failure.
- Performance or cost impact: Run aborts mid-stream; possible retry churn if configured.

## Root Cause Hypothesis

- `AzureLLMTransform` assumes `render_with_metadata()` only raises `TemplateError`, but `canonical_json()` can throw on row values; missing try/except around those exceptions at the transform boundary.

## Proposed Fix

- Code changes (modules/files):
  - Add a broader exception handler in `src/elspeth/plugins/llm/azure.py` around `render_with_metadata()` to catch `ValueError`/`TypeError` (and return `TransformResult.error()` with a clear reason like `invalid_row_data_for_hashing`).
- Config or schema changes: None.
- Tests to add/update:
  - Add a unit test that feeds a row with `float("nan")` (or `Decimal("NaN")`) and asserts `TransformResult.error()` is returned and routed to `on_error`.
- Risks or migration steps:
  - Ensure the error reason is consistent with other LLM transforms if similar handling is added elsewhere.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:196` (Operation Wrapping Rules)
- Observed divergence: Row-value operations (`canonical_json(row)`) are not wrapped at the transform boundary.
- Reason (if known): Missing catch for non-TemplateError exceptions from `render_with_metadata()`.
- Alignment plan or decision needed: Add explicit handling for canonicalization failures in the transform (and align other LLM transforms if desired).

## Acceptance Criteria

- A row containing NaN/Infinity or non-serializable values no longer crashes the run; it yields `TransformResult.error()` and is routed to `on_error`.
- Audit trail records the transform error with an actionable reason.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/llm/test_azure.py -k nan`
- New tests required: yes, add a unit test covering canonicalization failure in template rendering.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Operation Wrapping Rules)
