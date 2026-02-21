## Summary

`KeywordFilterConfig` accepts empty/blank `fields`, which turns `KeywordFilter` into a silent no-op and lets blocked content pass.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/keyword_filter.py`
- Line(s): 65-68, 150-152, 180-194
- Function/Method: `KeywordFilterConfig` (missing validator), `KeywordFilter.process()`, `KeywordFilter._get_fields_to_scan()`

## Evidence

`fields` is declared as required but has no content validator:

```python
fields: str | list[str] = Field(...)
```

Only `blocked_patterns` has a validator (lines 74-80), so `fields=[]`, `fields=""`, and `fields=[""]` are accepted.

`_get_fields_to_scan()` returns the list/string as-is (lines 186-194), and `process()` loops over it (lines 152-179). If empty, loop body never runs and code always returns success (lines 180-184).

I verified behavior at runtime:

- `KeywordFilterConfig.from_dict({"fields": [], ...})` succeeds.
- `KeywordFilter(...fields=[])` processing `{"content": "has secret"}` returns `status == "success"`.

## Root Cause Hypothesis

The config model enforces presence of `fields` but not semantic validity. Missing validator logic allows structurally present yet operationally empty/blank field selectors.

## Suggested Fix

Add a `@field_validator("fields")` in `KeywordFilterConfig` to enforce:

- string case: allow `"all"` or non-empty trimmed field name
- list case: non-empty list, each item non-empty trimmed string

Example shape:

```python
@field_validator("fields")
@classmethod
def validate_fields(cls, v: str | list[str]) -> str | list[str]:
    if type(v) is str:
        name = v.strip()
        if not name:
            raise ValueError("fields cannot be empty")
        return name
    if len(v) == 0:
        raise ValueError("fields list cannot be empty")
    cleaned = []
    for i, name in enumerate(v):
        n = name.strip()
        if not n:
            raise ValueError(f"fields[{i}] cannot be empty")
        cleaned.append(n)
    return cleaned
```

## Impact

Filtering policy can be unintentionally disabled while audit still records successful transform outcomes (`success_reason={"action":"filtered"}`), causing undetected policy bypass and incorrect compliance/audit conclusions.
