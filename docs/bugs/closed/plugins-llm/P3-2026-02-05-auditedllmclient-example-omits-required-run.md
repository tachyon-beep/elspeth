# Bug Report: AuditedLLMClient example omits required `run_id` and `telemetry_emit`

**Status: CLOSED (FIXED)**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- The package-level docstring example in `src/elspeth/plugins/clients/__init__.py` shows instantiating `AuditedLLMClient` without `run_id` and `telemetry_emit`, but those are required parameters. Following the example raises a `TypeError`.

## Severity

- Severity: minor
- Priority: P3

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/plugins/clients/__init__.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Copy the example from `src/elspeth/plugins/clients/__init__.py` and instantiate `AuditedLLMClient` without `run_id` and `telemetry_emit`.
2. Run the code.

## Expected Behavior

- The example should work as written, or include the required arguments so instantiation succeeds.

## Actual Behavior

- Python raises `TypeError: __init__() missing 2 required positional arguments: 'run_id' and 'telemetry_emit'`.

## Evidence

- The example omits `run_id` and `telemetry_emit`: `src/elspeth/plugins/clients/__init__.py:11-17`.
- `AuditedLLMClient.__init__` requires both parameters: `src/elspeth/plugins/clients/llm.py:227-233`.

## Impact

- User-facing impact: Developers following the example hit an immediate `TypeError` and cannot instantiate the client.
- Data integrity / security impact: None.
- Performance or cost impact: None.

## Root Cause Hypothesis

- The docstring example in `src/elspeth/plugins/clients/__init__.py` was not updated after `run_id` and `telemetry_emit` became required parameters.

## Proposed Fix

- Code changes (modules/files):
  - Update the example in `src/elspeth/plugins/clients/__init__.py` to include `run_id` and `telemetry_emit` (and optionally show their source, e.g., from `PluginContext`).
- Config or schema changes: None.
- Tests to add/update:
  - None (doc-only fix).
- Risks or migration steps:
  - None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` (Telemetry section: clients always receive a telemetry callback).
- Observed divergence: The public example omits required telemetry and run identifiers.
- Reason (if known): Likely stale documentation after telemetry wiring changes.
- Alignment plan or decision needed: Update the example to match the required constructor signature.

## Acceptance Criteria

- The example in `src/elspeth/plugins/clients/__init__.py` includes `run_id` and `telemetry_emit` and no longer raises `TypeError` when copied verbatim.

## Tests

- Suggested tests to run: None.
- New tests required: no, doc-only change.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Telemetry section)

---

## Verification (2026-02-12)

**Status: FIXED**

- Updated `src/elspeth/plugins/clients/__init__.py` package example to include required `run_id` and `telemetry_emit` constructor arguments for `AuditedLLMClient`.
- Verified `AuditedLLMClient.__init__` still requires both parameters (`run_id`, `telemetry_emit`) in `src/elspeth/plugins/clients/llm.py`.

## Closure Report (2026-02-12)

**Resolution:** CLOSED (FIXED)

### Quality Gates Run

- `.venv/bin/python -m ruff check src/elspeth/plugins/clients/__init__.py`

### Notes

- Doc/example alignment fix only; no runtime behavior changes.
