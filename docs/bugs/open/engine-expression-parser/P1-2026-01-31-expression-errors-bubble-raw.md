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

- `src/elspeth/engine/expression_parser.py:305-309` - `visit_Subscript()` returns `value[key]` directly and can raise `KeyError`.
- `src/elspeth/engine/expression_parser.py:353-358` - `visit_BinOp()` returns `op_func(left, right)` directly and can raise `ZeroDivisionError` / `TypeError`.
- `src/elspeth/engine/expression_parser.py:503-513` - `evaluate()` calls `evaluator.visit()` without wrapping or re-raising as a dedicated evaluation error.
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

## Verification (2026-02-01)

**Status: STILL VALID**

- `evaluate()` still propagates raw exceptions from evaluator methods; no `ExpressionEvaluationError` wrapper exists. (`src/elspeth/engine/expression_parser.py:305-358`, `src/elspeth/engine/expression_parser.py:503-513`)
