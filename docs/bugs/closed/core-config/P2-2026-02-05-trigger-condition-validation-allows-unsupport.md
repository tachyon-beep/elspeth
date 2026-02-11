# Bug Report: Trigger Condition Validation Allows Unsupported Keys

**Status: RESOLVED ✅**

## Status Update (2026-02-11)

- Classification: **Resolved**
- Verification summary:
  - `TriggerConfig(condition="row['type'] == 'flush_signal'")` is now rejected at config time with a clear unsupported-key validation error.
  - Batch-only conditions using `row['batch_count']` and `row['batch_age_seconds']` continue to validate and run.
- Current evidence:
  - `src/elspeth/core/config.py`
  - `tests/unit/core/test_config_aggregation.py`

## Summary

- `TriggerConfig` validation does not enforce the documented batch-only context, allowing conditions that reference non-existent keys and fail at runtime.

## Severity

- Severity: minor
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-02-04
- Related run/issue ID: N/A

## Environment

- Commit/branch: 1c70074e
- OS: Unknown
- Python version: Unknown
- Config profile / env vars: N/A
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: Static analysis deep bug audit of `src/elspeth/core/config.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure an aggregation trigger condition with a row field not present in batch context, e.g., `condition: "row['type'] == 'flush_signal'"`.
2. Load settings; validation succeeds because the expression is syntactically valid and boolean.
3. Run aggregation; `TriggerEvaluator` evaluates against a context containing only `batch_count` and `batch_age_seconds`, raising an evaluation error.

## Expected Behavior

- Trigger condition validation should reject references to keys outside the batch-only context.

## Actual Behavior

- Invalid trigger conditions pass validation and crash later at runtime due to missing keys.

## Evidence

- Trigger conditions are documented as batch-only with `batch_count` and `batch_age_seconds`.
- Validation now enforces a strict row-key whitelist for trigger conditions.
- Runtime evaluation context remains batch-only, and config-time rejection prevents missing-key runtime failures for unsupported trigger keys.

## Impact

- User-facing impact: Configurations that look valid at load time fail during execution with trigger evaluation errors.
- Data integrity / security impact: Aggregation may fail mid-run, interrupting audit trail completion for affected batches.
- Performance or cost impact: Failed runs and retries increase wasted compute.

## Root Cause Hypothesis

- `TriggerConfig` validation lacks a whitelist for allowable row keys in trigger conditions, despite the batch-only contract.

## Proposed Fix

- Code changes (modules/files): Extend `TriggerConfig.validate_condition_expression()` to parse and reject any row key usage outside `batch_count` and `batch_age_seconds`; update the docstring/examples to show `row['batch_count']`/`row['batch_age_seconds']` usage explicitly.
  - Implemented in `src/elspeth/core/config.py`:
    - Trigger condition validator now rejects unsupported keys outside `batch_count`/`batch_age_seconds`.
    - Non-literal row key access in trigger conditions is rejected.
    - Batch-trigger example updated to explicit `row[...]` syntax.
- Config or schema changes: None.
- Tests added/updated:
  - `tests/unit/core/test_config_aggregation.py`:
    - Updated combined-trigger valid example to batch-only keys.
    - Added regression tests rejecting `row['type']` and `row.get('status')`.
    - Added regression test rejecting non-literal row key access.
- Risks or migration steps: None.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `src/elspeth/core/config.py:146`.
- Observed divergence: Validation permits row-key references outside the documented batch-only context.
- Reason (if known): Validation logic checks syntax/boolean but not allowed identifiers.
- Alignment plan or decision needed: Enforce the batch-only key whitelist at config time.

## Acceptance Criteria

- Trigger conditions referencing non-batch keys are rejected at config validation with a clear error, and valid batch-only conditions pass.

## Tests

- Validation run:
  - `uv run pytest -q tests/unit/core/test_config_aggregation.py tests/unit/engine/test_triggers.py`
  - `uv run ruff check src/elspeth/core/config.py tests/unit/core/test_config_aggregation.py`
- New tests required: no (covered by added regression tests).

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `src/elspeth/core/config.py:146`
