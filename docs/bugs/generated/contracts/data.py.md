## Summary

`check_compatibility()` treats constrained `Annotated` types as plain base types, so it can approve a producer `float` field for a consumer `FiniteFloat` field even though the downstream runtime schema will still reject `NaN`/`Infinity`.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [data.py](/home/john/elspeth/src/elspeth/contracts/data.py#L136)
- Line(s): 140-185, 240-310
- Function/Method: `check_compatibility`, `_unwrap_annotated`, `_types_compatible`

## Evidence

[data.py](/home/john/elspeth/src/elspeth/contracts/data.py#L142) claims compatibility checking “handles ... constrained types,” but [_unwrap_annotated()`](/home/john/elspeth/src/elspeth/contracts/data.py#L240) explicitly strips all `Annotated[...]` metadata, and [_types_compatible()`](/home/john/elspeth/src/elspeth/contracts/data.py#L282) compares only the unwrapped base types:

```python
actual = _unwrap_annotated(actual)
expected = _unwrap_annotated(expected)
```

That means a producer schema like:

```python
class Producer(PluginSchema):
    score: float
```

is considered compatible with a consumer schema like:

```python
class Consumer(PluginSchema):
    score: Annotated[float, Field(allow_inf_nan=False)]
```

because both collapse to `float`.

The repo’s config-driven schema factory uses exactly that constraint for every configured `float` field in [schema_factory.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/schema_factory.py#L25):

```python
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
TYPE_MAP = {
    "float": FiniteFloat,
}
```

and `create_schema_from_config(..., allow_coercion=False)` builds downstream transform/sink schemas from it in [schema_factory.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/schema_factory.py#L140).

Graph validation trusts `check_compatibility()` in [graph.py](/home/john/elspeth/src/elspeth/core/dag/graph.py#L1095), so the edge is accepted statically:

```python
result = check_compatibility(producer_schema, consumer_schema)
if not result.compatible:
    raise GraphValidationError(...)
```

But runtime validation still uses Pydantic’s real constrained schema in [transform.py](/home/john/elspeth/src/elspeth/engine/executors/transform.py#L228) and [sink.py](/home/john/elspeth/src/elspeth/engine/executors/sink.py#L207):

```python
transform.input_schema.model_validate(input_dict)
sink.input_schema.model_validate(row)
```

I verified the mismatch locally in this repo environment:

```python
class Producer(PluginSchema):
    score: float

Consumer = create_schema_from_config(
    SchemaConfig(mode="fixed", fields=(FieldDefinition(name="score", field_type="float", required=True),)),
    "Consumer",
    allow_coercion=False,
)

check_compatibility(Producer, Consumer).compatible  # True
Consumer.model_validate({"score": float("nan")})    # ValidationError: finite_number
```

The current tests only cover the positive “unwrap Annotated” path in [test_data.py](/home/john/elspeth/tests/unit/contracts/test_data.py#L99) and do not include a regression asserting that `Field(allow_inf_nan=False)` must remain a compatibility boundary.

## Root Cause Hypothesis

The file was fixed for a previous false-negative bug around `Annotated` wrappers, but the fix overcorrected by treating all `Annotated` metadata as non-semantic. That is safe for cosmetic metadata, but not for Pydantic constraints like `allow_inf_nan=False`, which materially change what rows the consumer accepts.

## Suggested Fix

Preserve compatibility-relevant `Annotated` constraints instead of unconditionally discarding them. A practical fix in this file would be:

```python
# Pseudocode
actual_base, actual_constraints = _split_annotated(actual)
expected_base, expected_constraints = _split_annotated(expected)

# Keep existing base-type logic first.
# Then reject when expected has stricter finite-number requirements
# than actual guarantees.
if expected_requires_finite_float and not actual_requires_finite_float:
    return False
```

At minimum, special-case `Field(allow_inf_nan=False)` so unconstrained `float` is not accepted as compatible with constrained finite `float`.

Add regression tests covering:
- `float` producer -> `Annotated[float, Field(allow_inf_nan=False)]` consumer should be incompatible
- Config-generated `float` consumer from `create_schema_from_config(..., allow_coercion=False)` should reject unconstrained producer `float`
- Existing permissive `Annotated` metadata cases should still pass

## Impact

A pipeline graph can validate successfully even though downstream transform/sink validation will reject real rows at runtime. In practice this means:

- Configured float consumers advertise stronger guarantees than `check_compatibility()` enforces.
- Non-finite numbers can cross the static contract boundary unnoticed until execution time.
- Runs can fail or quarantine rows mid-flight instead of being rejected at graph-construction time.
- This weakens the repository’s explicit non-finite-number policy and undermines schema-contract reliability for audit-sensitive flows.
