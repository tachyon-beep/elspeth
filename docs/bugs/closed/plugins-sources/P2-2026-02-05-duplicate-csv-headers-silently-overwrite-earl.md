# Bug Report: Duplicate CSV Headers Silently Overwrite Earlier Columns

**Status: CLOSED**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


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

## Resolution (2026-02-12)

- Status: CLOSED
- Fixed by commit: `78eb27d3`
- Fix summary: Reject duplicate raw CSV headers before passthrough mapping
- Ticket moved from `docs/bugs/open/` to `docs/bugs/closed/` on 2026-02-12.
