# Bug Report: Duplicate CSV Headers Silently Overwrite Earlier Columns

## Summary

- CSV files with duplicate header names (when `normalize_fields` is false) silently overwrite earlier column values during row dict construction, causing undetected data loss.

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
- Data set or fixture: CSV with duplicate headers (e.g., `id,id`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/sources/csv_source.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a CSV file: `id,id\n1,2\n`.
2. Instantiate `CSVSource` with `schema: {mode: observed}` and `on_validation_failure: quarantine` (default `normalize_fields` = false).
3. Iterate `list(source.load(ctx))` and inspect the row dict.

## Expected Behavior

- Duplicate headers should be detected at the boundary and treated as a parse/validation error (e.g., quarantine with a recorded error or a raised ValueError), preventing silent data loss.

## Actual Behavior

- The produced row dict contains only the last duplicate header value (`{"id": "2"}`), and the earlier column value is silently dropped.

## Evidence

- `src/elspeth/plugins/sources/csv_source.py:151-160` resolves headers without any duplicate check when `normalize_fields` is false.
- `src/elspeth/plugins/sources/csv_source.py:242-243` builds the row via `dict(zip(headers, values, strict=False))`, which overwrites earlier duplicates.
- `src/elspeth/plugins/config_base.py:110-167` validates duplicates for `columns` config, but raw CSV headers have no equivalent validation path.

## Impact

- User-facing impact: Incorrect row values in downstream transforms/sinks without any indication of error.
- Data integrity / security impact: Silent field loss violates auditability guarantees; earlier column data is unrecoverable.
- Performance or cost impact: None.

## Root Cause Hypothesis

- CSVSource does not validate for duplicate raw headers when normalization is disabled, so dict construction overwrites earlier fields without error.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/plugins/sources/csv_source.py` add a duplicate-header check on `headers` after resolution (even when `normalize_fields` is false) and treat duplicates as a parse error (record validation error + quarantine/return, or raise).
- Config or schema changes: N/A
- Tests to add/update: Add a test in `tests/plugins/sources/test_csv_source.py` asserting duplicate headers are rejected/quarantined when `normalize_fields` is false.
- Risks or migration steps: Decide whether to hard-fail (ValueError) or quarantine a single “file-level parse error” row; ensure behavior is consistent with JSONSource parse handling.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:63-67` (Tier 3 boundary validation and quarantine), `CLAUDE.md:15-19` (auditability standard)
- Observed divergence: Duplicate headers allow silent field loss instead of being validated/quarantined at the source boundary.
- Reason (if known): No duplicate check before dict construction when normalization is disabled.
- Alignment plan or decision needed: Decide on consistent “file-level parse error” handling for unrecoverable header ambiguity.

## Acceptance Criteria

- CSV files with duplicate headers reliably trigger a parse/validation error and do not silently overwrite columns.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/sources/test_csv_source.py -k duplicate_header`
- New tests required: yes, duplicate-header rejection/quarantine test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
---
# Bug Report: skip_rows Uses Line-Based Skipping and Breaks Multiline CSV Records

## Summary

- `skip_rows` advances the file by raw lines before creating `csv.reader`, which desynchronizes parsing when skipped rows contain quoted newlines and can corrupt downstream parsing.

## Severity

- Severity: minor
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
- Data set or fixture: CSV where a skipped row contains a quoted newline

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/sources/csv_source.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a CSV where the first record contains a quoted newline, e.g. `comment,"line1\nline2"\nheader1,header2\n1,2\n`.
2. Set `skip_rows: 1` so the first record should be skipped.
3. Load via `CSVSource.load()`.

## Expected Behavior

- Skipping should operate on CSV records (not raw lines) so multiline quoted records are skipped atomically and parsing remains aligned.

## Actual Behavior

- The raw `next(f)` line skip leaves the file pointer mid-record; `csv.reader` starts parsing from the middle of a quoted field, producing parse errors or corrupted header/data alignment.

## Evidence

- `src/elspeth/plugins/sources/csv_source.py:133-138` skips rows via `next(f, None)` before `csv.reader` is created.
- `src/elspeth/plugins/sources/csv_source.py:107-108` claims multiline quoted field support, but line-based skipping breaks that guarantee when `skip_rows > 0`.

## Impact

- User-facing impact: Incorrect parsing or crashes for CSVs with multiline quoted records in skipped rows.
- Data integrity / security impact: Potential row/field misalignment and silent corruption.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `skip_rows` is implemented as raw line skipping instead of CSV-record skipping, which is incompatible with multiline quoted fields.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/plugins/sources/csv_source.py` create `csv.reader` before skipping and skip via `next(reader, None)` in a loop (or `itertools.islice`) so skipping respects CSV record boundaries.
- Config or schema changes: N/A
- Tests to add/update: Add a regression test with `skip_rows` and a multiline quoted skipped record to ensure parsing remains correct.
- Risks or migration steps: Ensure `reader.line_num` accounting remains accurate after switching to reader-based skipping.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/sources/csv_source.py:107-108` (explicit multiline support claim)
- Observed divergence: Line-based skipping undermines multiline CSV support.
- Reason (if known): skip_rows implemented before `csv.reader` creation.
- Alignment plan or decision needed: Align skipping behavior with CSV parsing guarantees.

## Acceptance Criteria

- `skip_rows` skips full CSV records and does not corrupt parsing when skipped rows contain quoted newlines.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/sources/test_csv_source.py -k skip_rows_multiline`
- New tests required: yes, multiline skip_rows regression test.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: N/A
---
# Bug Report: Malformed CSV Header Raises csv.Error Without Quarantine or Audit Record

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
