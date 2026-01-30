# Bug Report: Expression evaluation errors bubble as raw exceptions (missing ExpressionEvaluationError/context)

## Summary

- Expression evaluation failures (missing fields, bad operations) raise raw runtime exceptions (e.g., KeyError/ZeroDivisionError) instead of a dedicated, contextual ExpressionEvaluationError, contrary to the planned contract for engine-level gates.

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
- Data set or fixture: Unknown

## Agent Context (if relevant)

- Goal or task prompt: static analysis agent doing a deep bug audit of `src/elspeth/engine/expression_parser.py`
- Model/version: Codex (GPT-5)
- Tooling and permissions (sandbox/approvals): read-only sandbox
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: code review only

## Steps To Reproduce

1. Construct an expression that accesses a missing field: `ExpressionParser("row['missing'] == 1").evaluate({})`.
2. Observe the raised exception.

## Expected Behavior

- Evaluation failures should raise a dedicated `ExpressionEvaluationError` with actionable context (expression, offending field, available fields), as specified in the engine-level gate plan.

## Actual Behavior

- Raw exceptions bubble out of evaluation (e.g., `KeyError: 'missing'`), with no structured error type or context about the expression.

## Evidence

- No evaluation error type exists in the implementation: `src/elspeth/engine/expression_parser.py:24-30`.
- Evaluation uses unchecked subscripting and arithmetic without wrapping: `src/elspeth/engine/expression_parser.py:305-358`.
- `evaluate()` returns evaluator result directly without error translation: `src/elspeth/engine/expression_parser.py:503-513`.
- Planned contract explicitly defines `ExpressionEvaluationError` and expects evaluation to raise it on missing fields: `docs/plans/completed/plugin-refactor/2026-01-18-wp09-engine-level-gates.md:763-1044`.

## Impact

- User-facing impact: Gate expressions can crash runs with opaque errors when row data is missing or operations fail.
- Data integrity / security impact: Failures lack actionable context in the audit trail; difficult to attribute and remediate.
- Performance or cost impact: Pipeline runs can abort early, increasing retries/re-runs and operational overhead.

## Root Cause Hypothesis

- The implementation omitted the planned `ExpressionEvaluationError` and did not wrap evaluation-time failures, so low-level exceptions propagate directly.

## Proposed Fix

- Code changes (modules/files):
  - Add `ExpressionEvaluationError` to `src/elspeth/engine/expression_parser.py` and use it for evaluation-time failures.
  - Wrap evaluation operations (subscript, call, binop, compare) to raise `ExpressionEvaluationError` with context (expression, field name, available keys).
  - Update `ExpressionParser.evaluate()` to translate unexpected exceptions into `ExpressionEvaluationError`.
- Config or schema changes: None.
- Tests to add/update:
  - Add tests asserting missing fields, division by zero, and invalid subscripts raise `ExpressionEvaluationError` with clear context.
- Risks or migration steps:
  - Behavior change: callers currently seeing raw exceptions will now see a custom error type; update any exception handling if present.

## Architectural Deviations

- Spec or doc reference (e.g., docs/design/architecture.md#L...): `docs/plans/completed/plugin-refactor/2026-01-18-wp09-engine-level-gates.md:763-1044`
- Observed divergence: Implementation lacks `ExpressionEvaluationError` and does not translate evaluation failures into a structured error.
- Reason (if known): Unknown.
- Alignment plan or decision needed: Implement `ExpressionEvaluationError` and wrap evaluation failures as specified.

## Acceptance Criteria

- Evaluation-time failures (missing keys, invalid operations) raise `ExpressionEvaluationError` with actionable context.
- No raw `KeyError`/`TypeError`/`ZeroDivisionError` escapes from `ExpressionParser.evaluate()`.

## Tests

- Suggested tests to run: `./.venv/bin/python -m pytest tests/engine/test_expression_parser.py`
- New tests required: yes, add cases for evaluation-time failures and error context.

## Notes / Links

- Related issues/PRs: N/A
- Related design docs: `docs/plans/completed/plugin-refactor/2026-01-18-wp09-engine-level-gates.md`
