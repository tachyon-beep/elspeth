## Summary

`_validate_field_type()` accepts non-finite floats (`NaN`, `Infinity`) for `number` outputs, allowing Tier-3 external values to pass boundary validation and crash later during canonical hashing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base_multi_query.py`
- Line(s): `521-525`
- Function/Method: `_validate_field_type`

## Evidence

In the target file, `number` validation only checks Python type, not finiteness:

```python
elif expected_type == OutputFieldType.NUMBER:
    if isinstance(value, bool):
        return "expected number, got boolean"
    if not isinstance(value, (int, float)):
        return f"expected number, got {type(value).__name__}"
```

That value is then written to output unchanged by subclasses:
- `src/elspeth/plugins/llm/openrouter_multi_query.py:386-401`

OpenRouter parsing path uses plain `json.loads(...)`:
- `src/elspeth/plugins/llm/openrouter_multi_query.py:349-351`

Python JSON parsing can accept non-standard constants unless rejected, so `NaN`/`Infinity` can become `float('nan')`/`float('inf')`.
Later, executor hashing rejects non-finite floats and converts this into a hard plugin contract failure:
- `src/elspeth/engine/executors/transform.py:291-302`
- `src/elspeth/core/canonical.py:60-63`

So boundary validation currently allows a value that must be rejected at the boundary.

## Root Cause Hypothesis

Numeric boundary validation in `BaseMultiQueryTransform` validates only coarse type shape (`int|float`) and misses canonical-safety constraints (`math.isfinite`), so invalid external numeric values can leak into Tier-2 pipeline data.

## Suggested Fix

In `_validate_field_type()`, reject non-finite floats for both `NUMBER` and `INTEGER` branches before accepting the value.

Example direction:
```python
import math

if isinstance(value, float) and not math.isfinite(value):
    return "expected finite number, got non-finite float"
```

Add unit tests for multi-query paths where LLM returns `{"score": NaN}` / `{"score": Infinity}` and assert `TransformResult.error(...)` instead of pipeline crash.

## Impact

Malformed external LLM data can crash execution instead of producing a structured transform error, violating Tier-3 boundary handling and weakening auditability guarantees (error should be attributed as row/query failure, not plugin contract crash).

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/base_multi_query.py.md`
- Finding index in source report: 1
- Beads: pending
