# Bug Report: Span ID derivation ignores UTC normalization for naive timestamps

**Status: OVERTAKEN BY EVENTS**

## Status Update (2026-02-11)

- Classification: **Overtaken by events (refactor)**
- Verification summary:
  - The prior `_derive_span_id()` path no longer exists; span IDs are now generated randomly.
  - Since span ID generation no longer derives from timestamps, the original naive-timestamp normalization mismatch no longer applies in current code.
- Current evidence:
  - `src/elspeth/telemetry/exporters/otlp.py:48`
  - `src/elspeth/telemetry/exporters/otlp.py:59`
  - `src/elspeth/telemetry/exporters/otlp.py:242`

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
