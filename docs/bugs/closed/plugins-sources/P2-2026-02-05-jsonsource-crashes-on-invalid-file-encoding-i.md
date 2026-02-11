# Bug Report: JSONSource crashes on invalid file encoding instead of quarantining

**Status: CLOSED**

## Status Update (2026-02-12)

- Classification: **Resolved**
- Resolution summary:
  - JSONL loading now reads bytes and decodes per line, so `UnicodeDecodeError` is handled at the source boundary instead of crashing iteration.
  - Decode failures are recorded as `schema_mode="parse"` validation errors and routed to quarantine/discard according to config.
  - Added regression tests for invalid-encoding JSONL lines in both quarantine and discard modes.


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

## Actual Behavior (Before Fix)

- A `UnicodeDecodeError` was raised during file read/iteration, crashing the pipeline without a validation record.

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

- Code changes (modules/files): Handle decoding in `_load_jsonl` at per-line boundary, record parse validation errors for decode failures, and continue processing subsequent lines.
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

---

## Verification (2026-02-12)

- Reproduced prior failure:
  - JSONL file containing invalid UTF-8 bytes (`\xff\xfe`) raised `UnicodeDecodeError` and aborted load.
- Post-fix behavior:
  - Invalid-encoding line is quarantined (or discarded) as a parse error.
  - Valid lines before and after the malformed line continue processing.
- Tests executed:
  - `PYTHONPATH=src .venv/bin/python -m pytest -q tests/unit/plugins/sources/test_json_source.py -k "parse or encoding"`
  - `PYTHONPATH=src .venv/bin/python -m pytest -q tests/unit/plugins/sources/test_json_source.py`
  - `.venv/bin/ruff check src/elspeth/plugins/sources/json_source.py tests/unit/plugins/sources/test_json_source.py`
  - `.venv/bin/mypy src/elspeth/plugins/sources/json_source.py`
