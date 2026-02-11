# Bug Report: DatabaseSink Fails After `validate_output_target()` Due to Missing Metadata Initialization

**Status: OPEN**

## Status Update (2026-02-11)

- Classification: **Still open**
- Verification summary:
  - Re-verified against current code on 2026-02-11; the behavior described in this ticket is still present.


## Summary

- `validate_output_target()` creates a SQLAlchemy engine but never initializes `self._metadata`, causing `_ensure_table()` to raise `RuntimeError` on the first write after validation (resume path).

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
- Data set or fixture: Any pipeline using `DatabaseSink` in resume/append mode (CLI resume path)

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/plugins/sinks/database_sink.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure a pipeline with `DatabaseSink` and run it once so a table exists.
2. Resume the run via CLI (or any path that calls `sink.validate_output_target()` before execution).
3. During the resumed run, `DatabaseSink.write()` calls `_ensure_table()` and raises `RuntimeError`.

## Expected Behavior

- After `validate_output_target()`, the sink should be able to write without initialization errors.

## Actual Behavior

- `_ensure_table()` raises `RuntimeError("Database sink write() called before initialization")` because `_metadata` is still `None`.

## Evidence

- `src/elspeth/plugins/sinks/database_sink.py:149-152` initializes `self._engine` but not `self._metadata` in `validate_output_target()`.
- `src/elspeth/plugins/sinks/database_sink.py:208-221` assumes `_metadata` is set whenever `_engine` exists and raises `RuntimeError` if it is `None`.
- `src/elspeth/cli.py:2166-2188` shows `validate_output_target()` is called in the resume path before any writes.

## Impact

- User-facing impact: Resume runs with `DatabaseSink` fail immediately on first write.
- Data integrity / security impact: Resume is blocked, preventing completion of pipeline outputs.
- Performance or cost impact: Wasted compute due to failed resume attempts.

## Root Cause Hypothesis

- `validate_output_target()` partially initializes the sink (engine only), while `_ensure_table()` expects metadata to be initialized whenever an engine exists.

## Proposed Fix

- Code changes (modules/files): `src/elspeth/plugins/sinks/database_sink.py` initialize `_metadata = MetaData()` when `_engine` is created in `validate_output_target()`, or defensively initialize `_metadata` inside `_ensure_table()` even if `_engine` already exists.
- Config or schema changes: None.
- Tests to add/update: Add a test that calls `validate_output_target()` then `write()` (SQLite in-memory URL) and asserts no `RuntimeError`.
- Risks or migration steps: Low risk; change only affects initialization consistency.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): Unknown
- Observed divergence: Unknown
- Reason (if known): Unknown
- Alignment plan or decision needed: Unknown

## Acceptance Criteria

- Resume path invoking `validate_output_target()` no longer causes `DatabaseSink.write()` to fail.
- New test passes and prevents regression.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/plugins/ -k database_sink -v`
- New tests required: yes, add a resume/validate-then-write unit test for `DatabaseSink`.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: docs/plans/2026-02-03-pipelinerow-migration.md
