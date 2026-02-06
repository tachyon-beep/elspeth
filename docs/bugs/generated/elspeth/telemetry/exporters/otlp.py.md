# Bug Report: OTLP exporter accepts invalid config types and raises non-TelemetryExporterError

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
---
# Bug Report: Span ID derivation ignores UTC normalization for naive timestamps

## Summary

- `_derive_span_id()` uses `event.timestamp.timestamp()` directly, which interprets naive datetimes in local time, while `_event_to_span()` normalizes naive timestamps to UTC. This yields inconsistent span IDs vs. span timestamps when a naive `TelemetryEvent.timestamp` is provided.

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

1. Construct a `TelemetryEvent` (e.g., `RunStarted`) with a naive `timestamp=datetime(2026, 1, 1, 0, 0, 0)` (no tzinfo).
2. Call `_event_to_span(event)` and capture the resulting `span.context.span_id`.
3. Run the same on a host with a different local timezone, or compare to an expected UTC-normalized span ID.

## Expected Behavior

- Span ID derivation should be based on the same UTC-normalized timestamp used for span timestamps, or naive timestamps should be rejected.

## Actual Behavior

- `_derive_span_id()` uses local-time interpretation of naive timestamps, while `_event_to_span()` treats them as UTC, producing inconsistent IDs across environments.

## Evidence

- `src/elspeth/telemetry/exporters/otlp.py#L61-L66` uses `event.timestamp.timestamp()` directly in `_derive_span_id()`.
- `src/elspeth/telemetry/exporters/otlp.py#L261-L266` normalizes naive timestamps to UTC before converting to nanoseconds in `_event_to_span()`.
- `src/elspeth/contracts/events.py#L141-L146` documents telemetry timestamps as UTC, but `_derive_span_id()` does not enforce or normalize that.

## Impact

- User-facing impact: Telemetry span IDs can be inconsistent across environments, degrading trace correlation and causing hard-to-debug gaps.
- Data integrity / security impact: Operational telemetry integrity is reduced; audit trail unaffected.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Inconsistent timezone handling: `_derive_span_id()` does not mirror UTC normalization applied in `_event_to_span()`.

## Proposed Fix

- Code changes (modules/files):
  - Normalize timestamp to UTC in `_derive_span_id()` using the same logic as `_event_to_span()`, or explicitly reject naive timestamps with a clear error.
- Config or schema changes: None.
- Tests to add/update:
  - Unit test asserting `_derive_span_id()` uses UTC normalization for naive timestamps.
- Risks or migration steps:
  - Low risk; aligns span IDs with documented UTC expectations.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/contracts/events.py#L141-L146`
- Observed divergence: Span ID derivation does not honor the UTC timestamp expectation for naive datetimes.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Normalize or enforce UTC in `_derive_span_id()`.

## Acceptance Criteria

- For naive timestamps, span IDs are derived from UTC-normalized time (or naive timestamps are rejected).
- Span IDs remain consistent across hosts with different local timezones.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/telemetry/`
- New tests required: yes, span ID normalization for naive timestamps.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/events.py`
