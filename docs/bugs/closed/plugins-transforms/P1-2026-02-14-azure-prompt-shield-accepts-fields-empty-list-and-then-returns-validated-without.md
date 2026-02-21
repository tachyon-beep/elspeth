## Summary

`azure_prompt_shield` accepts `fields: []` and then returns `"validated"` without scanning any content, creating a fail-open security path.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/prompt_shield.py
- Line(s): 70-73, 288-289, 367-370, 372-379
- Function/Method: `AzurePromptShieldConfig`, `AzurePromptShield._get_fields_to_scan`, `AzurePromptShield._process_single_with_state`

## Evidence

`fields` has no non-empty validation:

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/prompt_shield.py:70-73
fields: str | list[str] = Field(...)
```

Empty list is passed through directly:

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/prompt_shield.py:372-379
if self._fields == "all":
    ...
elif isinstance(self._fields, str):
    return [self._fields]
else:
    return self._fields
```

Processing loop silently skips and returns success:

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/prompt_shield.py:288-370
for field_name in fields_to_scan:
    ...
return TransformResult.success(row, success_reason={"action": "validated"})
```

Verified by runtime repro in this repo:
- `AzurePromptShieldConfig.from_dict(..., fields=[])` is accepted.
- `_process_single_with_state(...)` returns `status=success`.
- `record_call_count` remains `0` (no external safety call recorded).

## Root Cause Hypothesis

The config model does not enforce a non-empty `fields` configuration, and runtime logic treats an empty field list as "nothing to do" instead of a configuration error/fail-closed error result.

## Suggested Fix

Add strict validation in this file:
1. `fields` list must be non-empty when list mode is used.
2. Each field name must be non-empty after strip.
3. Optionally reject duplicates.

Example direction:

```python
@field_validator("fields")
@classmethod
def validate_fields(cls, v: str | list[str]) -> str | list[str]:
    if isinstance(v, str):
        if not v.strip():
            raise ValueError("fields cannot be empty")
        return v
    if len(v) == 0:
        raise ValueError("fields list cannot be empty")
    cleaned = [f.strip() for f in v]
    if any(not f for f in cleaned):
        raise ValueError("fields entries cannot be empty")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError("fields contains duplicates")
    return cleaned
```

## Impact

Rows can be marked as `"validated"` without any Prompt Shield API call. This weakens security guarantees and audit semantics by recording successful validation for unscanned content.
