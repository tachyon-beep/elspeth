## Summary

`validate_tracing_config()` only checks credentials for `None`, so empty strings and wrong types pass validation and reach SDK setup paths unvalidated.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1: tracing is optional observability; bad config causes SDK init failure, not data corruption)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/tracing.py`
- Line(s): 165-172 (validation), 134-143 (untyped parse assignment)
- Function/Method: `parse_tracing_config`, `validate_tracing_config`

## Evidence

Current checks:

```python
# tracing.py:165-172
if config.connection_string is None: ...
if config.public_key is None: ...
if config.secret_key is None: ...
```

No type/non-empty validation exists for:
- `connection_string`
- `public_key`
- `secret_key`
- `host`
- boolean flags

Repro (executed in repo):

- `validate_tracing_config(AzureAITracingConfig(connection_string=""))` -> `[]`
- `validate_tracing_config(LangfuseTracingConfig(public_key="", secret_key=""))` -> `[]`
- Parsing wrong types:
  - `connection_string=123`, `enable_live_metrics="yes"` -> `errors []`
  - `public_key=123`, `secret_key=['x']`, `host=False` -> `errors []`

Integration risk: callers treat `errors == []` as setup-ready, then call SDK init:
- `src/elspeth/plugins/llm/azure.py:275-280`, `304-324`
- `src/elspeth/plugins/llm/openrouter.py:259-263`, `290-313`

Those setup blocks only catch `ImportError`, so bad runtime values can propagate as uncaught exceptions.

## Root Cause Hypothesis

Validation logic checks only field presence (`None`) and assumes value shape/type is valid, even though config values are sourced from `dict[str, Any]`.

## Suggested Fix

Strengthen `validate_tracing_config()` with explicit boundary checks:

- Required secret fields: must be `str` and `strip()` non-empty.
- `host`: must be non-empty `str` (and preferably URL-validated).
- Boolean flags: must be `bool`.
- Return validation errors instead of allowing bad values into SDK constructors.

Example pattern:

```python
if not isinstance(config.connection_string, str) or not config.connection_string.strip():
    errors.append("azure_ai tracing requires non-empty connection_string.")
```

## Impact

Misconfigured tracing can silently pass validation, then fail later during setup/runtime with poor diagnostics or crashes. This creates observability blind spots and unstable startup behavior in LLM plugins.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/tracing.py.md`
- Finding index in source report: 2
- Beads: pending
