# Analysis: src/elspeth/contracts/transform_contract.py

**Lines:** 141
**Role:** Bridges Pydantic-based PluginSchema with frozen SchemaContract dataclasses. Provides `create_output_contract_from_schema()` to extract field types from transform output schemas, and `validate_output_against_contract()` to validate transform output data.
**Key dependencies:**
- Imports: `PluginSchema` (from `data.py`), `ContractViolation` (from `errors.py`), `FieldContract`/`SchemaContract` (from `schema_contract.py`), `UnionType`/`Union`/`get_args`/`get_origin` (stdlib)
- Imported by: `engine/executors.py` (lazy import at line 441), `contracts/__init__.py`
**Analysis depth:** FULL

## Summary

This file contains a real bug: the `_TYPE_MAP` at line 18 is missing `datetime`, meaning any PluginSchema declaring `datetime` fields will have them silently mapped to `object` type in the output contract. This loses type precision and would cause phantom `TypeMismatchViolation` errors during contract validation when datetime values are checked against an `object`-typed field contract. The `_get_python_type` function also has a subtle issue with `Union[int, str]` types where only the first non-None member is extracted, losing information about the full union. One warning finding, two observations.

## Critical Findings

### [18-24] _TYPE_MAP missing `datetime` -- transform schemas with datetime fields get silently wrong type

**What:** The `_TYPE_MAP` dictionary maps Python types to contract types but only includes `{int, str, float, bool, type(None)}`. The `datetime` type is absent. When `_get_python_type()` encounters a `datetime` annotation, it falls through to the fallback `return object` at line 60. This means the output contract records the field as `object` type instead of `datetime`.

**Why it matters:** This is a silent type precision loss. The consequences cascade:

1. **Contract validation weakening:** A field declared as `datetime` in the schema will have `python_type=object` in the contract. Since `object` is the "any" type that skips validation (see `schema_contract.py` line 237), datetime fields will never be type-checked at runtime. Any value type passes for these fields.

2. **Checkpoint hash divergence:** If a field is recorded as `object` in the contract, but actual data contains `datetime` values, the contract's `version_hash()` will encode `"t": "object"` while the runtime type is `datetime`. This could cause checkpoint integrity failures on resume if the type is ever corrected.

3. **Audit trail inaccuracy:** The contract stored in the audit trail misrepresents the actual type constraint, violating the principle that the audit trail is the source of truth.

**Evidence:**
```python
_TYPE_MAP: dict[type, type] = {
    int: int,
    str: str,
    float: float,
    bool: bool,
    type(None): type(None),
    # datetime is NOT here
}
```

Compare with `VALID_FIELD_TYPES` in `schema_contract.py` which DOES include `datetime`:
```python
VALID_FIELD_TYPES: frozenset[type] = frozenset({
    int, str, float, bool, type(None), datetime, object,
})
```

And `ALLOWED_CONTRACT_TYPES` in `type_normalization.py` which also includes `datetime`:
```python
ALLOWED_CONTRACT_TYPES: frozenset[type] = frozenset({
    int, str, float, bool, type(None), datetime,
})
```

The inconsistency between these three type sets is the root cause. `_TYPE_MAP` is the odd one out. Currently no PluginSchema subclasses declare `datetime` fields (only `NullSourceSchema` exists), so this bug is latent.

## Warnings

### [46-55] Union type extraction takes first non-None member only, losing multi-type information

**What:** For `Union[int, str]` (a non-Optional union), `_get_python_type` returns the first non-None type only (`int`). For `Union[str, int]`, it would return `str`. The order of type arguments in a Union determines the contract type, which is fragile and order-dependent.

**Why it matters:** If a transform declares `Union[int, str]` as an output field type, the contract will record it as `int`. At runtime, if a `str` value appears, it will fail type validation. This is arguably correct (the contract chose one type), but it is surprising behavior that depends on argument order, and it is undocumented. The comment says "taking the first non-None type" but does not explain why this is the right strategy for non-Optional unions.

**Evidence:**
```python
if _is_union_type(annotation):
    args = get_args(annotation)
    for arg in args:
        if arg is not type(None):
            if arg in _TYPE_MAP:
                return _TYPE_MAP[arg]
            return object
    return type(None)
```

For `Union[int, str]`, this returns `int`. For `Union[str, int]`, this returns `str`. The behavior is deterministic but order-dependent.

### [80] Direct access to model_config["extra"] without checking key existence

**What:** Line 80 accesses `schema_class.model_config["extra"]` directly. The comment correctly notes this follows Tier 1 trust model (we control all schemas via PluginSchema base class). However, if someone creates a bare Pydantic BaseModel (not inheriting PluginSchema) and passes it to this function, this would raise `KeyError`.

**Why it matters:** Low severity. The function signature declares `schema_class: type[PluginSchema]`, so type checkers would catch misuse. The function is only called from `executors.py` with validated transform output schemas. This is a correct application of the Tier 1 trust model.

## Observations

### [100-101] Private field skip logic uses startswith("_")

**What:** Fields starting with `_` are skipped. This is a reasonable heuristic for Pydantic models where private fields are prefixed with underscore. However, Pydantic v2's `model_fields` already excludes private attributes (those declared with `PrivateAttr`), so this check is redundant for properly constructed schemas.

**Why it matters:** Very low severity. The check is harmless defense-in-depth and does not affect behavior for correctly constructed PluginSchema subclasses.

### [128-141] validate_output_against_contract is a thin wrapper

**What:** `validate_output_against_contract()` is a one-line delegation to `contract.validate(output)`. While it provides a named entry point, it adds no logic beyond the delegation.

**Why it matters:** Design observation only. The function exists as a convenience import for callers who work with transform contracts specifically, avoiding the need to import SchemaContract directly. It is correctly thin.

### [121-125] Type ignore comment on mode argument

**What:** Line 122 has `# type: ignore[arg-type]` for passing the `mode` string to `SchemaContract`. The `mode` variable is a `str` but `SchemaContract.mode` expects `Literal["FIXED", "FLEXIBLE", "OBSERVED"]`. The actual value is always one of those three literals (from the if/elif/else at lines 82-91), but mypy cannot infer this from the runtime logic.

**Why it matters:** Very low severity. The type ignore is correctly placed and documented. The actual values are always valid.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Add `datetime` to `_TYPE_MAP` (and import it from `datetime`). This is a one-line fix that aligns this file with `VALID_FIELD_TYPES` and `ALLOWED_CONTRACT_TYPES`. Without this fix, any future transform schema declaring datetime fields will have silently wrong type contracts. Also consider documenting the Union extraction strategy or mapping multi-type unions to `object` explicitly.
**Confidence:** HIGH -- the missing `datetime` is clearly a bug when compared against the other two type sets in the codebase. The Union ordering issue is a design concern with clear evidence.
