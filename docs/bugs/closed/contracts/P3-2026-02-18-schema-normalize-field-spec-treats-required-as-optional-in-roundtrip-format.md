## Summary

`_normalize_field_spec()` in `schema.py` treats the `required` key as optional in the round-trip dict format (`{"name": ..., "type": ..., "required": ...}`), silently defaulting to `required=True` when the key is absent. Since `FieldDefinition.to_dict()` always emits `required`, a missing key indicates corruption, not a valid optional field.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/contracts/schema.py`
- Line: 237-243
- Function: `_normalize_field_spec()`

## Evidence

**Write side** (`FieldDefinition.to_dict()`, line 122-128) always includes `required`:
```python
def to_dict(self) -> dict[str, str | bool]:
    return {
        "name": self.name,
        "type": self.field_type,
        "required": self.required,
    }
```

**Read side** (line 237-243) treated it as optional:
```python
if "required" in spec and type(spec["required"]) is not bool:
    raise ValueError(...)
optional = "required" in spec and spec["required"] is False
```

The `"required" in spec` guard makes the field effectively optional, defaulting to required when absent.

## Root Cause

Defensive `in` check on Tier 1 round-trip data. The comment on line 228 explicitly says this handles the `to_dict()` round-trip format.

## Fix Applied

1. Changed to require `"required"` key: `if "required" not in spec: raise ValueError(...)`
2. Unconditional type check: `if type(spec["required"]) is not bool: raise ValueError(...)`
3. Direct access: `optional = spec["required"] is False`

## Impact

Missing `required` key in round-trip dict format now raises `ValueError` with clear message instead of silently assuming `required=True`.
