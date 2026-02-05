# Bug Report: Datadog exporter ignores `api_key`, so agentless Datadog telemetry never works

## Summary

- The Datadog exporter documents and accepts an `api_key` option but never reads or applies it, so “agentless” Datadog export (direct API) is non-functional and silently falls back to agent host/port.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row / 0282d1b441fe23c5aaee0de696917187e1ceeb9b
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/telemetry/exporters/datadog.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure telemetry with exporter `datadog` and set `options.api_key` (no local Datadog agent running).
2. Run any pipeline with telemetry enabled.
3. Observe that no telemetry arrives in Datadog (agentless flow never activates).

## Expected Behavior

- When `api_key` is provided, the exporter should configure ddtrace for direct API export (agentless), or explicitly fail fast with a clear error if agentless is not supported.

## Actual Behavior

- `api_key` is ignored; the exporter only sets agent host/port and uses the local agent path, leading to silent telemetry loss when no agent is running.

## Evidence

- `src/elspeth/telemetry/exporters/datadog.py:36-85, 90-150` documents `api_key` but never reads or applies it; configuration only sets `DD_AGENT_HOST` and `DD_TRACE_AGENT_PORT`.
- `docs/guides/telemetry.md:179-217` explicitly states `api_key` enables direct API use (“Using without Agent”).

## Impact

- User-facing impact: Telemetry does not reach Datadog when users follow the documented agentless configuration.
- Data integrity / security impact: None for Landscape; operational telemetry is missing, which can hide failures.
- Performance or cost impact: Potentially wasted time diagnosing missing telemetry; no direct runtime cost.

## Root Cause Hypothesis

- `api_key` support was documented but never wired into `DatadogExporter.configure()`, leaving an incomplete implementation.

## Proposed Fix

- Code changes (modules/files):
  - Implement agentless configuration in `src/elspeth/telemetry/exporters/datadog.py` when `api_key` is present (set the appropriate ddtrace env vars or tracer configuration per ddtrace agentless mode).
  - If agentless mode is not supported in current ddtrace usage, explicitly raise `TelemetryExporterError` when `api_key` is provided to avoid silent misconfiguration.
- Config or schema changes: None required unless adding optional fields like `site` for Datadog API domain.
- Tests to add/update:
  - Add a test in `tests/telemetry/exporters/test_datadog.py` verifying that providing `api_key` results in agentless configuration (or a clear error if unsupported).
- Risks or migration steps:
  - Ensure any new environment variables are set before tracer initialization; document any new required options (e.g., Datadog site).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/guides/telemetry.md:179-217`
- Observed divergence: Docs say `api_key` enables direct API export, but exporter ignores `api_key` and only configures agent host/port.
- Reason (if known): Likely incomplete implementation.
- Alignment plan or decision needed: Implement agentless mode or explicitly disallow it with a validation error.

## Acceptance Criteria

- Providing `api_key` in Datadog exporter options results in successful agentless telemetry export or a clear, immediate configuration error.
- Tests cover the `api_key` path to prevent regression.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/telemetry/exporters/test_datadog.py`
- New tests required: yes, add coverage for `api_key` configuration behavior.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/guides/telemetry.md`
