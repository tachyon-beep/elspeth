## Summary

`validate_tracing_config()` can crash with `TypeError` when `provider` is not a string/hashable value, instead of returning a validation error.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1: requires unusual YAML config like provider: {bad: type}; observability subsystem only)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/tracing.py`
- Line(s): 129, 146, 160
- Function/Method: `parse_tracing_config`, `validate_tracing_config`

## Evidence

`parse_tracing_config()` accepts `provider` as `Any` and stores it directly:

```python
# tracing.py:129
provider = config.get("provider", "none")
# tracing.py:146
return TracingConfig(provider=provider)
```

`validate_tracing_config()` then does set membership without type guarding:

```python
# tracing.py:160
if config.provider not in SUPPORTED_TRACING_PROVIDERS:
```

Repro (executed in repo):

- Input: `parse_tracing_config({"provider": {"bad": "type"}})`
- Output: `TracingConfig {'bad': 'type'}`
- Then `validate_tracing_config(...)` raises: `TypeError: unhashable type: 'dict'`

So malformed config at the trust boundary crashes validation instead of producing an actionable config error.

## Root Cause Hypothesis

The tracing config is modeled as `dict[str, Any]`, but `provider` is used as if it is always a valid string. There is no boundary type validation before set membership.

## Suggested Fix

In `validate_tracing_config()`, validate `provider` type before membership check, and return explicit errors:

```python
if not isinstance(config.provider, str):
    errors.append(
        f"Invalid tracing provider type: expected str, got {type(config.provider).__name__}."
    )
    return errors
```

Optionally also harden `parse_tracing_config()` to reject/coerce non-string provider values early.

## Impact

A malformed `tracing.provider` can hard-crash plugin startup (`on_start`) instead of cleanly disabling tracing with a clear warning. This is a config trust-boundary validation failure and degrades operational reliability.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/tracing.py.md`
- Finding index in source report: 1
- Beads: pending
