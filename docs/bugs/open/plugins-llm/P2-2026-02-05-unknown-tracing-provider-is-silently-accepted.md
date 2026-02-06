# Bug Report: Unknown Tracing Provider Is Silently Accepted and Disables Tracing

## Summary

- Unknown `tracing.provider` values are accepted without validation, causing tracing to be silently disabled with no warning.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b (RC2.3-pipeline-row)
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A (config-only)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/plugins/llm/tracing.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure any LLM plugin with `tracing.provider` set to a typo, e.g. `langfusee`, and provide valid keys.
2. Run a pipeline using that plugin.
3. Observe that no tracing is initialized and no configuration error is logged.

## Expected Behavior

- Invalid `tracing.provider` values should be rejected or at least produce a clear validation error/warning.

## Actual Behavior

- Unknown providers are parsed into a base `TracingConfig`, pass validation, and are treated as “none,” resulting in silent tracing disablement.

## Evidence

- Supported providers are explicitly listed as `azure_ai`, `langfuse`, and `none` in the module docstring, but unknown providers are still accepted: `src/elspeth/plugins/llm/tracing.py:12`, `src/elspeth/plugins/llm/tracing.py:127`, `src/elspeth/plugins/llm/tracing.py:144`.
- `validate_tracing_config()` only validates Azure and Langfuse required fields and does not flag unknown providers: `src/elspeth/plugins/llm/tracing.py:147`, `src/elspeth/plugins/llm/tracing.py:158`, `src/elspeth/plugins/llm/tracing.py:162`.
- Call sites treat unknown providers as “no tracing” without warning: `src/elspeth/plugins/llm/azure.py:282`, `src/elspeth/plugins/llm/azure.py:287`.

## Impact

- User-facing impact: Tracing silently disappears on mis-typed provider values, leading to confusion and lost observability.
- Data integrity / security impact: Missing tracing reduces operational accountability; prompt/response visibility is lost without notice.
- Performance or cost impact: None directly, but troubleshooting time increases.

## Root Cause Hypothesis

- `parse_tracing_config()` and `validate_tracing_config()` do not enforce the supported provider set, allowing invalid providers to pass silently.

## Proposed Fix

- Code changes (modules/files): Add provider validation in `parse_tracing_config()` and/or `validate_tracing_config()` in `src/elspeth/plugins/llm/tracing.py` to emit an error for unknown providers.
- Config or schema changes: None.
- Tests to add/update: Update `tests/plugins/llm/test_tracing_config.py` to assert that unknown providers produce a validation error (or raise).
- Risks or migration steps: Existing configs with typos will now surface an error instead of silently disabling tracing.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/llm/tracing.py:12` and `CLAUDE.md:582` (No Silent Failures principle).
- Observed divergence: Unknown tracing providers are silently accepted, violating the documented supported provider list and the “no silent failures” telemetry principle.
- Reason (if known): Validation only checks required fields for known providers; unknown providers default to base config.
- Alignment plan or decision needed: Enforce provider validation and log/raise on invalid values.

## Acceptance Criteria

- Unknown tracing providers trigger a validation error or warning that is visible during `on_start()`.
- Existing valid providers (`azure_ai`, `langfuse`, `none`) remain unaffected.
- Updated tests pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/llm/test_tracing_config.py -v`
- New tests required: yes, add a test for invalid `provider` values.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/guides/tier2-tracing.md`
