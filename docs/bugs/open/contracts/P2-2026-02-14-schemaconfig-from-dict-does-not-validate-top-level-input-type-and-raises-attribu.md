## Summary

`SchemaConfig.from_dict()` does not validate top-level input type and raises `AttributeError` for non-dict input, violating its documented `ValueError` contract and bypassing structured validation paths.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/schema.py`
- Line(s): 310-327 (first failing access at 325)
- Function/Method: `SchemaConfig.from_dict`

## Evidence

`from_dict` assumes dict and immediately calls `.get()`:

```python
guaranteed_fields = _parse_field_names_list(config.get("guaranteed_fields"), "guaranteed_fields")
```

No guard exists for non-dict `config`, so malformed input raises `AttributeError` instead of `ValueError`.

Repro (executed in repo with `PYTHONPATH=src`):

- `SchemaConfig.from_dict([])` -> `AttributeError: 'list' object has no attribute 'get'`
- `SchemaConfig.from_dict("x")` -> `AttributeError: 'str' object has no attribute 'get'`
- `SchemaConfig.from_dict(None)` -> `AttributeError: 'NoneType' object has no attribute 'get'`

Integration expectation mismatch:

- `/home/john/elspeth-rapid/src/elspeth/plugins/validation.py:199-214` catches `ValueError` from `SchemaConfig.from_dict()` and explicitly relies on that contract for structured errors.

## Root Cause Hypothesis

`from_dict` relies on static typing (`dict[str, Any]`) but omits runtime trust-boundary validation. Callers and docs assume `ValueError` on invalid schema config, but non-dict values trigger uncaught attribute access failures.

## Suggested Fix

Add an early runtime type guard in `SchemaConfig.from_dict`:

```python
if not isinstance(config, dict):
    raise ValueError(f"Schema config must be a dict, got {type(config).__name__}")
```

Keep all invalid user/config inputs on the documented `ValueError` path.

## Impact

Malformed schema payloads can crash validation flows instead of returning actionable validation errors, reducing operator debuggability and violating contract expectations in consumers like `PluginConfigValidator`.

## Triage

- Status: open
- Source report: `docs/bugs/generated/contracts/schema.py.md`
- Finding index in source report: 2
- Beads: pending
