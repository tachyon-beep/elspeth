## Summary

`ExpressionParser` permits `row.get(key, default)` in gate expressions, so missing Tier 2 fields can be silently replaced with synthetic defaults and routed as if the source had provided them.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [/home/john/elspeth/src/elspeth/core/expression_parser.py](/home/john/elspeth/src/elspeth/core/expression_parser.py)
- Line(s): 128-145, 181-202, 460-487, 605-608
- Function/Method: `_ExpressionValidator._is_allowed_derived`, `_ExpressionValidator.visit_Call`, `_ExpressionEvaluator.visit_Attribute`, `_ExpressionEvaluator.visit_Call`, `ExpressionParser`

## Evidence

[`expression_parser.py`](/home/john/elspeth/src/elspeth/core/expression_parser.py#L128) explicitly treats `row.get(...)` as “row-derived data,” and [`visit_Call`](/home/john/elspeth/src/elspeth/core/expression_parser.py#L181) allows one- or two-argument `.get()` calls:

```python
# src/elspeth/core/expression_parser.py
# lines 138-145
return (
    isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and isinstance(node.func.value, ast.Name)
    and node.func.value.id in self._allowed_names
    and node.func.attr == "get"
)
```

```python
# src/elspeth/core/expression_parser.py
# lines 183-202
if (
    isinstance(node.func, ast.Attribute)
    and isinstance(node.func.value, ast.Name)
    and node.func.value.id in self._allowed_names
    and node.func.attr == "get"
):
    ...
    if len(node.args) < 1 or len(node.args) > 2:
        ...
```

At runtime, [`visit_Attribute`](/home/john/elspeth/src/elspeth/core/expression_parser.py#L460) returns the underlying mapping’s `.get`, so the default is actually applied during gate evaluation:

```python
# src/elspeth/core/expression_parser.py
# lines 463-469
if node.attr == "get":
    if self._single_name_mode and value is self._context:
        return value.get
```

That behavior is relied on by tests that intentionally fabricate values for missing fields:

- [`tests/unit/engine/test_expression_parser.py:123-126`](/home/john/elspeth/tests/unit/engine/test_expression_parser.py#L123) accepts `row.get('status', 'unknown') == 'unknown'`.
- [`tests/unit/engine/test_expression_parser.py:1381-1385`](/home/john/elspeth/tests/unit/engine/test_expression_parser.py#L1381) accepts `row.get('missing', {'key': 'default'})['key'] == 'default'`.
- [`tests/unit/engine/test_expression_parser.py:434-440`](/home/john/elspeth/tests/unit/engine/test_expression_parser.py#L434) accepts `len(str(row.get('page_content', ''))) >= 50` and explicitly treats a missing field as empty content.

This conflicts with the repo’s trust model. [`CLAUDE.md:52-56`](/home/john/elspeth/CLAUDE.md#L52) says missing external fields must be recorded as absence, not filled with fabricated defaults, and [`CLAUDE.md:39-44`](/home/john/elspeth/CLAUDE.md#L39) says post-source Tier 2 data must not be coerced or normalized downstream. Config gates are system routing logic, and [`gate.py:257-283`](/home/john/elspeth/src/elspeth/engine/executors/gate.py#L257) feeds parser results directly into route selection and audit context.

What the code does: missing fields can be turned into `"unknown"`, `{ "key": "default" }`, or `""`, and the gate records a normal routing decision.

What it should do: gate expressions should observe the actual row state only. Missing fields may be checked as `row.get("x") is None`, but not replaced with synthetic non-`None` defaults inside the parser.

## Root Cause Hypothesis

The parser was designed around Python mapping convenience and sandbox safety, not ELSPETH’s audit semantics. Treating `.get(key, default)` as harmless because it is side-effect free missed that the default value changes the meaning of the audited routing decision.

## Suggested Fix

Restrict parser support to `name.get(key)` only, or at minimum reject non-`None` defaults.

Possible direction:

```python
# validator
if len(node.args) == 2 and not self._is_none_constant(node.args[1]):
    self.errors.append(f"{caller_name}.get() default must be None")

# evaluator/docs/tests
# keep row.get('field') for explicit absence checks
# reject row.get('field', 'unknown')
# reject row.get('missing', {...})
```

Also remove or rewrite tests that currently lock in fabricated-default behavior.

## Impact

Rows can be routed based on values that never existed in the pipeline data. The audit trail then records a confident gate outcome whose premise was synthetic, which weakens the attributability guarantee for any output produced downstream of that gate.
---
## Summary

`ExpressionParser` allows coercive builtins (`str`, `int`, `float`, `bool`) on pipeline-row values, so gates can silently normalize bad Tier 2 data instead of surfacing an upstream contract bug.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [/home/john/elspeth/src/elspeth/core/expression_parser.py](/home/john/elspeth/src/elspeth/core/expression_parser.py)
- Line(s): 95-107, 204-213, 473-493, 726-728
- Function/Method: `_SAFE_BUILTINS`, `_ExpressionValidator.visit_Call`, `_ExpressionEvaluator.visit_Call`, `ExpressionParser._is_boolean_node`

## Evidence

[`expression_parser.py:98-106`](/home/john/elspeth/src/elspeth/core/expression_parser.py#L98) whitelists coercive constructors as “safe builtins”:

```python
_SAFE_BUILTINS = MappingProxyType(
    {
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "abs": abs,
    }
)
```

[`visit_Call`](/home/john/elspeth/src/elspeth/core/expression_parser.py#L204) accepts all of them, and [`_ExpressionEvaluator.visit_Call`](/home/john/elspeth/src/elspeth/core/expression_parser.py#L473) executes them directly:

```python
if isinstance(node.func, ast.Name) and node.func.id in _SAFE_BUILTINS:
    ...
    return func(*args)
```

The parser’s boolean classifier even treats `bool(...)` as inherently boolean config:

```python
# src/elspeth/core/expression_parser.py lines 726-728
if isinstance(node, ast.Call):
    return isinstance(node.func, ast.Name) and node.func.id == "bool"
```

Dedicated tests confirm this is intentional behavior:

- [`tests/unit/engine/test_expression_parser.py:469-476`](/home/john/elspeth/tests/unit/engine/test_expression_parser.py#L469) accepts `str(row['code'])` and `str(row.get('x')) == 'None'`.
- [`tests/unit/engine/test_expression_parser.py:486-493`](/home/john/elspeth/tests/unit/engine/test_expression_parser.py#L486) accepts `int(row['amount'])` on string input and truncates `float` to `int`.
- [`tests/unit/engine/test_expression_parser.py:502-509`](/home/john/elspeth/tests/unit/engine/test_expression_parser.py#L502) accepts `float(row['score'])` on string input.
- [`tests/unit/engine/test_expression_parser.py:518-527`](/home/john/elspeth/tests/unit/engine/test_expression_parser.py#L518) accepts `bool(row['count'])` and `bool(row.get('text', ''))`.
- [`tests/property/engine/test_expression_safety.py:451-458`](/home/john/elspeth/tests/property/engine/test_expression_safety.py#L451) and [`tests/property/engine/test_expression_safety.py:495-504`](/home/john/elspeth/tests/property/engine/test_expression_safety.py#L495) fuzz-assert that these coercive builtins are always accepted.

This is at odds with the project contract. [`CLAUDE.md:39-44`](/home/john/elspeth/CLAUDE.md#L39) says Tier 2 pipeline data must not be coerced downstream, and [`CLAUDE.md:104-127`](/home/john/elspeth/CLAUDE.md#L104) says wrong plugin output types are bugs to crash/fix, not values to normalize. Yet [`gate.py:257-279`](/home/john/elspeth/src/elspeth/engine/executors/gate.py#L257) routes directly from parser output.

What the code does: `int("200")`, `float("0.75")`, `bool("false")`, and `str(None)` are treated as valid gate inputs.

What it should do: gates should inspect already-validated row values, not repair or reinterpret them.

## Root Cause Hypothesis

The allowlist optimizes for sandbox safety and Python convenience, but it conflates “side-effect free” with “semantically safe.” In ELSPETH, downstream coercion is not safe because it hides contract violations and changes the evidence used for routing.

## Suggested Fix

Narrow `_SAFE_BUILTINS` to non-coercive operations only, likely `len` and `abs`.

Possible direction:

```python
_SAFE_BUILTINS = MappingProxyType({
    "len": len,
    "abs": abs,
})
```

Then update `_is_boolean_node()` to stop treating `bool(...)` as a valid boolean-expression form, and remove the tests that assert coercive constructor support.

## Impact

A gate can silently turn malformed upstream data into routable values, so the pipeline keeps moving and records a plausible explanation even though an upstream plugin violated its schema contract. That weakens audit integrity and makes data-contract bugs harder to detect.
