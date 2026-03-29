## Summary

`resolve_queries()` only logs a warning for reserved output suffixes, but some of those suffixes deterministically collide with ELSPETH’s auto-generated operational fields and silently overwrite user-requested structured output.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/llm/multi_query.py
- Line(s): 231-252
- Function/Method: `resolve_queries`

## Evidence

In the target file, reserved suffixes are detected but not rejected:

```python
if field.suffix in reserved_suffixes:
    logger.warning(...)
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/multi_query.py:245-252`

The warning is insufficient because downstream code writes auto-generated operational fields using the same naming scheme:

```python
field_key = f"{spec.name}_{field.suffix}"
partial[field_key] = parsed[field.suffix]
...
populate_llm_operational_fields(
    partial,
    f"{spec.name}_{self.response_field}",
    usage=result.usage,
    model=result.model,
)
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:657-686` and `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:691-696`

`populate_llm_operational_fields()` writes:

```python
output[f"{field_prefix}_usage"] = ...
output[f"{field_prefix}_model"] = model
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/__init__.py:125-145`

So a query named `quality` with `response_field="llm_response"` and an extracted field suffix of `llm_response_usage` produces the user field `quality_llm_response_usage`, which is then overwritten by the operational usage metadata field of the same name. The same class of collision exists for `llm_response_model` and reserved audit suffixes.

The target file already knows these suffixes are dangerous, but today it merely warns and continues. Tests also codify that current behavior is only a warning, not rejection:

- `/home/john/elspeth/tests/unit/plugins/llm/test_multi_query.py:434-466`

What the code does:
- Accepts conflicting suffixes and logs.

What it should do:
- Reject any suffix that can generate a key already reserved by the transform’s guaranteed/audit field namespace.

## Root Cause Hypothesis

The collision check in `resolve_queries()` is incomplete. It only checks collisions among user-declared `output_fields`, while treating reserved suffix conflicts as advisory. But multi-query output names are composed later by concatenation with query name and `response_field`, and that later composition creates guaranteed key overlaps with system-owned fields.

## Suggested Fix

Change reserved suffix handling from warning to validation failure. `resolve_queries()` should reject any `field.suffix` that can generate a system-owned output key for that query, not just warn.

A robust fix would:
- Reject suffixes derived from `LLM_GUARANTEED_SUFFIXES` and `LLM_AUDIT_SUFFIXES`
- Reject suffixes like `error`
- Reject suffixes that equal or begin with the configured `response_field` namespace when they can produce `"{query}_{response_field}..."` collisions

## Impact

Structured LLM output can be silently replaced by usage/model metadata in the emitted row. That is silent data loss in pipeline data, and it also corrupts audit interpretability because the row no longer reflects the field the query actually produced.
---
## Summary

Per-query `max_tokens` bypasses the normal LLM config validation entirely, so invalid values are accepted and either silently ignored (`0`) or passed through to providers as invalid request parameters.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/llm/multi_query.py
- Line(s): 99-113, 175-184, 199-205
- Function/Method: `QuerySpec.__post_init__`, `resolve_queries`

## Evidence

Top-level LLM config validates `max_tokens` as `gt=0`:

```python
max_tokens: int | None = Field(None, gt=0, description="Maximum tokens in response")
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/base.py:70-72`

But per-query `max_tokens` in the target file is just a raw dataclass field with no validation:

```python
max_tokens: int | None = None
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/multi_query.py:99-104`

And `resolve_queries()` forwards config values directly into `QuerySpec`:

```python
max_tokens=definition.get("max_tokens")
...
max_tokens=item.get("max_tokens")
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/multi_query.py:182-183` and `/home/john/elspeth/src/elspeth/plugins/transforms/llm/multi_query.py:204-205`

Later, runtime selection uses:

```python
query_max_tokens = spec.max_tokens or self.max_tokens
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:518`

That means:
- `max_tokens=0` is accepted, then silently discarded in favor of the global value because `0` is falsy
- `max_tokens=-1` is accepted, then passed to `provider.execute_query(...)` unchanged

What the code does:
- Accepts invalid per-query token limits.

What it should do:
- Enforce the same positive-integer contract for per-query overrides that the main LLM config already enforces.

## Root Cause Hypothesis

`queries` is modeled as raw `dict[str, Any]` / `list[dict[str, Any]]` in the main Pydantic config, and `resolve_queries()` manually constructs `QuerySpec` dataclasses afterward. That manual path skipped the `gt=0` validation already present on the main config model.

## Suggested Fix

Validate `QuerySpec.max_tokens` in `__post_init__`:
- Reject `bool`
- Reject non-`int`
- Reject values `<= 0`

That keeps per-query overrides aligned with the top-level LLM config contract and prevents silent fallback behavior from `spec.max_tokens or self.max_tokens`.

## Impact

Bad config is accepted instead of failing fast. In one branch the override is silently ignored, and in the other it can reach the provider as an invalid request parameter, causing avoidable runtime failures and making configuration behavior inconsistent with the documented LLM config contract.
