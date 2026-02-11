# Bug Report: JSON array mode silently ignores `mode=append` and truncates existing files

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- JSONSink accepts `mode="append"` with `format="json"` but `_write_json_array()` always truncates, so existing JSON array files are silently overwritten.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Existing JSON array file with prior rows

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit for `src/elspeth/plugins/sinks/json_sink.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create `output.json` containing `[{"id": 1}]`.
2. Configure JSONSink with `format: "json"` and `mode: "append"` and a valid schema.
3. Call `sink.write([{"id": 2}], ctx)`.

## Expected Behavior

- Configuration should be rejected (append is unsupported for JSON array), or existing rows should be preserved without truncation.

## Actual Behavior

- The file is opened in write mode, truncated, and rewritten only with the new rows; prior content is lost.

## Evidence

- `src/elspeth/plugins/sinks/json_sink.py:40` defines `mode` including `"append"` without format constraint.
- `src/elspeth/plugins/sinks/json_sink.py:66-70` documents that JSON array cannot append.
- `src/elspeth/plugins/sinks/json_sink.py:296-317` shows `_write_json_array()` always opening with `"w"` and calling `truncate()` regardless of `_mode`.

## Impact

- User-facing impact: Existing JSON output files are silently overwritten when users expect append behavior.
- Data integrity / security impact: Silent data loss in output artifacts.
- Performance or cost impact: N/A

## Root Cause Hypothesis

- Missing validation that disallows `mode="append"` when `format="json"`, combined with `_write_json_array()` ignoring `_mode`.

## Proposed Fix

- Code changes (modules/files): Add validation in `src/elspeth/plugins/sinks/json_sink.py` (or JSONSinkConfig) to raise on `format="json"` with `mode="append"`; add a guard in `_write_json_array()` to refuse append mode explicitly.
- Config or schema changes: None.
- Tests to add/update: Add a unit test in `tests/plugins/sinks/test_json_sink.py` asserting `mode="append"` + `format="json"` raises `PluginConfigError` or `ValueError`.
- Risks or migration steps: Existing configs using `mode="append"` with JSON array will now fail fast; this is intentional to prevent silent data loss.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/plugins/sinks/json_sink.py:66-70`
- Observed divergence: Code accepts append mode for JSON array despite documenting that JSON array cannot append.
- Reason (if known): Missing validation and `_mode` check in JSON array writer.
- Alignment plan or decision needed: Enforce configuration constraint and fail fast.

## Acceptance Criteria

- Configuring JSONSink with `format="json"` and `mode="append"` raises a clear configuration error.
- JSON array writer never truncates an existing file when append mode is requested (because append is rejected).

## Tests

- Suggested tests to run: `pytest tests/plugins/sinks/test_json_sink.py -k append`
- New tests required: yes, add a test for invalid `format=json` + `mode=append` configuration.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/contracts/plugin-protocol.md` (artifact hashing contract)
