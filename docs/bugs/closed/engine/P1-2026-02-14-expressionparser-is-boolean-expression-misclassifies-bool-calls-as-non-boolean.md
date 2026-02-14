## Summary

`ExpressionParser.is_boolean_expression()` misclassifies `bool(...)` calls as non-boolean, causing config validation/runtime routing contract drift.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1 — real gap in static classifier but workarounds exist: users can write `row['x'] != 0` instead of `bool(row['x'])`; not data corruption, just validation inconsistency)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/engine/expression_parser.py`
- Line(s): `608-637` (missing `ast.Call` handling for `bool(...)`)
- Function/Method: `ExpressionParser._is_boolean_node`

## Evidence

`_is_boolean_node()` does not include any branch for call nodes, even though `bool` is an allowed builtin and evaluator executes it:

- `src/elspeth/engine/expression_parser.py:97-105` allows `"bool"` in `_SAFE_BUILTINS`.
- `src/elspeth/engine/expression_parser.py:409-429` evaluates builtin calls, including `bool(...)`.
- `src/elspeth/engine/expression_parser.py:608-637` boolean classifier has no `ast.Call` case, so `bool(row['x'])` is classified non-boolean.

Integration evidence that this causes incorrect behavior:

- `src/elspeth/core/config.py:604-606` uses `parser.is_boolean_expression()` to decide if gate routes must be `{"true","false"}`.
- `src/elspeth/engine/executors/gate.py:265-266` converts actual boolean eval results to `"true"`/`"false"` route labels.
- `src/elspeth/engine/executors/gate.py:274-288` fails if those labels are missing.

So `condition="bool(row['x'])"` can pass as "non-boolean" at config time (allowing custom labels), then fail at runtime when result is mapped to `"true"`/`"false"`.
Also, trigger validation rejects a genuinely boolean condition (`src/elspeth/core/config.py:323-329`) because classification returns false.

## Root Cause Hypothesis

Boolean classification logic was not updated when safe builtin calls were introduced/expanded. The evaluator supports `bool(...)`, but `_is_boolean_node()` still only recognizes comparisons, bool ops, `not`, boolean literals, and boolean ternaries.

## Suggested Fix

Update `_is_boolean_node()` to treat `bool(...)` calls as boolean (with valid arity). Example approach:

- Add `ast.Call` branch:
  - `node.func` is `ast.Name` with `id == "bool"`
  - `len(node.args)` is `0` or `1`
  - return `True`

Then add regression tests:

- `ExpressionParser("bool(row['x'])").is_boolean_expression() is True`
- Gate config with `condition="bool(row['x'])"` must enforce `true/false` route labels
- Trigger config accepts `condition="bool(row['batch_count'])"`

## Impact

- Valid boolean trigger conditions are incorrectly rejected.
- Gate configs can pass validation with wrong labels, then fail per-row at runtime.
- This creates config/runtime contract inconsistency and avoidable `FAILED` node states, reducing reliability and predictability of routing behavior.
