# Bug Report: CSV bad lines skipped without quarantine in AzureBlobSource

## Summary

- Malformed CSV lines are silently skipped due to `on_bad_lines="warn"` in pandas parsing, so those rows never reach a terminal state or audit trail.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Azure blob CSV containing at least one malformed row (e.g., extra delimiter/quote)

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure AzureBlobSource with `format: csv` and `on_validation_failure: quarantine`.
2. Upload a CSV blob containing a malformed row (e.g., extra field or broken quotes).
3. Run the pipeline and observe source output/audit trail.

## Expected Behavior

- The malformed row is recorded via `ctx.record_validation_error` and emitted as `SourceRow.quarantined`, ensuring a terminal state and audit visibility.

## Actual Behavior

- Pandas skips the malformed row without raising, and no quarantine/audit entry is created, resulting in silent data loss.

## Evidence

- `src/elspeth/plugins/azure/blob_source.py:391` uses `pd.read_csv(...)` for parsing.
- `src/elspeth/plugins/azure/blob_source.py:398` sets `on_bad_lines="warn"` with an inline comment indicating bad lines are skipped.
- `src/elspeth/plugins/azure/blob_source.py:400` only handles file-level parse exceptions, not per-line failures.

## Impact

- User-facing impact: Rows disappear without explanation; downstream counts won’t match source data.
- Data integrity / security impact: Audit trail violates “no silent drops,” undermining traceability.
- Performance or cost impact: Potentially reduced processing cost but at the expense of correctness/auditability.

## Root Cause Hypothesis

- CSV parsing is delegated to pandas with `on_bad_lines="warn"`, which skips malformed lines and provides no hook to record or quarantine them.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/plugins/azure/blob_source.py` to handle malformed CSV rows explicitly (e.g., switch to `csv.reader` like `CSVSource`, or use pandas with `on_bad_lines` callable to capture and quarantine bad lines).
- Config or schema changes: None.
- Tests to add/update:
  - Add a test in `tests/plugins/azure/test_blob_source.py` asserting malformed CSV rows are quarantined and recorded (not skipped).
- Risks or migration steps:
  - Behavior change: previously skipped rows will surface as quarantined; update expectations and audit metrics accordingly.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:637`, `CLAUDE.md:639`
- Observed divergence: Malformed rows are silently skipped instead of reaching a terminal state.
- Reason (if known): Pandas default behavior with `on_bad_lines="warn"` was accepted without audit integration.
- Alignment plan or decision needed: Ensure every malformed row yields a quarantined SourceRow with validation error recorded.

## Acceptance Criteria

- Malformed CSV rows from Azure blobs are emitted as `SourceRow.quarantined` (or explicitly discarded when configured), and validation errors are recorded in the audit trail.
- No CSV rows are silently skipped.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/azure/test_blob_source.py`
- New tests required: yes, add a malformed-CSV quarantine test for AzureBlobSource.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:637`, `CLAUDE.md:639`
---
# Bug Report: AzureBlobSource JSON array errors crash instead of quarantining external data

## Summary

- JSON array parsing/structure errors raise `ValueError` and crash the run, violating the Tier‑3 external-data rule to quarantine malformed input.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Azure blob JSON with invalid JSON, wrong root type, or missing `data_key`

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure AzureBlobSource with `format: json` and `on_validation_failure: quarantine`.
2. Upload a blob with invalid JSON or with a non-array root (e.g., `{"id": 1}`) or missing `data_key`.
3. Run the pipeline.

## Expected Behavior

- The file/structure error is recorded via `ctx.record_validation_error`, and a quarantined SourceRow is emitted (unless `discard`).

## Actual Behavior

- `ValueError` is raised, terminating the run and recording no quarantine entry for the invalid input.

## Evidence

- `src/elspeth/plugins/azure/blob_source.py:448` decodes and calls `json.loads` inside a try/except.
- `src/elspeth/plugins/azure/blob_source.py:454` raises `ValueError` on JSON decode failure instead of quarantining.
- `src/elspeth/plugins/azure/blob_source.py:458` raises `ValueError` when `data_key` is missing or root is not a dict.
- `src/elspeth/plugins/azure/blob_source.py:462` raises `ValueError` when JSON root is not a list.
- Reference behavior for sources quarantining structural errors exists in `src/elspeth/plugins/sources/json_source.py:175` and `src/elspeth/plugins/sources/json_source.py:247`.

## Impact

- User-facing impact: Entire pipeline run can fail due to a single malformed blob.
- Data integrity / security impact: External-data failures are not recorded in the audit trail, violating traceability.
- Performance or cost impact: None beyond increased retries/failed runs.

## Root Cause Hypothesis

- `_load_json_array` treats external JSON parse and structure errors as hard exceptions rather than Tier‑3 quarantine events.

## Proposed Fix

- Code changes (modules/files):
  - Update `src/elspeth/plugins/azure/blob_source.py` to mirror JSONSource behavior: catch JSON parse/structure errors, call `ctx.record_validation_error`, emit quarantined rows (unless `discard`), and return.
- Config or schema changes: None.
- Tests to add/update:
  - Update tests in `tests/plugins/azure/test_blob_source.py` that currently expect `ValueError` for invalid JSON/root type to instead expect quarantined rows.
- Risks or migration steps:
  - Behavior change affects existing tests and any callers relying on exceptions; update tests and docs accordingly.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:68`, `CLAUDE.md:72`, `CLAUDE.md:75`
- Observed divergence: External JSON structural errors crash the pipeline instead of being quarantined and recorded.
- Reason (if known): Implementation diverged from JSONSource’s Tier‑3 handling and existing tests codified the exception behavior.
- Alignment plan or decision needed: Align AzureBlobSource JSON handling with Tier‑3 quarantine rules and JSONSource behavior.

## Acceptance Criteria

- Invalid JSON blobs and structural mismatches result in recorded validation errors and quarantined SourceRows (unless `discard`), without crashing the run.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/azure/test_blob_source.py`
- New tests required: yes, update existing JSON error tests to assert quarantine behavior.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md:68`, `CLAUDE.md:72`, `CLAUDE.md:75`
---
# Bug Report: AzureBlobSource accepts NaN/Infinity in JSON input (canonical JSON violation)

## Summary

- JSON parsing in AzureBlobSource uses `json.loads` without rejecting `NaN`/`Infinity`, allowing non-canonical values to enter the pipeline and potentially break audit hashing.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Azure blob JSON/JSONL containing `NaN`, `Infinity`, or `-Infinity`

## Agent Context (if relevant)

- Goal or task prompt: You are a static analysis agent doing a deep bug audit. Target file: /home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure AzureBlobSource with `format: json` or `format: jsonl`.
2. Upload a blob containing `{"value": NaN}` or `{"value": Infinity}`.
3. Run the pipeline; downstream hashing/canonicalization will encounter non-finite floats.

## Expected Behavior

- `NaN`/`Infinity` are rejected at the source boundary, recorded as validation errors, and quarantined per canonical JSON policy.

## Actual Behavior

- `json.loads` accepts non-finite values by default; these values flow into validated rows and can later trigger canonical hashing errors or audit policy violations.

## Evidence

- `src/elspeth/plugins/azure/blob_source.py:450` uses `json.loads(text_data)` without `parse_constant`.
- `src/elspeth/plugins/azure/blob_source.py:502` uses `json.loads(line)` without `parse_constant`.
- Canonical JSON rejects non-finite floats in `src/elspeth/core/canonical.py:9` and `src/elspeth/core/canonical.py:60`.
- JSONSource explicitly rejects NaN/Infinity via `parse_constant` at `src/elspeth/plugins/sources/json_source.py:148` and `src/elspeth/plugins/sources/json_source.py:177`.

## Impact

- User-facing impact: Potential pipeline crashes during hashing or nondeterministic audit records.
- Data integrity / security impact: Violates canonical JSON policy; audit trail may contain non-canonical data.
- Performance or cost impact: Possible run failures and retries.

## Root Cause Hypothesis

- AzureBlobSource does not apply the canonical JSON parse guard (`parse_constant`) used elsewhere, so non-finite values are not filtered at the Tier‑3 boundary.

## Proposed Fix

- Code changes (modules/files):
  - Add a `_reject_nonfinite_constant` helper (or reuse the JSONSource utility) and call `json.loads(..., parse_constant=...)` in `src/elspeth/plugins/azure/blob_source.py`.
  - Update exception handling to catch `ValueError` from the non-finite rejection and quarantine accordingly.
- Config or schema changes: None.
- Tests to add/update:
  - Add tests in `tests/plugins/azure/test_blob_source.py` asserting NaN/Infinity inputs are quarantined for both JSON and JSONL formats.
- Risks or migration steps:
  - Behavior change for non-standard JSON; document that NaN/Infinity are rejected per canonical policy.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/core/canonical.py:9`, `src/elspeth/core/canonical.py:60`
- Observed divergence: AzureBlobSource accepts non-finite JSON values that canonical JSON explicitly rejects.
- Reason (if known): Missing `parse_constant` usage in AzureBlobSource JSON parsing.
- Alignment plan or decision needed: Enforce canonical JSON policy in AzureBlobSource by rejecting NaN/Infinity at parse time.

## Acceptance Criteria

- JSON/JSONL blobs containing NaN/Infinity are quarantined with validation errors recorded, and no non-finite values reach canonical hashing.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/azure/test_blob_source.py`
- New tests required: yes, add NaN/Infinity rejection tests for JSON and JSONL in AzureBlobSource.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/core/canonical.py:9`, `src/elspeth/core/canonical.py:60`
