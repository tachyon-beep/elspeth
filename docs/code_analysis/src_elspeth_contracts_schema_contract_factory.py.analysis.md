# Analysis: src/elspeth/contracts/schema_contract_factory.py

**Lines:** 99
**Role:** Factory for creating SchemaContract from plugin configuration (SchemaConfig). Bridges the gap between user-facing YAML configuration and runtime SchemaContract objects used for validation and dual-name access. Contains `map_schema_mode()` and `create_contract_from_config()`.
**Key dependencies:**
- Imports from: `contracts.schema_contract` (FieldContract, SchemaContract), `contracts.schema` (SchemaConfig -- TYPE_CHECKING only)
- Imported by: `contracts/__init__.py` (re-exported), `plugins/sources/csv_source.py`, `plugins/sources/json_source.py`, `plugins/azure/blob_source.py`. All source plugins use this to create initial contracts.
**Analysis depth:** FULL

## Summary

This is a small, focused factory module with clean separation of concerns. The code is straightforward and correct for its intended use cases. There is one warning: the `field_resolution` reverse mapping at line 70 silently drops entries when multiple original names normalize to the same name. There is one observation about `datetime` not being a declarable type in YAML config despite being supported at the runtime level. Overall the module is sound.

## Warnings

### [69-70] Reverse mapping of field_resolution silently drops entries on collision

**What:** The `field_resolution` parameter is `original->normalized`. The code reverses it at line 70: `normalized_to_original = {v: k for k, v in field_resolution.items()}`. If two different original names normalize to the same normalized name (e.g., `"Amount $"` and `"amount_$"` both becoming `"amount"`), the dict comprehension silently keeps only the last original name, discarding the other.

**Why it matters:** The `original_name` on `FieldContract` is used for audit trail display and error messages. If the wrong original name is associated with a field due to a collision in the reverse mapping, audit messages like "Required field 'Amount $' (amount) is missing" could display the wrong original header. This is a data integrity concern for the audit trail display layer.

In practice, the normalization layer (`resolve_field_names` in `plugins/sources/field_normalization.py`) likely handles collisions before this point -- but `create_contract_from_config` does not validate this invariant. The function assumes the mapping is bijective (1:1) without verifying it.

**Evidence:**
```python
# Line 70: dict comprehension silently drops collisions
normalized_to_original = {v: k for k, v in field_resolution.items()}
# If field_resolution = {"Amount $": "amount", "amount_$": "amount"}
# then normalized_to_original = {"amount": "amount_$"} -- "Amount $" is lost
```

## Observations

### [18-24] _FIELD_TYPE_MAP excludes datetime (intentional asymmetry)

**What:** The `_FIELD_TYPE_MAP` supports `{"int", "str", "float", "bool", "any"}` mapping to Python types. The `datetime` type is supported at the runtime level (`VALID_FIELD_TYPES` in schema_contract.py, `ALLOWED_CONTRACT_TYPES` in type_normalization.py) but is not declarable in YAML config. This means `datetime` fields can only arise through type inference (OBSERVED mode) from actual data values, not through explicit field declarations.

**Why it matters:** This is likely intentional -- datetime parsing varies by format, and source plugins handle datetime coercion at the Tier 3 boundary. However, it means users cannot declare `"timestamp: datetime"` in their schema, which may be surprising. If a user needs a FIXED schema with a datetime field, they must use `"timestamp: any"` and lose type checking, or use FLEXIBLE mode and rely on inference. This is a design limitation worth documenting.

**Evidence:**
```python
# schema_contract_factory.py - no datetime
_FIELD_TYPE_MAP: dict[str, type] = {
    "int": int, "str": str, "float": float, "bool": bool, "any": object,
}

# schema_contract.py - includes datetime and object
VALID_FIELD_TYPES: frozenset[type] = frozenset({
    int, str, float, bool, type(None), datetime, object,
})
```

### [27-42] map_schema_mode relies on str.upper() without validation

**What:** `map_schema_mode` uses `mode.upper()` with a `type: ignore` to convert lowercase YAML modes to uppercase runtime modes. The function trusts that the input is one of the three valid literals (`"fixed"`, `"flexible"`, `"observed"`). It does not validate the input.

**Why it matters:** This is acceptable because the input comes from `SchemaConfig.mode`, which is a `Literal["fixed", "flexible", "observed"]` -- Pydantic or the `SchemaConfig.from_dict()` parser validates the mode before this function is called. The `type: ignore` comment on `mode.upper()` is needed because mypy cannot prove that `.upper()` on a Literal["fixed", ...] produces Literal["FIXED", ...]. The type safety is maintained by the caller contract, not by this function.

### [75-89] config.fields iteration correctly handles None for observed schemas

**What:** For observed schemas, `config.fields` is `None`, so the `if config.fields is not None:` guard correctly produces an empty tuple. This results in a SchemaContract with no declared fields and `locked=False`, ready for first-row inference. This is correct behavior.

### [79] .get() on normalized_to_original is legitimate defensive lookup

**What:** Line 79 uses `normalized_to_original.get(fd.name, fd.name)` -- a `.get()` with a default. Per CLAUDE.md, `.get()` is prohibited when hiding bugs, but here it's legitimate: `field_resolution` is optional (`None` means no name mapping), and when no resolution is provided, the default is identity (`original_name = normalized_name`). This is proper handling of an optional parameter, not bug suppression.

### [91-99] Locking logic is clean and intentional

**What:** `locked = not config.is_observed` correctly locks explicit schemas (FIXED/FLEXIBLE) and leaves observed schemas unlocked. This aligns with the design where explicit schemas have known types upfront and observed schemas infer types from the first row.

## Verdict

**Status:** SOUND
**Recommended action:** The reverse mapping collision (W1) should be addressed with either a validation check (assert bijectivity) or a documented precondition. The datetime gap (O1) should be documented in user-facing schema documentation. Neither issue is urgent -- the collision requires specific conditions to manifest, and the datetime limitation has a workaround (`any` type).
**Confidence:** HIGH -- Complete read of all 99 lines plus all upstream consumers (csv_source, json_source, blob_source) and downstream dependencies (SchemaConfig, FieldContract, SchemaContract). The module is small and self-contained with clear contracts.
