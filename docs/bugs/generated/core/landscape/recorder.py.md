# Bug Report: Routing Reason Payloads Never Persisted (reason_ref Always None)

## Summary

- Routing decisions record only a hash; the actual routing reason payload is never persisted to the payload store, and multi-destination routing hard-codes `reason_ref=None`, so audit/export cannot reconstruct gate reasoning.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any gate routing with a non-empty RoutingReason

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/core/landscape/recorder.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a `LandscapeRecorder` with a payload store and execute a gate that sets a non-empty `RoutingReason`.
2. Trigger routing with multiple destinations (fork) or single routing via `record_routing_events`/`record_routing_event`.
3. Inspect `routing_events.reason_ref` for the recorded events or check the payload store for reason payloads.

## Expected Behavior

- When `reason` is provided, the recorder serializes it via `canonical_json`, stores it in the payload store, and records `reason_ref` for each routing event (shared across a routing group).

## Actual Behavior

- The recorder only stores `reason_hash`; `reason_ref` is never auto-populated, and multi-route recording always sets `reason_ref=None`, so routing reason payloads are lost.

## Evidence

- `src/elspeth/core/landscape/recorder.py:1157` (record_routing_event computes `reason_hash` but never persists payload)
- `src/elspeth/core/landscape/recorder.py:1217` (record_routing_events lacks a `reason_ref` parameter)
- `src/elspeth/core/landscape/recorder.py:1251` (record_routing_events hard-codes `reason_ref=None` in the RoutingEvent)
- `src/elspeth/engine/executors.py:854` (engine passes `reason` but no `reason_ref`)

## Impact

- User-facing impact: Routing explanations and audit exports lack decision reason payloads even when provided.
- Data integrity / security impact: Audit trail violates “no inference” for routing decisions; reason content cannot be reconstructed.
- Performance or cost impact: None directly; may increase audit/debugging time.

## Root Cause Hypothesis

- `LandscapeRecorder.record_routing_event(s)` never persist routing reason payloads to the payload store and do not populate `reason_ref`, despite schema support.

## Proposed Fix

- Code changes (modules/files):
  - Add payload persistence in `record_routing_event` when `reason` is provided and `reason_ref` is not.
  - Add `reason_ref` support to `record_routing_events`, storing once per routing group and inserting `reason_ref` into DB rows.
- Config or schema changes: None (schema already supports `reason_ref`).
- Tests to add/update:
  - Unit test verifying `reason_ref` is set and payload exists for single routing.
  - Unit test verifying `reason_ref` is set for multi-destination routing and is shared across group.
- Risks or migration steps:
  - None; additive behavior only.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/completed/2026-01-15-landscape-export-inline-payloads.md:44`
- Observed divergence: Routing reason payloads are not captured even when provided.
- Reason (if known): Missing payload-store wiring in recorder methods.
- Alignment plan or decision needed: Implement payload storage and `reason_ref` population in recorder.

## Acceptance Criteria

- Routing events with a non-empty `reason` record a non-null `reason_ref`.
- Payload store contains a canonical JSON payload for the routing reason.
- Export can include routing reason payloads.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/`
- New tests required: yes, routing reason payload persistence for single and multi-destination routing.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/2026-01-15-landscape-export-inline-payloads.md`
---
# Bug Report: Token Outcome Context Stored with json.dumps (Non-Canonical JSON)

## Summary

- `record_token_outcome` serializes `context` with `json.dumps`, allowing non-canonical/invalid JSON (e.g., NaN/Infinity) into the audit trail and bypassing canonical JSON enforcement.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any token outcome with `context` containing NaN/Infinity or non-canonical types

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/core/landscape/recorder.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Call `record_token_outcome(..., context={"metric": float("nan")})`.
2. Query `token_outcomes.context_json` for that record.
3. Observe `NaN` emitted in JSON (non-canonical/invalid per RFC 8785).

## Expected Behavior

- Context should be serialized via `canonical_json`, rejecting NaN/Infinity and enforcing canonical JSON.

## Actual Behavior

- `json.dumps` writes non-canonical JSON (`NaN`, `Infinity`) and bypasses canonical JSON constraints.

## Evidence

- `src/elspeth/core/landscape/recorder.py:2134` (uses `json.dumps(context)` instead of `canonical_json`)

## Impact

- User-facing impact: Audit exports may include invalid JSON for token outcomes.
- Data integrity / security impact: Violates canonical JSON policy; risks inconsistent parsing across tools.
- Performance or cost impact: None direct.

## Root Cause Hypothesis

- `record_token_outcome` uses `json.dumps` rather than `canonical_json`, bypassing canonicalization and NaN/Infinity rejection rules.

## Proposed Fix

- Code changes (modules/files):
  - Replace `json.dumps(context)` with `canonical_json(context)` in `record_token_outcome`.
- Config or schema changes: None.
- Tests to add/update:
  - Add test asserting `record_token_outcome` rejects NaN/Infinity in context.
  - Add test for valid context serialization with canonical JSON.
- Risks or migration steps:
  - Existing records with non-canonical JSON remain; no migration required but consider cleanup if needed.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:619`
- Observed divergence: Audit data stored using non-canonical JSON serialization.
- Reason (if known): Legacy `json.dumps` usage in recorder.
- Alignment plan or decision needed: Enforce canonical JSON for all audit payload fields.

## Acceptance Criteria

- `record_token_outcome` uses canonical JSON serialization and rejects NaN/Infinity.
- Stored `context_json` is RFC 8785-compliant.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/`
- New tests required: yes, context serialization/validation coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
