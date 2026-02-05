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
---
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
---
# Bug Report: JSON/JSONL accepts NaN/Infinity, violating canonical JSON policy

## Summary

- JSON and JSONL parsing use `json.loads` without `parse_constant`, allowing non-finite values (NaN/Infinity) that violate canonical JSON requirements.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: RC2.3-pipeline-row @ 1c70074ef3b71e4fe85d4f926e52afeca50197ab
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Azure blob JSON/JSONL containing `NaN` or `Infinity`

## Agent Context (if relevant)

- Goal or task prompt: static analysis deep bug audit for `src/elspeth/plugins/azure/blob_source.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Upload a JSON blob containing `{"value": NaN}` or `{"value": Infinity}`.
2. Load via `AzureBlobSource(..., format="json")` or `format="jsonl"`.
3. Observe that parsing succeeds and the row is processed.

## Expected Behavior

- Non-finite JSON constants are rejected at parse time with a recorded validation error and quarantine.

## Actual Behavior

- Non-finite constants are accepted into rows, risking later failures in canonical hashing or audit record integrity.

## Evidence

- `src/elspeth/plugins/azure/blob_source.py:592-595` uses `json.loads` without `parse_constant` in JSON array parsing.
- `src/elspeth/plugins/azure/blob_source.py:645-646` uses `json.loads` without `parse_constant` in JSONL parsing.
- Canonical JSON policy explicitly requires rejecting NaN/Infinity. `CLAUDE.md:642-645`.
- JSONSource already enforces this via `_reject_nonfinite_constant`. `src/elspeth/plugins/sources/json_source.py:9-42`.

## Impact

- User-facing impact: Non-standard JSON values can slip through or cause later crashes during hashing/recording.
- Data integrity / security impact: Violates canonical JSON requirements; may break audit trail determinism.
- Performance or cost impact: Potential downstream failures and reprocessing.

## Root Cause Hypothesis

- Missing `parse_constant` handler in Azure blob JSON parsing paths.

## Proposed Fix

- Code changes (modules/files): Add a non-finite constant rejection handler in `src/elspeth/plugins/azure/blob_source.py` and pass it to `json.loads` for both JSON and JSONL paths (mirroring JSONSource).
- Config or schema changes: None.
- Tests to add/update: Add tests in `tests/plugins/azure/test_blob_source.py` for NaN/Infinity rejection in JSON and JSONL.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:642`
- Observed divergence: Non-finite JSON constants are accepted instead of rejected.
- Reason (if known): JSON parsing does not use `parse_constant`.
- Alignment plan or decision needed: Align Azure blob JSON parsing with canonical JSON policy and JSONSource behavior.

## Acceptance Criteria

- JSON/JSONL blobs containing NaN/Infinity are rejected at parse time.
- Validation errors are recorded and rows quarantined (or discarded per config).

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/azure/test_blob_source.py -k "json"`
- New tests required: yes, NaN/Infinity rejection coverage.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:642`
