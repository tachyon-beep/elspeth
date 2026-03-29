## Summary

`get_nested_field()` always interprets `.` as structural nesting, so `FieldMapper` cannot read legitimate pipeline fields whose actual key literally contains a dot (for example JSON input with `"meta.source": "api"`). In non-strict mode the field is silently skipped; in strict mode it is misreported as missing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/utils.py
- Line(s): 44-53
- Function/Method: `get_nested_field`

## Evidence

`get_nested_field()` unconditionally splits the requested key on `.` and traverses nested dicts:

```python
parts = path.split(".")
current: Any = data

for index, part in enumerate(parts):
    if not isinstance(current, dict):
        ...
    if part not in current:
        return default
    current = current[part]
```

Source: `/home/john/elspeth/src/elspeth/plugins/infrastructure/utils.py:44-53`

`FieldMapper` routes every mapping source containing `.` through this helper instead of using contract/name resolution:

```python
for source, target in self._mapping.items():
    if "." in source:
        value = get_nested_field(row_data, source)
    elif source in row:
        value = row[source]
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/field_mapper.py:133-139`

That matters because JSON sources explicitly preserve raw field names rather than normalizing them:

- `/home/john/elspeth/src/elspeth/plugins/sources/json_source.py:145-150` says “JSON sources don't need field normalization”
- `/home/john/elspeth/src/elspeth/plugins/sources/json_source.py:378-382` uses identity field resolution: `field_resolution = {k: k for k in validated_row}`

So a valid row like `{"meta.source": "api"}` remains keyed by the literal string `"meta.source"` in pipeline data. Today:

- `get_nested_field({"meta.source": "api"}, "meta.source")` returns `MISSING`
- `FieldMapper({"mapping": {"meta.source": "origin"}})` silently drops the value in non-strict mode
- The same config returns a misleading `"missing_field"` error in strict mode

There is test coverage for nested dict lookup and for original-name resolution without dots, but no coverage for literal dotted keys:
- `/home/john/elspeth/tests/unit/plugins/test_utils.py`
- `/home/john/elspeth/tests/unit/plugins/transforms/test_field_mapper.py:73-87`
- `/home/john/elspeth/tests/unit/plugins/transforms/test_field_mapper.py:172-204`

## Root Cause Hypothesis

The helper was written assuming “contains a dot” means “nested path”, which is true for normalized schema field definitions but not for observed JSON/object data. Because the target file does not check for an exact key match before path traversal, it collapses two distinct cases:

1. literal field name `"meta.source"`
2. nested structure `{"meta": {"source": ...}}`

That ambiguity leaks into `FieldMapper`, which bypasses `PipelineRow` contract resolution for dotted sources and therefore relies entirely on this helper’s behavior.

## Suggested Fix

Teach `get_nested_field()` to prefer an exact-key hit before treating the string as a dotted path. For example:

```python
def get_nested_field(data: dict[str, Any], path: str, default: Any = MISSING) -> Any:
    if path in data:
        return data[path]

    parts = path.split(".")
    current: Any = data
    ...
```

That preserves current nested lookup behavior while allowing literal dotted keys from JSON/object sources to work. Add tests for:

- `get_nested_field({"meta.source": "api"}, "meta.source") == "api"`
- `FieldMapper` mapping a literal dotted top-level key
- strict mode on a row containing the literal dotted key

## Impact

JSON/object pipelines can lose data without any terminal error when users map a real field whose name contains `.`. In non-strict mode the mapped output is silently incomplete; in strict mode operators get a false “missing field” diagnosis. This is a contract/integration bug in the target file because it makes valid Tier-2 pipeline data inaccessible and causes silent transform omissions.
