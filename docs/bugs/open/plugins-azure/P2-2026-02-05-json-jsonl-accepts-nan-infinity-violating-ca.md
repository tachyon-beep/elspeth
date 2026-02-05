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
