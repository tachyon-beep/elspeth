# Bug Report: CSVSink Silently Writes Blank Values When Required Fields Are Missing

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- CSVSink does not enforce required fields when `validate_input=False` (default), so rows missing required schema fields are written with empty strings instead of crashing, causing silent data corruption and audit-trail mismatch.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b / RC2.3-pipeline-row
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any CSV sink with fixed or flexible schema and a row missing required fields

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/sinks/csv_sink.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a `CSVSink` with a fixed schema (e.g., `{"mode": "fixed", "fields": ["id: int", "name: str"]}`) and leave `validate_input` at its default `False`.
2. Call `write()` with a batch where at least one row is missing the required `name` field.

## Expected Behavior

- The sink should raise an error before writing any rows when required fields are missing, because missing required fields indicate an upstream bug and must not be silently coerced.

## Actual Behavior

- The sink writes the row with a blank value for the missing field and returns success, silently corrupting output while the audit trail records a successful sink write.

## Evidence

- `validate_input` defaults to `False`, meaning missing fields are not validated by default: `src/elspeth/plugins/sinks/csv_sink.py:39-42`.
- Validation only runs when `validate_input=True`, and otherwise rows are written directly with no required-field checks: `src/elspeth/plugins/sinks/csv_sink.py:239-265`.

## Impact

- User-facing impact: Output CSV can contain blank values for required fields without any error, producing incorrect deliverables.
- Data integrity / security impact: Violates audit integrity by recording successful sink writes for rows that are missing required data; this is silent data loss.
- Performance or cost impact: None directly; potential downstream costs due to corrupted outputs and reprocessing.

## Root Cause Hypothesis

- CSVSink relies on optional `validate_input` for required-field checks, but defaults it to `False` and does not perform any required-field validation before writing rows.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/plugins/sinks/csv_sink.py`: Add required-field preflight validation (based on `self._schema_config.fields`) before any writes, even when `validate_input=False`. For explicit schemas, raise a clear error if any required field is missing from any row.
- Config or schema changes: None.
- Tests to add/update:
  - Add a sink test that `CSVSink.write()` raises when a required field is missing even with `validate_input=False`.
  - Add a test asserting no output is written when required-field validation fails mid-batch.
- Risks or migration steps:
  - Pipelines that previously relied on silent blanking will now fail fast; this is intentional and aligns with auditability requirements.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:15-19`, `CLAUDE.md:29-31`
- Observed divergence: Missing required fields are silently converted to blank values instead of crashing on upstream bugs, contradicting “no silent recovery” and the audit-trail-as-source-of-truth principles.
- Reason (if known): Unknown
- Alignment plan or decision needed: Enforce required-field presence in CSVSink prior to writing any rows.

## Acceptance Criteria

- Writing a row missing a required schema field raises an error before any file writes occur.
- Output CSV is unchanged when required-field validation fails.
- New tests covering missing required fields pass.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/sinks/test_csv_sink.py -k missing`
- New tests required: yes, add coverage for missing required fields with `validate_input=False`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
