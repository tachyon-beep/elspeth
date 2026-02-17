## Summary

`validate_field_names()` can raise `AttributeError` for non-string entries, violating its documented `ValueError` contract and bypassing uniform config error wrapping.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/core/identifiers.py`
- Line(s): 13, 24-26
- Function/Method: `validate_field_names`

## Evidence

`validate_field_names()` documents `ValueError` on invalid names, but it directly calls `name.isidentifier()` without first ensuring `name` is a `str`:

```python
# src/elspeth/core/identifiers.py:21,25
# Raises:
#   ValueError: If any name is invalid identifier, is Python keyword, or is duplicate
if not name.isidentifier():
```

Reproduction:

```python
from elspeth.core.identifiers import validate_field_names
validate_field_names(["ok", 1], "columns")
# -> AttributeError: 'int' object has no attribute 'isidentifier'
```

Why this matters in integration: config wrappers normalize errors as `PluginConfigError` only for `ValidationError` and `ValueError` (`src/elspeth/plugins/config_base.py:76-79`). If this helper ever receives mixed-type data, the raw `AttributeError` escapes that contract.

## Root Cause Hypothesis

The function assumes static type hints (`list[str]`) are enforced at runtime and skips explicit runtime type validation before string method calls.

## Suggested Fix

Add an explicit type check in `validate_field_names()` before calling string methods, and raise `ValueError` with context/index.

```python
for i, name in enumerate(names):
    if type(name) is not str:
        raise ValueError(f"{context}[{i}] must be a string, got {type(name).__name__}")
    if not name.isidentifier():
        raise ValueError(f"{context}[{i}] '{name}' is not a valid Python identifier")
```

Also add a unit test in `tests/unit/core/test_identifiers.py` for non-string input.

## Impact

Current main config paths are mostly protected by Pydantic typing, so this is likely latent. But when triggered, it produces non-actionable exception type leakage (`AttributeError`) and breaks the helper’s documented validation contract, reducing reliability of error handling at config boundaries.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/identifiers.py.md`
- Finding index in source report: 1
- Beads: pending
