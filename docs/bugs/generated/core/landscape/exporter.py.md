# Bug Report: LandscapeExporter omits contract fields and payload references from exported audit records

## Summary

- Exported records drop multiple fields defined in audit contracts (config JSON, timestamps, payload refs, error/context data), making the export incomplete for compliance/forensics.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: de0ca01d55d988eca8b20f7aec17af733f8ad8b5
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any run with nodes, calls, failures, routing, batches, or artifacts

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of exporter.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Run any pipeline that records nodes, rows/tokens, external calls, routing events, batches, or artifacts.
2. Export the run via `LandscapeExporter.export_run(run_id)` (or enable export in config).
3. Inspect exported records for missing contract fields (e.g., config JSON, timestamps, payload refs, error/context).

## Expected Behavior

- Exported records include all fields defined in the audit contracts/schemas so the export is self-contained for compliance review and forensic reconstruction.

## Actual Behavior

- Exported records omit multiple contract fields (settings/config JSON, created_at timestamps, payload refs, error/context fields, batch linkage), making the audit export incomplete.

## Evidence

- Exporter omits contract fields in record construction:
  - Run record omits `settings_json` and export metadata (`export_status`, `export_error`, `exported_at`, `export_format`, `export_sink`) in `src/elspeth/core/landscape/exporter.py:162`.
  - Node record omits `determinism`, `config_json`, `registered_at`, `schema_mode`, `schema_fields` in `src/elspeth/core/landscape/exporter.py:175`.
  - Edge record omits `created_at` in `src/elspeth/core/landscape/exporter.py:188`.
  - Row record omits `created_at`, `source_data_ref` in `src/elspeth/core/landscape/exporter.py:200`.
  - Token record omits `created_at` in `src/elspeth/core/landscape/exporter.py:211`.
  - Node state records omit `context_before_json`, `context_after_json`, and `error_json` for failures in `src/elspeth/core/landscape/exporter.py:235`.
  - Routing events omit `created_at` and `reason_ref` in `src/elspeth/core/landscape/exporter.py:303`.
  - Call records omit `created_at`, `request_ref`, `response_ref`, and `error_json` in `src/elspeth/core/landscape/exporter.py:317`.
  - Batch records omit `aggregation_state_id` and `trigger_type` in `src/elspeth/core/landscape/exporter.py:332`.
  - Artifact records omit `created_at` and `idempotency_key` in `src/elspeth/core/landscape/exporter.py:356`.
- Audit contracts define the missing fields:
  - Run settings/export metadata in `src/elspeth/contracts/audit.py:39`.
  - Node determinism/config/registered_at/schema fields in `src/elspeth/contracts/audit.py:66`.
  - Edge/Row/Token timestamps and refs in `src/elspeth/contracts/audit.py:94`.
  - NodeState error/context, Call payload refs, RoutingEvent reason_ref/created_at, Batch linkage, Artifact idempotency/created_at in `src/elspeth/contracts/audit.py:223`.
- Auditability standard requires full traceability (including configuration and external call payloads) in `CLAUDE.md:15`.

## Impact

- User-facing impact: Exported audit files are not self-contained for compliance review or explainability outside the originating database.
- Data integrity / security impact: Missing payload references and error/context data break traceability of external calls and failures.
- Performance or cost impact: None directly (fields are already stored).

## Root Cause Hypothesis

- Exporter manually assembles a reduced field set and has drifted out of alignment with `contracts/audit.py` and the auditability requirements.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/core/landscape/exporter.py` to include all contract fields for each record type (run/node/edge/row/token/node_state/routing_event/call/batch/artifact).
  - Serialize datetime fields via `.isoformat()` and pass through nullable fields as `None`.
- Config or schema changes: None.
- Tests to add/update:
  - Extend `tests/core/landscape/test_exporter.py` to assert presence of all contract fields per record type.
  - Add coverage for failed node state export (`error_json`, context fields) and call payload refs.
- Risks or migration steps:
  - Export schema expands; downstream consumers must tolerate additional fields (additive change).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:15`
- Observed divergence: Export omits configuration and external call payload references required for auditability.
- Reason (if known): Exporter’s record dicts are manually curated and incomplete.
- Alignment plan or decision needed: Align exporter output with `contracts/audit.py` and add tests to prevent drift.

## Acceptance Criteria

- Exported records include all fields defined in `contracts/audit.py` for each record type.
- Tests fail if any contract field is missing from exported output.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_exporter.py`
- New tests required: yes, field-presence assertions for all record types

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
