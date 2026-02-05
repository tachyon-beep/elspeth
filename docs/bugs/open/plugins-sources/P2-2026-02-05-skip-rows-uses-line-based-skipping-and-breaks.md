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
