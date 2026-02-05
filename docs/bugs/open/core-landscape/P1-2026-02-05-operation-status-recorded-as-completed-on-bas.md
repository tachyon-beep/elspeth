# Bug Report: Operation status recorded as completed on BaseException (KeyboardInterrupt/SystemExit)

## Summary

- `track_operation` only marks failures for `Exception`, so `BaseException` subclasses (e.g., `KeyboardInterrupt`, `SystemExit`, `GeneratorExit`) leave `status="completed"` and `error_message=None` even though the operation aborted.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074ef3b71e4fe85d4f926e52afeca50197ab / RC2.3-pipeline-row
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline with a source/sink that raises `KeyboardInterrupt` during load/write

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/operations.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Create a source or sink plugin that raises `KeyboardInterrupt` inside `load()` or `write()`.
2. Run a pipeline so the call is wrapped by `track_operation`.
3. Inspect the operation via `recorder.get_operation(operation_id)` (or DB query).

## Expected Behavior

- The operation is recorded with `status="failed"` and an error message reflecting the interruption.

## Actual Behavior

- The operation is recorded as `status="completed"` with no error message despite aborting with a `BaseException`.

## Evidence

- `src/elspeth/core/operations.py:124-141` shows `status` defaulting to `"completed"` and only `Exception` is caught to mark `"failed"`, leaving `BaseException` unhandled and therefore recorded as completed.
- `CLAUDE.md:11-19` requires the audit trail to be the source of truth with no inference; recording “completed” on an interrupted operation violates this.

## Impact

- User-facing impact: Auditors/operators see completed operations for runs that were interrupted.
- Data integrity / security impact: Audit trail becomes inaccurate, violating the “no inference” and “source of truth” principles.
- Performance or cost impact: None.

## Root Cause Hypothesis

- `track_operation` does not handle `BaseException` subclasses, so interruptions bypass the failure-path and leave the default `"completed"` status.

## Proposed Fix

- Code changes (modules/files): Update `src/elspeth/core/operations.py` to add an `except BaseException as e:` block (after the `Exception` block) that sets `status="failed"`, `error_msg=str(e)`, assigns `original_exception`, and re-raises.
- Config or schema changes: None.
- Tests to add/update: Add a test in `tests/core/landscape/test_operations.py` asserting that `KeyboardInterrupt` causes `status="failed"` and `error_message` to be set.
- Risks or migration steps: Low risk; behavior only changes for `BaseException` subclasses.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md:11-19`
- Observed divergence: The audit trail records “completed” for an interrupted operation.
- Reason (if known): Missing `BaseException` handling in `track_operation`.
- Alignment plan or decision needed: Add `BaseException` handling to preserve audit integrity.

## Acceptance Criteria

- A `KeyboardInterrupt` raised inside `track_operation` results in `status="failed"` and a non-null `error_message`.
- Existing `Exception` and `BatchPendingError` behavior remains unchanged.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/core/landscape/test_operations.py -k track_operation`
- New tests required: yes, add a `KeyboardInterrupt` case.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` auditability standard
