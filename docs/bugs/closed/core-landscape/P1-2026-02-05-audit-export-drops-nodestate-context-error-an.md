# Bug Report: Audit Export Drops NodeState Context/Error and Payload References

## Summary

- Landscape export omits critical audit fields (node_state context/error/success_reason, routing_event reason_ref, call request/response refs + error_json, operation input/output refs), producing an incomplete audit export despite the exporter claiming to be “complete.”

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 1c70074ef3b71e4fe85d4f926e52afeca50197ab
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any run that records node_state context/error/success_reason, routing reason payloads, call payload refs, or operation input/output refs

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/landscape/exporter.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a run and record a node_state with `context_before` and `context_after`, and complete it with `error` or `success_reason`.
2. Record a routing event with `reason_ref`, and record a call with `request_ref`, `response_ref`, and `error_json`.
3. Record a source/sink operation with `input_data_ref` and `output_data_ref`.
4. Export the run via `LandscapeExporter.export_run(run_id)` and inspect the emitted records.

## Expected Behavior

- Exported records include all persisted audit fields, including `context_before_json`, `context_after_json`, `error_json`, `success_reason_json`, `reason_ref`, `request_ref`, `response_ref`, and `input_data_ref`/`output_data_ref`.

## Actual Behavior

- Exported `node_state`, `routing_event`, `call`, and `operation` records omit these fields, losing recorded audit context and payload lineage.

## Evidence

- Exporter omits operation payload refs and call error/refs: `src/elspeth/core/landscape/exporter.py:233-262`.
- Exporter omits node_state context/error/success_reason, routing reason_ref, and call error/refs: `src/elspeth/core/landscape/exporter.py:334-430`.
- These fields exist in the schema: `src/elspeth/core/landscape/schema.py:194-237`.
- Call and routing_event refs + error_json are part of the audit contract: `src/elspeth/contracts/audit.py:257-323`.
- Operation input/output refs are part of the audit contract: `src/elspeth/contracts/audit.py:601-651`.
- Exporter claims “complete audit data”: `src/elspeth/core/landscape/exporter.py:1-9`.

## Impact

- User-facing impact: Audit exports are incomplete and cannot answer “why did this fail/route/call?” without the DB, contradicting the self-contained export expectation.
- Data integrity / security impact: Audit trail becomes lossy; key forensic fields are silently dropped, violating auditability guarantees.
- Performance or cost impact: None directly.

## Root Cause Hypothesis

- Export record dictionaries were not updated when context/error/payload reference fields were added to schema/contracts, leaving exporter output incomplete.

## Proposed Fix

- Code changes (modules/files): Add missing fields to exported `operation`, `call`, `node_state`, and `routing_event` records in `src/elspeth/core/landscape/exporter.py` (include `input_data_ref`, `output_data_ref`, `request_ref`, `response_ref`, `error_json`, `context_before_json`, `context_after_json`, `success_reason_json`, `reason_ref`).
- Config or schema changes: None.
- Tests to add/update: Extend `tests/core/landscape/test_exporter.py` with assertions that these fields appear when present in the DB.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:9-19` (Auditability Standard); `src/elspeth/core/landscape/exporter.py:1-9` (claims complete export).
- Observed divergence: Exporter drops persisted audit fields, making the export incomplete.
- Reason (if known): Exporter not updated alongside schema/contract additions.
- Alignment plan or decision needed: Update exporter output fields to match schema/contract and add tests to enforce completeness.

## Acceptance Criteria

- Exported records include all node_state context/error/success_reason fields, routing reason_ref, call refs/error_json, and operation input/output refs when those fields are present in the DB.
- New tests fail on omission and pass with corrected exporter output.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_exporter.py -k "exporter"`
- New tests required: yes, add coverage for the missing fields (context/error/payload refs).

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Auditability Standard)
