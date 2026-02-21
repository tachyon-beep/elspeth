## Summary

Schema type `any` is mapped to SQL `Text` without serialization, so valid `any` values (e.g., dict/list) crash at insert time.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/sinks/database_sink.py`
- Line(s): `39`, `283`, `352`
- Function/Method: `SCHEMA_TYPE_TO_SQLALCHEMY`, `_create_columns_from_schema_or_row`, `write`

## Evidence

`database_sink.py` maps `any` to `Text`:

```python
SCHEMA_TYPE_TO_SQLALCHEMY = {
    ...
    "any": Text,
}
```

Rows are then inserted directly:

```python
conn.execute(insert(self._table), rows)
```

But `any` in schema contracts explicitly accepts nested values (see `tests/unit/plugins/test_schema_factory.py:210-227`). A row like `{"payload": {"k": 1}}` is valid under schema `payload: any` but fails DB binding against `Text` with driver errors (e.g., sqlite "type 'dict' is not supported").

## Root Cause Hypothesis

The sink treats `any` as a scalar text column type but does not transform complex Python values into a storable representation before insert.

## Suggested Fix

Pick one explicit contract and enforce it in this file:

1. Preferred: serialize non-scalar `any` values deterministically (e.g., canonical JSON string) before insert.
2. Alternative: reject `any` for `DatabaseSinkConfig` with a clear config-time error until JSON-column support is implemented.

Also add unit tests for `any` with dict/list payloads.

## Impact

Pipelines with valid `any`-typed rows can fail in the sink despite passing schema validation, causing avoidable run failures and breaking schema contract expectations.
