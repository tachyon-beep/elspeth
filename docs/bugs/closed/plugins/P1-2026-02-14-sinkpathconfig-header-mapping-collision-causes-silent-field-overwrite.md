## Summary

`SinkPathConfig` accepts custom `headers` mappings that can map multiple input fields to the same output key, which causes silent field overwrite (data loss) in JSON sinks.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/config_base.py
- Line(s): 226-245
- Function/Method: `SinkPathConfig._validate_headers`

## Evidence

`SinkPathConfig._validate_headers` only checks top-level type and allowed string modes; it returns mapping dicts without semantic validation:

```python
# src/elspeth/plugins/config_base.py:236-244
if isinstance(v, dict):
    return v
```

Downstream, JSON sink rewrites row keys using a dict comprehension:

```python
# src/elspeth/plugins/sinks/json_sink.py:543-549
return [{display_map.get(k, k): v for k, v in row.items()} for row in rows]
```

If two source keys map to the same display name, later keys overwrite earlier keys with no error. Reproduced with current code:

- Config: `headers={"a": "COLLIDED", "b": "COLLIDED"}`
- Input row: `{"a": 1, "b": 2}`
- Output row becomes: `{"COLLIDED": 2}` (field `a` is silently lost)

This is a validation gap in the target file: invalid config is accepted, then causes silent data loss at sink write time.

## Root Cause Hypothesis

`SinkPathConfig` validates `headers` structurally (`str | dict`) but not contract semantics (uniqueness/collision safety). Because invalid mappings are allowed through config parsing, JSON sink key remapping can collapse multiple fields into one key.

## Suggested Fix

In `SinkPathConfig` (target file), add semantic validation for custom header mappings:

1. Reject duplicate mapping values (e.g., two fields -> same output name).
2. For explicit schemas (`fixed`/`flexible`), reject mappings whose output names collide with unmapped declared field names (e.g., `{"a": "b"}` while `b` is also a declared field not remapped).
3. Keep raising `ValueError` so `from_dict()` wraps it as `PluginConfigError`.

Example direction:

- Keep `_validate_headers` for type/mode checks.
- Add `@model_validator(mode="after")` on `SinkPathConfig` to inspect `self.headers` and `self.schema_config`.

## Impact

Silent output corruption in JSON sinks: fields can disappear without error or quarantine. This violates auditability expectations ("no silent data loss") because persisted sink artifacts can omit data while the pipeline reports success.
