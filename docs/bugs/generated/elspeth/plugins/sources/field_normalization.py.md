# Bug Report: Duplicate Raw Headers Are Not Detected When `normalize_fields=False`, Causing Silent Column Loss

## Summary

- Duplicate CSV headers pass through unchanged when `normalize_fields=False`, and the resulting resolution mapping and row dict silently drop earlier columns, violating auditability and causing data loss.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b (RC2.3-pipeline-row)
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: CSV with duplicate headers (e.g., header row `id,id` and data row `1,2`)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis bug audit of `src/elspeth/plugins/sources/field_normalization.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a CSV with duplicate headers (e.g., `id,id`) and run a pipeline with the default CSV source configuration (`normalize_fields=False`).
2. Observe that only the last `id` column survives in the row dict and audit mapping, with no error raised.

## Expected Behavior

- Duplicate headers should be rejected before processing, with a clear `ValueError` listing the colliding header names and positions.

## Actual Behavior

- Duplicate headers are accepted when `normalize_fields=False`, and the resolution mapping and row dict collapse duplicates, silently dropping data.

## Evidence

- `resolve_field_names` skips collision checks when `normalize_fields=False`, leaving duplicates undetected in the raw-header path. `src/elspeth/plugins/sources/field_normalization.py:215-223`
- `resolution_mapping = dict(zip(original_names, final_headers, strict=True))` collapses duplicate keys, silently discarding earlier headers. `src/elspeth/plugins/sources/field_normalization.py:247`
- CSV rows are built with `dict(zip(headers, values, strict=False))`, which overwrites earlier duplicate keys. `src/elspeth/plugins/sources/csv_source.py:242-243`

## Impact

- User-facing impact: Columns are silently dropped when duplicate headers are present; output rows do not reflect all source data.
- Data integrity / security impact: Audit trail loses traceability for dropped columns, violating auditability guarantees.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `resolve_field_names` only checks collisions after normalization or mapping, but does not validate duplicates when headers pass through unchanged, allowing duplicate raw headers to flow into dict construction and audit mapping.

## Proposed Fix

- Code changes (modules/files): Add duplicate-header detection in `resolve_field_names` for the `normalize_fields=False` path (and optionally columns mode) and raise a `ValueError` before building `resolution_mapping`. `src/elspeth/plugins/sources/field_normalization.py`
- Config or schema changes: None.
- Tests to add/update: Add a unit test in `tests/plugins/sources/test_field_normalization.py` (and/or integration test in `tests/plugins/sources/test_csv_source.py`) that asserts duplicate raw headers raise `ValueError` even when `normalize_fields=False`.
- Risks or migration steps: Existing pipelines with duplicate headers will fail fast instead of silently dropping data; this is intentional and aligns with audit requirements.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:15-19` (auditability and traceability guarantees)
- Observed divergence: Silent column loss means not every source field is traceable or recorded.
- Reason (if known): Missing duplicate-header validation in the no-normalization path.
- Alignment plan or decision needed: Enforce duplicate-header rejection at the source boundary in `resolve_field_names`.

## Acceptance Criteria

- Duplicate raw headers with `normalize_fields=False` raise a clear `ValueError`.
- No silent loss of columns occurs in `resolution_mapping` or row dict construction.
- Tests cover the duplicate-header rejection path.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/sources/test_field_normalization.py`
- New tests required: yes, add a duplicate-header rejection test for `normalize_fields=False`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: Unknown
