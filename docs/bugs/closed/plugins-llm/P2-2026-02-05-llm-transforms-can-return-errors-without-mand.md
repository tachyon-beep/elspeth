# Bug Report: LLM Transforms Can Return Errors Without Mandatory `on_error`, Causing Runtime Crash

**Status: OVERTAKEN BY EVENTS**

## Status Update (2026-02-13)

- Classification: **Overtaken by events**
- Verification summary:
  - `on_error` is required by `TransformSettings` at configuration boundary, so LLM transforms cannot be instantiated without it in normal pipeline config.
  - Transform execution path now treats missing `on_error` as an invariant violation rather than a user-configurable runtime case.
- Current evidence:
  - `src/elspeth/core/config.py:824`
  - `src/elspeth/core/config.py:867`
  - `src/elspeth/engine/executors/transform.py:382`


## Summary

- `BaseLLMTransform` returns `TransformResult.error()` for template and non-retryable LLM failures, but `LLMConfig` does not require `on_error`, so the executor raises a runtime error instead of routing/quarantining rows.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a `BaseLLMTransform` subclass without `on_error`.
2. Run a row that triggers `TemplateError` (missing template field) or a non-retryable `LLMClientError` (content policy/context length).
3. Observe the executor raising a runtime error instead of routing the row.

## Expected Behavior

- Configuration should require `on_error` for LLM transforms, or the transform should default to a safe error sink (e.g., `discard`) to avoid pipeline crashes on expected external failures.

## Actual Behavior

- The executor raises `RuntimeError` because `on_error` is `None`, crashing the pipeline when an LLM error occurs.

## Evidence

- `BaseLLMTransform` returns `TransformResult.error()` on template and non-retryable LLM errors in `src/elspeth/plugins/llm/base.py:303-343`.
- `LLMConfig` assigns `_on_error` from config without enforcing it in `src/elspeth/plugins/llm/base.py:221-235`.
- Executor raises when `on_error` is missing in `src/elspeth/engine/executors.py:451-456`.
- Transform config doc states `on_error` is required if a transform can return errors in `src/elspeth/plugins/config_base.py:324-344`.

## Impact

- User-facing impact: Pipeline crashes on expected external LLM failures (template issues, content policy, context length).
- Data integrity / security impact: Rows are not quarantined or routed, breaking expected audit trail flow.
- Performance or cost impact: Wasted run time due to hard failures and reruns.

## Root Cause Hypothesis

- `LLMConfig` does not enforce `on_error` even though `BaseLLMTransform` can return error results for normal external failure modes.

## Proposed Fix

- Code changes (modules/files):
  - Add a `model_validator` in `src/elspeth/plugins/llm/base.py` `LLMConfig` to require `on_error` be non-None.
- Config or schema changes: None.
- Tests to add/update:
  - Add a config validation test asserting `LLMConfig` rejects missing `on_error` for LLM transforms.
- Risks or migration steps:
  - Configs without `on_error` will fail validation and must be updated.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/config_base.py:324-344`
- Observed divergence: LLM transforms can return errors but `on_error` is not required at config time.
- Reason (if known): Missing validation in `LLMConfig`.
- Alignment plan or decision needed: Enforce `on_error` for LLM transforms at config validation.

## Acceptance Criteria

- Creating an LLM transform config without `on_error` fails fast with a clear validation error.
- LLM errors route to the configured sink instead of crashing the pipeline.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/ -k llm`
- New tests required: yes, configuration validation test for `LLMConfig` requiring `on_error`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/plugins/config_base.py`
