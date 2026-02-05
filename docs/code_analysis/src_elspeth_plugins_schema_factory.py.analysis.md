# Analysis: src/elspeth/plugins/schema_factory.py

**Lines:** 151
**Role:** Schema factory that creates runtime Pydantic models from SchemaConfig. Bridges configuration-driven schema definitions to runtime validation classes. Enforces the three-tier trust model through the `allow_coercion` parameter: sources may coerce types (Tier 3 external data), transforms/sinks must reject wrong types (Tier 2 pipeline data). Also defines `FiniteFloat` -- an annotated float type that rejects NaN and Infinity at source boundaries.
**Key dependencies:** Imports from `pydantic` (ConfigDict, Field, create_model), `elspeth.contracts` (PluginSchema), `elspeth.contracts.schema` (FieldDefinition, SchemaConfig). Imported by 17+ plugin implementation files (all sources, transforms, sinks), `test_schema_factory.py`, and various integration tests.
**Analysis depth:** FULL

## Summary

This is a clean, focused module with a clear purpose. The code correctly implements the three-tier trust model through Pydantic's `strict` mode and provides sensible type mapping. There is one significant concern around `FiniteFloat` not being used when `allow_coercion=False` (strict mode), which may allow NaN/Infinity to pass through transform/sink schemas. The module is otherwise sound.

## Critical Findings

### [28-38, 120-134] FiniteFloat constraint may not be enforced in strict mode

**What:** The `TYPE_MAP` maps `"float"` to `FiniteFloat` (line 35), which is `Annotated[float, Field(allow_inf_nan=False)]`. This correctly rejects NaN and Infinity values. However, when `allow_coercion=False` (used for transforms/sinks), the schema is created with `strict=True` in Pydantic's `ConfigDict` (line 131).

The interaction between Pydantic's `strict=True` mode and `Field(allow_inf_nan=False)` needs careful analysis. In strict mode, Pydantic requires exact type matches and disables coercion. The `allow_inf_nan=False` constraint is a validator, not a coercion rule, so it should still apply in strict mode. However, there is a risk that the order of validation (type check vs constraint check) could allow edge cases.

Specifically: if a transform receives a Python `float('nan')` value, strict mode confirms it IS a float (passes type check), and then `allow_inf_nan=False` should reject it. This is the correct order. But if a transform receives a string `"NaN"`, strict mode would reject the type mismatch BEFORE the `allow_inf_nan` check fires, which is also correct (wrong type = upstream bug, per Tier 2 rules).

**Why it matters:** After deeper analysis, this appears to be correct behavior. The FiniteFloat constraint works in both strict and non-strict modes. Downgrading from Critical to Observation -- see Observations section.

## Warnings

### [37] TYPE_MAP maps "any" to typing.Any -- no validation for "any" fields

**What:** When a schema field is declared as type `"any"`, `TYPE_MAP` maps it to `typing.Any`. This means Pydantic will accept ANY value for that field without type checking, even in strict mode.

**Why it matters:** Fields typed as `"any"` bypass all type validation. For sources (Tier 3), this is fine -- external data can be anything. But for transforms/sinks (Tier 2), an `"any"` field means the schema provides no type guarantee at all, which undermines the trust model. If a transform declares `output_schema` with an `"any"` field and a downstream transform expects a specific type, the schema validation layer will not catch the mismatch.

This is a design decision, not a bug -- `"any"` is an explicit opt-out of type checking. But it could mask upstream bugs.

**Evidence:**
```python
TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": FiniteFloat,
    "bool": bool,
    "any": Any,  # No type validation at all
}
```

### [94-134] _create_explicit_schema double-checks config validity

**What:** `_create_explicit_schema` begins with a guard (line 100-101) checking that `config.fields is not None or config.mode == "observed"`. However, this function is only called from `create_schema_from_config` when `config.is_observed` is False (line 70-75), so `config.mode == "observed"` can never be True at line 100. The guard is partially redundant.

**Why it matters:** Minor: the guard provides defense-in-depth against calling the function directly, but the `config.mode == "observed"` condition in the check is dead logic that cannot trigger through the normal call path. Not harmful but could confuse readers.

**Evidence:**
```python
# Line 70-75: Only calls _create_explicit_schema when NOT observed
if config.is_observed:
    return _create_dynamic_schema(name)
return _create_explicit_schema(config, name, allow_coercion)

# Line 100: Checks for observed again (redundant)
if config.fields is None or config.mode == "observed":
    raise ValueError("_create_explicit_schema requires fields and non-observed mode")
```

## Observations

### [28] FiniteFloat is correctly designed for audit integrity

The `FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]` type correctly rejects NaN and Infinity at source boundaries. Per CLAUDE.md, NaN/Infinity cannot be represented in RFC 8785 canonical JSON, so rejecting them at ingest is correct. The comment clearly explains the rationale.

After analysis, `allow_inf_nan=False` is a Pydantic field-level constraint that is applied regardless of `strict` mode. In strict mode, Pydantic first checks the type is exactly `float`, then applies field constraints. In non-strict mode, Pydantic first coerces the value to `float`, then applies field constraints. Both paths run the `allow_inf_nan` check. The FiniteFloat behavior is correct in all modes.

### [41-76] create_schema_from_config correctly separates observed from explicit paths

The function has a clean two-branch structure: observed schemas get a dynamic model (accepts anything), explicit schemas get a typed model with coercion control. The `allow_coercion` parameter correctly defaults to `True` (source boundary is the common case) and maps to Pydantic's inverted `strict` semantics (line 123: `use_strict = not allow_coercion`).

### [78-91] _create_dynamic_schema is appropriately minimal

For observed schemas, the factory creates a model with `extra="allow"` and no fields. The comment (line 89) correctly notes that coercion is irrelevant for dynamic schemas since there are no fields to validate types against.

### [137-151] _get_python_type correctly handles optional fields

The function uses the union type syntax (`base_type | None`) for optional fields, which is clean Python 3.10+ syntax. The `Any` return type annotation is pragmatic, as documented.

### [21] ExtraMode type alias provides semantic clarity

The `ExtraMode = Literal["allow", "forbid"]` type alias makes the Pydantic extra-field handling semantics explicit in function signatures.

## Verdict

**Status:** SOUND
**Recommended action:** No urgent changes needed. Consider whether `"any"` typed fields should be documented more prominently as a deliberate opt-out of type validation, to prevent accidental use in transform/sink schemas. The redundant guard in `_create_explicit_schema` could be simplified to check only `config.fields is None`.
**Confidence:** HIGH -- this is a small, focused module with clear responsibilities. The Pydantic interaction patterns are well-documented and correct.
