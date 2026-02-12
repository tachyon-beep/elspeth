# Bug Report: Telemetry Payloads Are Mutable References (Can Drift From Audit Hashes)

**Status: CLOSED (FIXED)**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- `PluginContext.record_call()` passes mutable `request_data`/`response_data` dicts directly into telemetry events, so later mutations can change telemetry payloads after hashes are computed, causing telemetry/audit correlation drift.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/plugins/context.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a `PluginContext` with a telemetry callback that stores emitted events in a list and a mocked `landscape`.
2. Call `ctx.record_call(...)` with `request_data={"a": 1}` and `response_data={"b": 2}`.
3. Mutate the original `request_data["a"] = 999` after `record_call()` returns.
4. Observe the stored telemetry event payload now reflects `{"a": 999}` while `request_hash` was computed from the original payload.

## Expected Behavior

- Telemetry payloads are immutable snapshots of the request/response at call time, consistent with the hashes recorded in the audit trail.

## Actual Behavior

- Telemetry payloads reference the original mutable dicts; later mutations change the payload contents while the hashes remain from the original data, breaking telemetry/audit correlation.

## Evidence

- `src/elspeth/plugins/context.py:331` shows `ExternalCallCompleted` constructed with `request_payload=request_data` and `response_payload=response_data` without copying.
- `src/elspeth/telemetry/manager.py:223` shows events are queued for async export, so payloads can be mutated before export.

## Impact

- User-facing impact: Operational dashboards and alerts can show incorrect request/response payloads, confusing incident triage.
- Data integrity / security impact: Telemetry payloads can diverge from recorded hashes, undermining audit/telemetry correlation.
- Performance or cost impact: None directly, but repeated investigations due to misleading telemetry.

## Root Cause Hypothesis

- `record_call()` passes mutable dict references into telemetry events without taking a snapshot; asynchronous telemetry export allows subsequent mutations to alter emitted payloads.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/plugins/context.py`, deep-copy or serialize `request_data`/`response_data` before building `ExternalCallCompleted`, and compute hashes from the copied snapshot.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/plugins/test_context.py` that mutates `request_data` after `record_call()` and asserts emitted payload remains unchanged.
- Risks or migration steps: Minor CPU/memory overhead for deep copies on large payloads.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:573-623`
- Observed divergence: Telemetry payloads can drift from call-time state, weakening operational visibility and correlation with audit hashes.
- Reason (if known): Payloads are passed by reference without snapshotting.
- Alignment plan or decision needed: Snapshot payloads at emission to keep telemetry consistent with audit hashes.

## Acceptance Criteria

- Mutating `request_data` or `response_data` after `record_call()` does not change telemetry payloads.
- Telemetry payloads remain consistent with `request_hash`/`response_hash` from the time of recording.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/test_context.py -k telemetry_payload_snapshot`
- New tests required: yes, add a regression test for telemetry payload immutability.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:573-623`, `docs/guides/telemetry.md`


## Resolution (2026-02-12)

- Status: CLOSED (FIXED)
- Fix summary: `PluginContext.record_call()` now deep-copies request/response payloads before emitting telemetry and hashes those snapshots, preventing post-call mutation drift.
- Code updated:
  - `src/elspeth/contracts/plugin_context.py`
- Tests added/updated:
  - `tests/unit/plugins/test_context.py`
- Verification:
  - `ruff check src/elspeth/contracts/plugin_context.py tests/unit/plugins/test_context.py`
  - `pytest tests/unit/plugins/test_context.py` (`37 passed`)
  - Manual repro check confirms emitted payloads remain unchanged after caller mutation.
- Ticket moved from `docs/bugs/open/plugins-transforms/` to `docs/bugs/closed/plugins-transforms/`.
