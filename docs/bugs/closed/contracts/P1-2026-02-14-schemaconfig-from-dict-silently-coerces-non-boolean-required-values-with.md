## Summary

`SchemaConfig.from_dict()` silently coerces non-boolean `required` values in dict-form field specs, causing incorrect required/optional semantics instead of rejecting invalid config.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/schema.py`
- Line(s): 230-234
- Function/Method: `_normalize_field_spec`

## Evidence

`_normalize_field_spec` treats `required` with truthiness instead of strict boolean validation:

```python
if "name" in spec and "type" in spec:
    name = spec["name"]
    type_spec = spec["type"]
    optional = not spec.get("required", True)
    return f"{name}: {type_spec}{'?' if optional else ''}"
```

Because `optional = not spec.get("required", True)`, invalid values are silently accepted and misinterpreted.

Repro (executed in repo with `PYTHONPATH=src`):

- Input: `{"mode":"fixed","fields":[{"name":"score","type":"float","required":"false"}]}`
- Output: `FieldDefinition(name='score', field_type='float', required=True)`

So `"false"` (string) becomes `required=True`, which is the opposite of user intent and no error is raised.

## Root Cause Hypothesis

The round-trip dict-form branch (`name/type/required`) was added for serialization compatibility, but `required` was not type-validated. Using truthiness (`not ...`) introduces coercion and semantic inversion for malformed values.

## Suggested Fix

In `_normalize_field_spec`, validate strict schema for this branch:

- Require `name` and `type` to be `str`
- If `required` is present, require `type(required) is bool`
- Raise `ValueError` on any invalid type instead of coercing

Example fix shape:

```python
if "name" in spec and "type" in spec:
    name = spec["name"]
    type_spec = spec["type"]
    if not isinstance(name, str) or not isinstance(type_spec, str):
        raise ValueError(...)
    if "required" in spec and type(spec["required"]) is not bool:
        raise ValueError(...)
    optional = "required" in spec and spec["required"] is False
    return f"{name}: {type_spec}{'?' if optional else ''}"
```

## Impact

Invalid config can silently change contract semantics (optional fields treated as required, or vice versa), causing:

- Incorrect row validation/quarantine behavior
- Incorrect schema guarantees used downstream
- Audit contract mismatch between configured intent and runtime behavior
