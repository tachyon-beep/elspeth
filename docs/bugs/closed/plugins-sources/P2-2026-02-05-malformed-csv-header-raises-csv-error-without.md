# Bug Report: Malformed CSV Header Raises csv.Error Without Quarantine or Audit Record

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- A malformed header row can raise `csv.Error` during header parsing and crash the run without any validation error record or quarantine handling.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 0282d1b441fe23c5aaee0de696917187e1ceeb9b
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: CSV with malformed header (e.g., unterminated quote)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/sources/csv_source.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a CSV with a malformed header, e.g. `id,"name\n1,alice\n`.
2. Configure `CSVSource` with `on_validation_failure: quarantine`.
3. Call `list(source.load(ctx))`.

## Expected Behavior

- Header parse errors should be treated as Tier-3 parse failures: record a validation error and, if not discarding, yield a quarantined row or stop gracefully without an unhandled exception.

## Actual Behavior

- `csv.Error` raised by `next(reader)` on the header propagates and crashes the run without a validation error record.

## Evidence

- `src/elspeth/plugins/sources/csv_source.py:145-149` only catches `StopIteration` when reading headers; `csv.Error` is not handled.
- `src/elspeth/plugins/sources/csv_source.py:175-205` shows csv.Error handling exists for data rows, but not for the header.

## Impact

- User-facing impact: Pipeline crashes on malformed headers instead of quarantining/recording the error.
- Data integrity / security impact: Missing audit trail entry for a source-boundary parse failure.
- Performance or cost impact: None.

## Root Cause Hypothesis

- Header parsing lacks the same `csv.Error` handling and validation recording that exists for data rows.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/plugins/sources/csv_source.py` wrap header `next(reader)` in `try/except csv.Error` and record a parse-mode validation error; if not discarding, yield a quarantined row and return.
- Config or schema changes: N/A
- Tests to add/update: Add a test for malformed header (unterminated quotes) asserting quarantine/recorded error rather than crash.
- Risks or migration steps: Decide whether header parse errors should hard-fail or follow the “file-level parse error” pattern (consistent with JSONSource).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:63-67` (Tier 3 boundary validation and quarantine)
- Observed divergence: Malformed external CSV headers are not quarantined/recorded and instead crash the run.
- Reason (if known): Header parsing lacks `csv.Error` handling.
- Alignment plan or decision needed: Standardize file-level parse error handling across sources.

## Acceptance Criteria

- Malformed CSV headers produce a recorded parse validation error and do not crash the run.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/sources/test_csv_source.py -k malformed_header`
- New tests required: yes, malformed-header quarantine/recording test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`

## Closure Update (2026-02-12)

- Status: Closed after implementing header-level parse error handling and regression coverage.
- Fix summary:
  - `CSVSource.load()` now catches `csv.Error` while reading the header row.
  - Header parse errors are recorded via `ctx.record_validation_error(..., schema_mode="parse")`.
  - Non-discard modes yield a quarantined `SourceRow`; discard mode returns without crashing.
- Evidence:
  - `src/elspeth/plugins/sources/csv_source.py`: header read block now handles `csv.Error` and routes through quarantine/discard flow.
  - `tests/unit/plugins/sources/test_csv_source.py`: added deterministic tests using `csv.field_size_limit()` to trigger header parse errors.
- Verification:
  - `.venv/bin/python -m pytest -q tests/unit/plugins/sources/test_csv_source.py -k "malformed_header_csv_error"`
  - `.venv/bin/python -m pytest -q tests/unit/plugins/sources/test_csv_source.py`
  - `.venv/bin/python -m pytest -q tests/unit/plugins/sources/test_csv_source_contract.py`
