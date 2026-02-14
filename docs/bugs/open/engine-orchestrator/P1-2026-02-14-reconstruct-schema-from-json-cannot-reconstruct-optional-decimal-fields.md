## Summary

`reconstruct_schema_from_json()` cannot reconstruct `Optional[Decimal]` fields (`Decimal | None`), causing resume to fail with a `ValueError` on valid Pydantic JSON Schema.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/export.py`
- Line(s): 317-347 (especially 319-320, 325-339, 342-347)
- Function/Method: `_json_schema_to_python_type`

## Evidence

In `_json_schema_to_python_type`, `anyOf` handling supports:
- Decimal only when `{"number","string"}` are present **and null is absent** (`export.py:319-320`)
- Nullable only when there is exactly one non-null branch (`export.py:325-339`)

So this valid Pydantic schema shape for `Decimal | None` is rejected:

```json
{"anyOf": [{"type":"number"}, {"type":"string"}, {"type":"null"}]}
```

The code falls through to the unsupported branch and raises (`export.py:342-347`).

This is a real runtime path for resume:
- Resume loads source schema JSON and reconstructs it (`/home/john/elspeth-rapid/src/elspeth/engine/orchestrator/core.py:1882-1887`).

Reproduction (executed in repo venv):
- Build `BaseModel` with `amount: Decimal | None`
- Call `reconstruct_schema_from_json(model_json_schema())`
- Actual result: `ValueError: Resume failed: Field 'amount' has unsupported anyOf pattern...`

Existing tests cover Decimal and nullable separately, but not nullable Decimal:
- Decimal pattern test (`/home/john/elspeth-rapid/tests/unit/engine/orchestrator/test_export.py:598-608`)
- Nullable non-Decimal tests (`/home/john/elspeth-rapid/tests/unit/engine/orchestrator/test_export.py:610-644`)

## Root Cause Hypothesis

The `anyOf` matcher treats "Decimal" and "nullable" as disjoint patterns. `Optional[Decimal]` is a combined 3-branch `anyOf` (`number|string|null`), but the implementation only accepts:
- Decimal with no null, or
- Nullable with exactly one non-null branch.

That leaves a valid Pydantic output shape unsupported.

## Suggested Fix

Update `_json_schema_to_python_type` to recognize combined nullable-Decimal patterns by:
1. Detecting null presence.
2. Resolving non-null branches first.
3. If non-null branches are Decimal pattern (`number|string`), return `Decimal | None` when null is present, else `Decimal`.

Example fix shape:

```python
if "anyOf" in field_info:
    any_of_items = cast(list[Mapping[str, object]], field_info["anyOf"])
    has_null = any(item.get("type") == "null" for item in any_of_items)
    non_null_items = [item for item in any_of_items if item.get("type") != "null"]
    non_null_types = {cast(str, item["type"]) for item in non_null_items if "type" in item}

    if {"number", "string"}.issubset(non_null_types) and len(non_null_items) == 2:
        return (Decimal | None) if has_null else Decimal

    if has_null and len(non_null_items) == 1:
        inner = _json_schema_to_python_type(...)
        return inner | None
```

Also add a unit test for `Optional[Decimal]` in `tests/unit/engine/orchestrator/test_export.py`.

## Impact

Resume can fail for otherwise valid runs whose source schema includes nullable Decimal fields, blocking recovery of unprocessed rows after interruption/failure. This breaks resume reliability and type-fidelity restoration guarantees for that schema shape.
