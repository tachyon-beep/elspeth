## Summary

`evaluate_commencement_gates()` silently coerces non-boolean commencement expressions with `bool(...)`, so invalid go/no-go conditions like `1` or `'yes'` pass instead of being rejected as bad config.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/engine/commencement.py`
- Line(s): 66-67, 89-93
- Function/Method: `validate_gate_expressions`, `evaluate_commencement_gates`

## Evidence

`validate_gate_expressions()` only checks syntax/security:

```python
for gate in gates:
    ExpressionParser(gate.condition, allowed_names=_GATE_ALLOWED_NAMES)
```

[`src/elspeth/engine/commencement.py:66`](file:///home/john/elspeth/src/elspeth/engine/commencement.py#L66)

At runtime, `evaluate_commencement_gates()` then coerces whatever the parser returns:

```python
parser = ExpressionParser(
    gate.condition,
    allowed_names=_GATE_ALLOWED_NAMES,
)
passed = bool(parser.evaluate(frozen_context))
```

[`src/elspeth/engine/commencement.py:89`](file:///home/john/elspeth/src/elspeth/engine/commencement.py#L89)

I verified the behavior directly in the repo:

- `condition="1"` passes
- `condition="'yes'"` passes
- `condition="collections['test']['count']"` passes when count is nonzero

This is inconsistent with the project’s existing “our data must not be truthy/falsy-coerced” enforcement for trigger conditions. The trigger config validator explicitly rejects non-boolean expressions:

```python
if not parser.is_boolean_expression():
    raise ValueError(
        f"Trigger condition must be a boolean expression that returns True/False. "
```

[`src/elspeth/core/config.py:347`](file:///home/john/elspeth/src/elspeth/core/config.py#L347)

And the trigger runtime has defense-in-depth:

```python
if not isinstance(result, bool):
    raise TypeError(
        f"Trigger condition must return bool, got {type(result).__name__}: {result!r}. "
```

[`src/elspeth/engine/triggers.py:126`](file:///home/john/elspeth/src/elspeth/engine/triggers.py#L126)

The trigger tests also codify that policy:

```python
Per CLAUDE.md Three-Tier Trust Model: trigger config is "our data" (Tier 1).
Non-boolean results should be rejected, not silently coerced with bool().
```

[`tests/unit/engine/test_triggers.py:489`](file:///home/john/elspeth/tests/unit/engine/test_triggers.py#L489)

By contrast, there is no corresponding commencement-gate validation test, and current commencement tests only cover truthy/falsy behavior, not strict boolean enforcement.

## Root Cause Hypothesis

Commencement gates were implemented with Python truthiness semantics (`bool(...)`) instead of the stricter Tier 1 config contract already used elsewhere in the engine. The module validates expression syntax/security, but never validates expression type, and then normalizes any non-boolean runtime value into `True`/`False`, masking config mistakes.

## Suggested Fix

Make commencement gates follow the same pattern as trigger conditions:

1. In `validate_gate_expressions()`, construct the parser once and reject any expression where `parser.is_boolean_expression()` is false.
2. In `evaluate_commencement_gates()`, remove `bool(...)` coercion and require `isinstance(result, bool)` before using it.

Example shape:

```python
parser = ExpressionParser(gate.condition, allowed_names=_GATE_ALLOWED_NAMES)
if not parser.is_boolean_expression():
    raise ValueError(
        f"Commencement gate must be a boolean expression that returns True/False. "
        f"Got: {gate.condition!r}"
    )
```

And at runtime:

```python
result = parser.evaluate(frozen_context)
if not isinstance(result, bool):
    raise TypeError(
        f"Commencement gate must return bool, got {type(result).__name__}: {result!r}. "
        f"Expression: {gate.condition!r}"
    )
passed = result
```

Also add regression tests mirroring [`tests/unit/engine/test_triggers.py`](file:///home/john/elspeth/tests/unit/engine/test_triggers.py).

## Impact

A misconfigured commencement gate can fail open and let the main pipeline run even though the configured go/no-go predicate is not actually a predicate. Because the audit trail only records `result: true` for passed gates, it hides that the underlying expression returned a non-boolean value, weakening the trustworthiness of the preflight decision record for a high-stakes audit boundary.
