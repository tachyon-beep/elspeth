# Bug Report: OTLP exporter accepts invalid config types and raises non-TelemetryExporterError

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - `OTLPExporter.configure()` still assigns `endpoint`, `headers`, and `batch_size` without explicit type validation.
  - Invalid types can still flow into operations like `batch_size < 1` and `headers.items()`, yielding non-contract exceptions.
- Current evidence:
  - `src/elspeth/telemetry/exporters/otlp.py:125`
  - `src/elspeth/telemetry/exporters/otlp.py:126`
  - `src/elspeth/telemetry/exporters/otlp.py:127`
  - `src/elspeth/telemetry/exporters/otlp.py:130`
  - `src/elspeth/telemetry/exporters/otlp.py:142`

## Summary

- `OTLPExporter.configure()` does not validate `endpoint`, `headers`, or `batch_size` types, so invalid config values raise `TypeError`/`AttributeError` instead of the required `TelemetryExporterError`.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/telemetry/exporters/otlp.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Instantiate `OTLPExporter`.
2. Call `configure({"endpoint": "http://localhost:4317", "headers": "Authorization: token"})` or `configure({"endpoint": "http://localhost:4317", "batch_size": "100"})`.
3. Observe `AttributeError`/`TypeError` instead of `TelemetryExporterError`.

## Expected Behavior

- Invalid config types should be rejected with a `TelemetryExporterError` that explains the misconfiguration.

## Actual Behavior

- Invalid types raise non-`TelemetryExporterError` exceptions during configuration.

## Evidence

- `src/elspeth/telemetry/exporters/otlp.py#L133-L158` assigns `endpoint`, `headers`, and `batch_size` without type validation; `headers.items()` is called later and `batch_size < 1` is evaluated without ensuring `batch_size` is an `int`.
- `src/elspeth/telemetry/protocols.py#L28-L30` requires `configure()` to raise `TelemetryExporterError` for invalid config.

## Impact

- User-facing impact: Misconfigurations crash startup with unhelpful exceptions.
- Data integrity / security impact: None directly, but violates telemetry exporter contract.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Missing type validation in `OTLPExporter.configure()` allows non-dict headers and non-int batch sizes to flow into runtime operations that raise built-in exceptions.

## Proposed Fix

- Code changes (modules/files):
  - Add explicit type checks in `src/elspeth/telemetry/exporters/otlp.py` for `endpoint` (str), `headers` (dict[str, str]), `batch_size` (int), and `flush_interval_ms` (int).
  - Raise `TelemetryExporterError` with actionable messages for invalid types.
- Config or schema changes: None.
- Tests to add/update:
  - Unit tests asserting `TelemetryExporterError` is raised for invalid `endpoint`, `headers`, and `batch_size` types.
- Risks or migration steps:
  - Low risk; only improves validation for incorrect configs.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/telemetry/protocols.py#L28-L30`
- Observed divergence: `configure()` can raise non-`TelemetryExporterError` exceptions on invalid config values.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Add type validation and raise `TelemetryExporterError` consistently.

## Acceptance Criteria

- Invalid `endpoint`, `headers`, or `batch_size` types consistently raise `TelemetryExporterError`.
- Valid configs continue to configure and export successfully.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/telemetry/`
- New tests required: yes, OTLP exporter config validation cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/telemetry/protocols.py`
