# Bug Report: CSV malformed lines are silently dropped due to `on_bad_lines="warn"`

## Summary

- `pd.read_csv` is configured to skip bad CSV lines with only a warning, which drops rows without quarantine or audit records.

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
- Data set or fixture: Azure blob CSV with at least one malformed line (e.g., unbalanced quotes)

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit for `src/elspeth/plugins/azure/blob_source.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a CSV blob containing a malformed row (e.g., `id,name\n1,"alice\n2,bob\n`).
2. Configure `AzureBlobSource` to read that blob with `format="csv"` and `on_validation_failure="quarantine"`.
3. Run `list(source.load(ctx))`.

## Expected Behavior

- The malformed row is quarantined (or file-level parse error is recorded) so every row has a terminal state and an audit record.

## Actual Behavior

- Pandas skips the malformed row with a warning; the row is never yielded nor recorded in the audit trail.

## Evidence

- `src/elspeth/plugins/azure/blob_source.py:499-507` uses `pd.read_csv(..., on_bad_lines="warn")`, which skips bad lines without producing any row or audit entry.
- There is no handling of pandas warnings or bad-line capture before yielding rows, so skipped lines never reach `ctx.record_validation_error` or `SourceRow.quarantined()`. `src/elspeth/plugins/azure/blob_source.py:508-527`.

## Impact

- User-facing impact: Missing rows in output without explanation.
- Data integrity / security impact: Audit trail violation via silent row drops (no terminal state).
- Performance or cost impact: Low, but remediation requires reprocessing.

## Root Cause Hypothesis

- The CSV parser is configured to warn and skip invalid lines, but the code never captures or records those skipped lines.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/plugins/azure/blob_source.py` to avoid silent skips by either using `on_bad_lines="error"` and recording a file-level parse failure, or providing an `on_bad_lines` callable that captures each bad line and emits `ctx.record_validation_error` plus a quarantined `SourceRow`.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/plugins/azure/test_blob_source.py` that includes a malformed CSV line and asserts a quarantined row or file-level parse error is recorded.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:66`, `CLAUDE.md:647`
- Observed divergence: External CSV errors are skipped without quarantine or audit records, violating “quarantine rows that can’t be coerced/validated” and “no silent drops.”
- Reason (if known): `on_bad_lines="warn"` bypasses row-level error handling.
- Alignment plan or decision needed: Decide whether to quarantine each bad line (preferred) or treat any bad line as a file-level parse error.

## Acceptance Criteria

- Malformed CSV lines result in audit-recorded quarantine events or a file-level parse error record.
- No CSV row is skipped without a terminal state.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/azure/test_blob_source.py -k "csv"`
- New tests required: yes, malformed CSV line quarantine coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:66`, `CLAUDE.md:647`
