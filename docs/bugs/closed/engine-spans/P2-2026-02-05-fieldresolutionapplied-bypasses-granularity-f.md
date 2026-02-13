# Bug Report: FieldResolutionApplied Bypasses Granularity Filtering

**Status: CLOSED**

## Status Update (2026-02-13)

- Classification: **Fixed**
- Verification summary:
  - `FieldResolutionApplied` now has explicit row-level classification in `should_emit()`.
  - Lifecycle granularity filters this event; rows/full granularities include it.
- Current evidence:
  - `src/elspeth/telemetry/filtering.py:64`
  - `src/elspeth/telemetry/filtering.py:65`
  - `tests/unit/telemetry/test_filtering.py:224`

## Summary

- `FieldResolutionApplied` telemetry events are emitted even when granularity is set to `lifecycle`, violating the documented granularity contract and increasing telemetry volume in minimal-overhead mode.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any source that applies field normalization (e.g., CSVSource with header normalization)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `/home/john/elspeth-rapid/src/elspeth/telemetry/filtering.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure telemetry with `granularity: lifecycle` and enable a console exporter.
2. Run a pipeline where the source applies field normalization (emits `FieldResolutionApplied`).

## Expected Behavior

- Only `RunStarted`, `RunFinished`, and `PhaseChanged` are emitted at `lifecycle` granularity.

## Actual Behavior

- `FieldResolutionApplied` is emitted even at `lifecycle` granularity.

## Evidence

- Granularity filter only whitelists lifecycle/row/external-call events and defaults unknown events to `True` (fail-open), so `FieldResolutionApplied` is not filtered. `src/elspeth/telemetry/filtering.py:59` `src/elspeth/telemetry/filtering.py:71`
- `FieldResolutionApplied` is a defined telemetry event but not included in the filter’s lifecycle or row-level cases. `src/elspeth/telemetry/events.py:80`
- Orchestrator emits `FieldResolutionApplied` during source processing. `src/elspeth/engine/orchestrator/core.py:1062`
- Docs state `lifecycle` granularity only emits `RunStarted`, `RunCompleted`, `PhaseChanged`. `docs/guides/telemetry.md:55`

## Impact

- User-facing impact: Operators selecting minimal telemetry still receive extra events, contrary to configuration expectations.
- Data integrity / security impact: Field normalization mappings (original headers) are emitted even in minimal telemetry mode, which may expose sensitive field names.
- Performance or cost impact: Slight extra telemetry volume per run (one event), plus increased exporter overhead in `lifecycle` mode.

## Root Cause Hypothesis

- `should_emit()` lacks an explicit classification for `FieldResolutionApplied`, so it falls through the default “unknown event types” path and is always emitted.

## Proposed Fix

- Code changes (modules/files): Add an explicit case for `FieldResolutionApplied` in `src/elspeth/telemetry/filtering.py`, and emit it only at `rows` (or `full`) granularity to match documented behavior.
- Config or schema changes: None.
- Tests to add/update: Add unit tests for `should_emit()` covering `FieldResolutionApplied` at `lifecycle`, `rows`, and `full`.
- Risks or migration steps: If the intent is to treat `FieldResolutionApplied` as lifecycle, update docs to match and still classify it explicitly to avoid fail-open surprises.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/guides/telemetry.md:55`
- Observed divergence: `FieldResolutionApplied` is emitted at `lifecycle` granularity despite the spec limiting lifecycle to run/phase events.
- Reason (if known): Missing explicit classification in the filter defaults to fail-open.
- Alignment plan or decision needed: Decide the correct granularity for `FieldResolutionApplied` and encode it in `should_emit()`; update docs if lifecycle inclusion is desired.

## Acceptance Criteria

- With `granularity: lifecycle`, `FieldResolutionApplied` is not emitted.
- With `granularity: rows` (or `full`, per decision), `FieldResolutionApplied` is emitted.
- Unit tests cover the classification behavior.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/telemetry/test_filtering.py -v`
- New tests required: yes, add coverage for `FieldResolutionApplied` in granularity filtering.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/guides/telemetry.md`
