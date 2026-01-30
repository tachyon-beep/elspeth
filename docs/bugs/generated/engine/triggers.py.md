# Bug Report: Trigger condition silently coerces non-boolean results

## Summary

- TriggerEvaluator coerces condition expression results with `bool(...)`, so non-boolean expressions (e.g., `"row['batch_count']"` or `"1"`) are accepted and can fire triggers unexpectedly instead of failing fast.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: Codex
- Date: 2026-01-30
- Related run/issue ID: N/A

## Environment

- Commit/branch: Unknown
- OS: unknown
- Python version: unknown
- Config profile / env vars: N/A
- Data set or fixture: Any pipeline with aggregation trigger conditions

## Agent Context (if relevant)

- Goal or task prompt: Static analysis agent doing a deep bug audit of `/home/john/elspeth-rapid/src/elspeth/engine/triggers.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Configure an aggregation trigger condition with a non-boolean expression, e.g. `condition: "row['batch_count']"` or `condition: "1"`.
2. Run a pipeline that buffers rows into that aggregation.

## Expected Behavior

- The condition result must be strictly boolean; non-boolean results should raise a clear error (ideally at config validation, or at least at runtime) rather than being coerced.

## Actual Behavior

- The condition evaluation is coerced with `bool(...)`, so any truthy non-boolean result immediately triggers a flush, causing unintended batch boundaries.

## Evidence

- `src/elspeth/engine/triggers.py:125-135` — `result = self._condition_parser.evaluate(context)` followed by `if bool(result):` coerces non-boolean values instead of rejecting them.

## Impact

- User-facing impact: Aggregations can flush at incorrect times, producing unexpected batch sizes.
- Data integrity / security impact: Audit trail records a condition trigger even when the configured expression did not explicitly evaluate to a boolean.
- Performance or cost impact: Increased flush frequency can increase downstream processing and storage costs.

## Root Cause Hypothesis

- The trigger condition result is coerced with `bool(result)` instead of enforcing a strict boolean contract, masking misconfigured expressions.

## Proposed Fix

- Code changes (modules/files):
  - `src/elspeth/engine/triggers.py`: After evaluation, enforce `isinstance(result, bool)` and raise a clear error if not.
- Config or schema changes: Consider adding boolean-expression validation in `TriggerConfig.validate_condition_expression()` using `ExpressionParser.is_boolean_expression()` to fail early (optional but recommended).
- Tests to add/update:
  - Unit test: trigger condition with non-boolean expression should raise (or fail validation) instead of firing.
  - Unit test: valid boolean condition still fires correctly.
- Risks or migration steps:
  - Existing pipelines relying on truthy non-boolean expressions will now fail fast; document this as a behavioral tightening.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `CLAUDE.md` — Data Manifesto (no coercion for our data) and prohibition on bug-hiding patterns.
- Observed divergence: Condition results are coerced with `bool(...)` instead of enforcing the contract.
- Reason (if known): Likely convenience to accept any truthy value.
- Alignment plan or decision needed: Enforce strict boolean results and validate at config time.

## Acceptance Criteria

- Non-boolean trigger condition results raise a clear error (config-time or runtime).
- Boolean condition expressions behave unchanged.
- New tests cover non-boolean and boolean condition evaluations.

## Tests

- Suggested tests to run: `.venv/bin/python -m pytest tests/unit/test_triggers.py` (or equivalent trigger tests)
- New tests required: yes, for non-boolean condition evaluation rejection

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `CLAUDE.md` (Data Manifesto / No coercion guidance)
