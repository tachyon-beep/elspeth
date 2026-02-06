# Bug Report: JSON array parse/structure errors crash instead of quarantine

## Summary

- `_load_json_array` raises `ValueError` for invalid JSON, missing `data_key`, or non-list roots, which crashes the pipeline instead of quarantining external data.

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
- Data set or fixture: Azure blob JSON array with invalid JSON or wrong root type

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit for `src/elspeth/plugins/azure/blob_source.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Upload an invalid JSON blob (e.g., `b'[{"id":1}'`) or a JSON object root when `format="json"`.
2. Run `AzureBlobSource(..., format="json", on_validation_failure="quarantine")`.
3. Call `list(source.load(ctx))`.

## Expected Behavior

- The source records a parse/structure validation error and yields a quarantined row (or at least records a file-level parse failure) instead of crashing.

## Actual Behavior

- A `ValueError` is raised, aborting the pipeline with no quarantine record for the external-data failure.

## Evidence

- `src/elspeth/plugins/azure/blob_source.py:591-598` raises `ValueError` on JSON decode failure without `ctx.record_validation_error`.
- `src/elspeth/plugins/azure/blob_source.py:601-607` raises `ValueError` for `data_key` mismatches or non-list root, also without quarantine/audit recording.
- Contrasts with JSON file source behavior that quarantines file-level parse and structural errors instead of raising. `src/elspeth/plugins/sources/json_source.py:193-282`.

## Impact

- User-facing impact: Pipeline crashes on malformed external JSON instead of continuing with valid data.
- Data integrity / security impact: Audit trail lacks record of the external-data failure.
- Performance or cost impact: Re-runs required; avoidable downtime.

## Root Cause Hypothesis

- The Azure blob JSON path uses direct `ValueError` raising instead of the quarantine/recording pattern used by other sources.

## Proposed Fix

- Code changes (modules/files): Mirror JSONSource behavior in `src/elspeth/plugins/azure/blob_source.py` by recording parse/structure errors via `ctx.record_validation_error`, yielding quarantined rows when `on_validation_failure != "discard"`, and returning early instead of raising.
- Config or schema changes: None.
- Tests to add/update: Update `tests/plugins/azure/test_blob_source.py` to expect quarantine behavior rather than `ValueError` for invalid JSON and non-array roots.
- Risks or migration steps: Existing tests expecting `ValueError` will need to be updated.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:59`, `CLAUDE.md:66`
- Observed divergence: External JSON errors crash the pipeline instead of being quarantined and recorded.
- Reason (if known): Exception-first implementation path in `_load_json_array`.
- Alignment plan or decision needed: Align Azure blob JSON handling with JSONSource and trust model by quarantining parse/structure failures.

## Acceptance Criteria

- Invalid JSON array files produce recorded validation errors and (if configured) quarantined rows.
- `data_key` mismatches and non-list roots are handled without crashing.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/azure/test_blob_source.py -k "json"`
- New tests required: yes, update existing tests that currently expect `ValueError`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:59`, `CLAUDE.md:66`
