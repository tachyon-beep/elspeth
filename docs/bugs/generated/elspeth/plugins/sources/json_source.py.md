# Bug Report: JSONSource records validation errors with unsupported `schema_mode="structure"`

## Summary

- JSONSource uses `schema_mode="structure"` for data_key structural errors, but audit contracts/documentation only allow `fixed`, `flexible`, `observed`, or `parse`, creating a schema-mode contract violation.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: JSON file with `data_key` configured but root is a list or missing key

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `src/elspeth/plugins/sources/json_source.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure JSONSource with `format: json`, `data_key: "results"`, and `on_validation_failure: "quarantine"`.
2. Provide a JSON file where the root is a list or where `results` is missing.
3. Run `JSONSource.load(ctx)` with a Landscape-backed context and inspect validation error records.

## Expected Behavior

- Validation errors should be recorded with a `schema_mode` that matches the allowed contract values (`fixed`, `flexible`, `observed`, or `parse`).

## Actual Behavior

- Structural errors are recorded with `schema_mode="structure"`, which is not part of the documented/contracted set.

## Evidence

- `src/elspeth/plugins/sources/json_source.py:224-275` uses `schema_mode="structure"` when recording structural errors.
- `src/elspeth/plugins/context.py:363-381` documents allowed `schema_mode` values as `fixed`, `flexible`, `observed`, or `parse`.
- `src/elspeth/contracts/audit.py:462-476` documents `ValidationErrorRecord.schema_mode` with the same allowed set.

## Impact

- User-facing impact: Validation error analytics or UI filters that assume the documented schema_mode values may ignore or misclassify structural errors.
- Data integrity / security impact: Audit metadata violates the documented contract for validation error records.
- Performance or cost impact: None.

## Root Cause Hypothesis

- JSONSource introduced a custom `schema_mode="structure"` label without updating the contract or downstream expectations.

## Proposed Fix

- Code changes (modules/files): In `src/elspeth/plugins/sources/json_source.py`, replace `schema_mode="structure"` with an allowed value (likely `parse` for structural boundary failures or `self._schema_config.mode` for schema-context errors).
- Config or schema changes: None, unless the team decides to officially extend `schema_mode` to include `structure` across contracts and docs.
- Tests to add/update: Add or update JSONSource tests to assert recorded `schema_mode` is one of the allowed values on data_key structural errors.
- Risks or migration steps: If choosing to add a new schema_mode, update audit contracts, schema docs, and any analytics consumers.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/context.py:363-381`, `src/elspeth/contracts/audit.py:462-476`.
- Observed divergence: JSONSource records `schema_mode="structure"` outside the documented contract.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Decide whether to conform to existing allowed values or formally extend the schema_mode contract.

## Acceptance Criteria

- No validation error record is created with `schema_mode="structure"` from JSONSource structural errors.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/sources/test_json_source.py -k "data_key_structural_error"`
- New tests required: yes, add assertion on schema_mode for structural errors

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/contracts/audit.py`, `src/elspeth/plugins/context.py`
---
# Bug Report: JSONSource crashes on invalid file encoding instead of quarantining

## Summary

- JSONSource does not handle `UnicodeDecodeError` during file reads, causing the pipeline to crash on invalid encoding bytes rather than recording a validation error and quarantining.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 0282d1b441fe23c5aaee0de696917187e1ceeb9b on `RC2.3-pipeline-row`
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: JSON/JSONL file containing invalid UTF-8 byte sequence with `encoding: "utf-8"`

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `src/elspeth/plugins/sources/json_source.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Write a JSONL file with invalid UTF-8 bytes (for example, `Path.write_bytes(b'{"id": 1}\\n\\xff\\xfe')`).
2. Configure JSONSource with `format: jsonl`, `encoding: "utf-8"`, and `on_validation_failure: "quarantine"`.
3. Call `JSONSource.load(ctx)`.

## Expected Behavior

- The source should catch the decode error at the Tier 3 boundary, record a validation error, and yield a quarantined SourceRow (unless `on_validation_failure="discard"`).

## Actual Behavior

- A `UnicodeDecodeError` is raised during file read/iteration, crashing the pipeline without a validation record.

## Evidence

- `src/elspeth/plugins/sources/json_source.py:160-191` and `195-200` show file reads and JSON parsing wrapped only for `json.JSONDecodeError` and `ValueError`, with no handling for `UnicodeDecodeError`.
- `CLAUDE.md:59-69` states external data should be validated/quarantined and should not crash the pipeline.

## Impact

- User-facing impact: Pipeline crashes on a single malformed byte sequence in a source file.
- Data integrity / security impact: No validation error record is created for the bad input, reducing audit completeness.
- Performance or cost impact: Entire run aborts prematurely, wasting compute.

## Root Cause Hypothesis

- File decoding errors happen before JSON parsing and are not included in the current exception handling.

## Proposed Fix

- Code changes (modules/files): Wrap file reads in `_load_jsonl` and `_load_json_array` with `try/except UnicodeDecodeError` to record a `schema_mode="parse"` validation error and yield a quarantined row (unless discard).
- Config or schema changes: None.
- Tests to add/update: Add tests for JSON and JSONL inputs with invalid encoding to ensure quarantine behavior.
- Risks or migration steps: Decide whether to stop processing the file on decode error (likely yes, since the stream is corrupt).

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:59-69` (Tier 3 external data should be quarantined, not crash).
- Observed divergence: Decode errors from external source data crash the pipeline.
- Reason (if known): Missing exception handling around file decoding.
- Alignment plan or decision needed: Implement decode-error quarantine path consistent with other parse errors.

## Acceptance Criteria

- Invalid encoding in JSON/JSONL source produces a validation error record and (when configured) a quarantined SourceRow instead of crashing.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/sources/test_json_source.py -k "encoding"`
- New tests required: yes, add decode-error cases for JSON and JSONL

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md`
