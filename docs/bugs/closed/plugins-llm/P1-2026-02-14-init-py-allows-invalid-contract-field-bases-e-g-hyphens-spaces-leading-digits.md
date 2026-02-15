## Summary

`src/elspeth/plugins/llm/__init__.py` allows invalid contract field bases (e.g., hyphens/spaces/leading digits), so LLM transforms can publish `guaranteed_fields`/`audit_fields` that violate field-name contracts.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1: requires deliberate misconfiguration of response_field; unlikely in practice)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/__init__.py`
- Line(s): `80-83`, `101-103`, `126-128`
- Function/Method: `get_llm_guaranteed_fields`, `get_llm_audit_fields`, `get_multi_query_guaranteed_fields`

## Evidence

In the target file, validation only rejects empty/whitespace-only strings, then concatenates the **raw** base value:

```python
if not response_field or not response_field.strip():
    raise ValueError(...)
return tuple(f"{response_field}{suffix}" for suffix in LLM_GUARANTEED_SUFFIXES)
```

Same pattern exists for audit and multi-query helpers at `src/elspeth/plugins/llm/__init__.py:101-103` and `src/elspeth/plugins/llm/__init__.py:126-128`.

These helpers are used directly when building transform output schema contracts, e.g.:
- `src/elspeth/plugins/llm/openrouter.py:150`, `src/elspeth/plugins/llm/openrouter.py:163-164`
- `src/elspeth/plugins/llm/azure.py:165`, `src/elspeth/plugins/llm/azure.py:178-179`
- `src/elspeth/plugins/llm/base_multi_query.py:107`, `src/elspeth/plugins/llm/base_multi_query.py:111`

But field-name contract rules require Python identifiers:
- `src/elspeth/contracts/schema.py:160-165` (`name.isidentifier()` enforced)
- `src/elspeth/plugins/config_base.py:316-320` (`required_input_fields` must be identifiers)

Repro in current code:
- `get_llm_guaranteed_fields("bad field")` returns `("bad field", "bad field_usage", ...)`
- `get_llm_audit_fields("bad-field")` returns `("bad-field_template_hash", ...)`
- Instantiating `OpenRouterLLMTransform` with `response_field="bad-field"` produces `guaranteed_fields` containing `"bad-field"` and `"bad-field_usage"`.

So the target file is generating contract metadata that can violate downstream schema/contract assumptions.

## Root Cause Hypothesis

The helper functions in `llm/__init__.py` perform only emptiness checks and never normalize/validate identifier semantics. Because they are the shared contract-field generator for LLM plugins, invalid config values propagate system-wide into schema contracts.

## Suggested Fix

In `src/elspeth/plugins/llm/__init__.py`, centralize strict normalization/validation and use it in all three helpers:

```python
def _validate_field_base(value: str, arg_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{arg_name} cannot be empty or whitespace-only")
    if not normalized.isidentifier():
        raise ValueError(
            f"{arg_name} must be a valid Python identifier, got {value!r}"
        )
    return normalized
```

Then:
- validate+normalize `response_field` in `get_llm_guaranteed_fields` and `get_llm_audit_fields`
- validate+normalize `output_prefix` in `get_multi_query_guaranteed_fields`
- build returned tuples from the normalized value.

## Impact

- Schema contract integrity is weakened: transforms can advertise invalid `guaranteed_fields`/`audit_fields`.
- DAG field-contract checks may become misleading or unusable for those fields.
- Downstream transforms cannot reliably declare dependencies (identifier-only rules), creating preventable config/runtime failures.
- Violates CLAUDE.md contract/auditability intent by allowing malformed field metadata to enter the recorded pipeline contract.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/__init__.py.md`
- Finding index in source report: 1
- Beads: pending
