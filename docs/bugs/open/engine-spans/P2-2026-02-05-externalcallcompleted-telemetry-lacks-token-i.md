# Bug Report: ExternalCallCompleted telemetry lacks token_id for correlation

## Summary

- `ExternalCallCompleted` does not include `token_id`, violating the telemetry correlation workflow requirement and making external-call telemetry hard to tie to a specific row/token.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b4 / RC2.3-pipeline-row
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline emitting `ExternalCallCompleted` (LLM/HTTP/SQL)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/telemetry/events.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Enable telemetry with `granularity: full` and a console/OTLP exporter.
2. Run a pipeline with an external call (e.g., LLM transform using `AuditedLLMClient`).
3. Inspect `ExternalCallCompleted` output; it has `state_id` or `operation_id` but no `token_id`.

## Expected Behavior

- `ExternalCallCompleted` includes `token_id` for transform-context calls, consistent with the correlation workflow expectation that telemetry events include `run_id` and `token_id`.

## Actual Behavior

- `ExternalCallCompleted` schema lacks a `token_id` field, so emitted events cannot include it.

## Evidence

- Telemetry correlation requirement: `CLAUDE.md:623` states telemetry events include `run_id` and `token_id`.
- `ExternalCallCompleted` lacks `token_id` in its dataclass definition: `src/elspeth/telemetry/events.py:127-165`.
- Emission example shows no token field is available to pass: `src/elspeth/plugins/clients/llm.py:350-364`.

## Impact

- User-facing impact: Operational debugging is harder; external-call telemetry cannot be directly correlated to a row/token without an extra state_id join.
- Data integrity / security impact: None.
- Performance or cost impact: None.

## Root Cause Hypothesis

- The `ExternalCallCompleted` event schema omitted a `token_id` field, so callers cannot emit token correlation even when the call originates from a token-bound transform.

## Proposed Fix

- Code changes (modules/files): Add `token_id: str | None` to `ExternalCallCompleted` in `src/elspeth/telemetry/events.py`, and populate it in call sites (e.g., `AuditedLLMClient`, `AuditedHTTPClient`, `PluginContext.record_call`) when `state_id` is set.
- Config or schema changes: None.
- Tests to add/update: Add/update telemetry event tests to assert `ExternalCallCompleted` includes `token_id` for transform context and allows `None` for operation context.
- Risks or migration steps: Requires updating event constructors in audited clients; exporters will include the new field automatically via `asdict`.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:623` (telemetry events include `run_id` and `token_id`).
- Observed divergence: `ExternalCallCompleted` lacks `token_id`, so external-call telemetry cannot follow the documented correlation workflow.
- Reason (if known): Likely omission when defining telemetry event schema.
- Alignment plan or decision needed: Add `token_id` to the event schema and populate it at emit sites.

## Acceptance Criteria

- `ExternalCallCompleted` includes `token_id` for transform-context calls.
- Operation-context calls can omit `token_id` without validation errors.
- Telemetry exporters surface the new field in emitted data.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/telemetry/ tests/plugins/clients/ tests/plugins/test_context.py`
- New tests required: yes, add a focused test for `ExternalCallCompleted` token_id presence/optional behavior.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` telemetry correlation workflow
