# Bug Report: Routing reason payloads are never persisted, leaving `reason_ref` null for routing events

## Summary

- Routing decisions include a structured `RoutingReason`, but `LandscapeRecorder` only stores `reason_hash` and never persists the reason payload to the payload store, leaving `routing_events.reason_ref` null for both single and multi-route cases.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab on `RC2.3-pipeline-row`
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Any run with a gate that produces `RoutingReason` and a configured payload store

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/landscape/recorder.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a payload store and run a pipeline with a gate that routes using a `RoutingReason`.
2. Inspect `routing_events.reason_ref` for the recorded routing events.

## Expected Behavior

- When `reason` is provided and a payload store is configured, the reason payload should be persisted and `routing_events.reason_ref` should point to the stored payload (for single or multi-route recording).

## Actual Behavior

- `routing_events.reason_ref` is always `NULL` because `LandscapeRecorder` never persists `reason` to the payload store and does not write `reason_ref` for multi-route inserts.

## Evidence

- `src/elspeth/core/landscape/recorder.py:1463-1517` records `reason_hash` but never persists `reason` to the payload store or auto-populates `reason_ref`.
- `src/elspeth/core/landscape/recorder.py:1523-1571` hardcodes `reason_ref=None` and omits `reason_ref` from the insert for multi-route events.
- `src/elspeth/core/landscape/schema.py:319-330` defines `routing_events.reason_ref`, indicating the payload reference is part of the schema.
- `src/elspeth/contracts/audit.py:307-323` includes `reason_ref` on the `RoutingEvent` contract.
- `src/elspeth/engine/executors.py:964-1001` passes `reason` into recorder methods but does not provide `reason_ref`, so recorder must handle persistence.

## Impact

- User-facing impact: Routing reasons cannot be reconstructed during audits or explain tooling because only hashes are stored.
- Data integrity / security impact: Audit trail loses decision rationale, violating the auditability standard (“every decision must be traceable”).
- Performance or cost impact: None directly, but missing payloads can force expensive recomputation or manual investigation.

## Root Cause Hypothesis

- `LandscapeRecorder.record_routing_event()` and `.record_routing_events()` do not auto-persist `reason` to the payload store and never set `reason_ref`, even though the schema and contract include it.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/core/landscape/recorder.py` to:
    - If `reason` is provided and `reason_ref` is `None` and `self._payload_store` is configured, store `canonical_json(reason)` and set `reason_ref`.
    - In `record_routing_events`, compute one `reason_ref` and include it in every insert and `RoutingEvent` object.
- Config or schema changes: None.
- Tests to add/update:
  - Extend `tests/core/landscape/test_recorder_routing_events.py` to assert `reason_ref` is set when a payload store is configured.
  - Add a multi-route test to ensure all events share the same non-null `reason_ref`.
- Risks or migration steps:
  - None. This is additive and fills missing data.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/core/landscape/schema.py:319-330`, `src/elspeth/contracts/audit.py:307-323`
- Observed divergence: The contract and schema include `reason_ref`, but recorder never populates it, leaving routing reasons unrecoverable.
- Reason (if known): Missing implementation in `LandscapeRecorder` for reason payload persistence.
- Alignment plan or decision needed: Implement reason payload storage in recorder methods and add tests to enforce it.

## Acceptance Criteria

- `reason_ref` is non-null for routing events when a payload store is configured and `reason` is provided.
- Multi-route events share the same `reason_ref`.
- Existing routing event tests pass, and new tests validate payload persistence.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_recorder_routing_events.py`
- New tests required: yes, add coverage for `reason_ref` persistence in single and multi-route cases.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
