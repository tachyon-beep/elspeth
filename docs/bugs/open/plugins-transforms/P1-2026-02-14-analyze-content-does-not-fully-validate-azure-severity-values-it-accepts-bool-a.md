## Summary

`_analyze_content()` does not fully validate Azure severity values; it accepts `bool` and out-of-range integers, which can fail open and mark malformed responses as safe.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/content_safety.py`
- Line(s): 43-55, 507-510, 560-564
- Function/Method: `_analyze_content` (and downstream `_check_thresholds` behavior)

## Evidence

The module documents Azure severity as `0-6`:
`/home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/content_safety.py:43-55`

But runtime validation only checks `isinstance(..., int)`:

```python
if not isinstance(item["severity"], int):
    raise MalformedResponseError(...)
result[internal_name] = item["severity"]
```

Source: `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/content_safety.py:507-510`

Then threshold logic treats that value as trusted numeric severity:

```python
info["exceeded"] = info["severity"] > info["threshold"]
```

Source: `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/azure/content_safety.py:560-564`

Problems:
- `bool` passes `isinstance(x, int)` in Python (`False` -> `0`, `True` -> `1`)
- Negative/out-of-range ints are accepted (e.g., `-1`) and can be treated as safe

This violates fail-closed validation at an external Tier-3 boundary.

## Root Cause Hypothesis

Validation enforces only coarse numeric type and misses strict contract checks (exact int domain and bounds) for security-sensitive external response fields.

## Suggested Fix

Use strict integer and bounds validation at the boundary before storing severity:

```python
severity = item["severity"]
if type(severity) is not int or not (0 <= severity <= 6):
    raise MalformedResponseError(
        f"severity for {azure_category!r} must be int in [0, 6], got {severity!r}"
    )
```

(Use `type(...) is int` intentionally to reject `bool`.)

## Impact

Malformed provider responses can be treated as valid and pass content that should be rejected, producing incorrect `"validated"` outcomes and weakening security/audit integrity for moderation decisions.
