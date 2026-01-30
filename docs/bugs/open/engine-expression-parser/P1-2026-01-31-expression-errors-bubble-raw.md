# Bug Report: Expression evaluation errors bubble as raw exceptions

## Summary

- Expression parser evaluation errors (KeyError, ZeroDivisionError, TypeError) bubble up as raw exceptions instead of a dedicated `ExpressionEvaluationError`, causing gate expressions to crash runs with opaque errors.

## Severity

- Severity: major
- Priority: P1

## Reporter

- Name or handle: Codex (triaged by Claude)
- Date: 2026-01-31
- Related run/issue ID: N/A

## Evidence

- `src/elspeth/engine/expression_parser.py:305-358`:
  - `visit_Subscript()` line 309: `return value[key]` can raise `KeyError`
  - `visit_BinOp()` line 358: `return op_func(left, right)` can raise `ZeroDivisionError`
- `evaluate()` at lines 503-513 does not wrap these in a dedicated exception type
- Design doc `docs/plans/completed/plugin-refactor/2026-01-18-wp09-engine-level-gates.md` specifies `ExpressionEvaluationError` which does not exist

## Impact

- User-facing impact: Gate expressions crash with confusing KeyError/ZeroDivisionError instead of clear message
- Data integrity / security impact: None (fails safe)
- Performance or cost impact: Developer time debugging opaque errors

## Root Cause Hypothesis

- Missing exception wrapping in expression evaluation - errors should be caught and re-raised as `ExpressionEvaluationError` with context.

## Proposed Fix

- Code changes:
  - Create `ExpressionEvaluationError` exception class
  - Wrap evaluation in try/except, catch common errors, re-raise with expression context
- Tests to add/update:
  - Add test with missing field access, assert `ExpressionEvaluationError` raised
  - Add test with division by zero, assert `ExpressionEvaluationError` raised

## Acceptance Criteria

- Expression evaluation errors raise `ExpressionEvaluationError` with expression text and original error
- Error messages are actionable (include field name, expression, row context)
