## Summary

`LLMConfig._validate_required_input_fields_declared()` is single-query-centric, so multi-query configs either get the wrong contract advice (`text_content` instead of the real row field `customer_text`) or bypass contract declaration entirely when the top-level template is static.

## Severity

- Severity: major
- Priority: P2

## Location

- File: [src/elspeth/plugins/transforms/llm/base.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/base.py)
- Line(s): 123-155
- Function/Method: `_validate_required_input_fields_declared`

## Evidence

In the target file, the validator only inspects `self.template`:

```python
fields_not_declared = self.required_input_fields is None
...
extracted = extract_jinja2_fields(self.template)
if extracted:
    raise ValueError(...)
```

Source: [base.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/base.py#L136)

That logic is wrong for multi-query mode because the real upstream dependencies come from `queries[*].input_fields`, not from the synthetic names visible inside the query template. `QuerySpec.build_template_context()` maps template variables to real row columns:

```python
for template_var, row_column in self.input_fields.items():
    context[template_var] = row[row_column]
```

Source: [multi_query.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/multi_query.py#L127)

If one of those mapped row columns is missing, runtime fails row-by-row in `_execute_one_query()`:

```python
except KeyError as e:
    return TransformResult.error({"reason": "template_context_failed", ...})
```

Source: [transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L471)

DAG validation only consults explicit `required_input_fields` / schema `required_fields`; it does not inspect `queries`:

```python
required_input = node_info.config.get("required_input_fields")
if required_input is not None and len(required_input) > 0:
    return frozenset(required_input)
```

Source: [graph.py](/home/john/elspeth/src/elspeth/core/dag/graph.py#L1459)

Verified behavior:

- `LLMConfig.from_dict(...)` with a static top-level template plus `queries={"q1": {"input_fields": {"text_content": "customer_text"}, "template": "Summarize {{ row.text_content }}"}}` succeeds and leaves `required_input_fields=None`.
- `LLMConfig.from_dict(...)` with `template="Summarize {{ row.text_content }}"` and the same query mapping fails, but the error tells the user to declare `required_input_fields: ['text_content']`, even though the actual upstream field is `customer_text`.

That means multi-query contract enforcement is both incomplete and misleading.

## Root Cause Hypothesis

The validator was written for single-query templates, where `extract_jinja2_fields(self.template)` approximates the transform's upstream dependencies. Multi-query mode introduced an indirection layer (`input_fields`: template variable -> row column), but `LLMConfig` never updated its contract logic to derive required fields from that mapping.

## Suggested Fix

Teach `LLMConfig` to branch on `self.queries` before using `extract_jinja2_fields(self.template)`.

For multi-query configs, the validator should:

1. Resolve `self.queries` into `QuerySpec`s.
2. Compute the real required upstream fields as the union of `spec.input_fields.values()`.
3. If `required_input_fields is None`, raise with those real row-column names.
4. Optionally validate that any declared `required_input_fields` covers that union, unless the user explicitly opts out with `[]`.

The current `extract_jinja2_fields(self.template)` logic should remain for true single-query configs only.

## Impact

Multi-query transforms can ship without accurate DAG contracts. Best case, users get a misleading config error and must opt out with `[]`. Worst case, the config passes validation, upstream schema mismatches are not caught at build time, and rows fail later with `template_context_failed` instead of a deterministic config-time contract error. That weakens ELSPETH's explicit-contract guarantees and pushes a preventable setup defect into runtime processing.
---
## Summary

`LLMConfig` accepts invalid `response_field` names even though downstream LLM schema builders require a non-empty Python identifier, so bad config survives model validation and only explodes later during transform construction.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: [src/elspeth/plugins/transforms/llm/base.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/base.py)
- Line(s): 72
- Function/Method: `LLMConfig.response_field`

## Evidence

The target file declares `response_field` as a plain `str` with no validator:

```python
response_field: str = Field("llm_response", description="Field name for LLM response in output")
```

Source: [base.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/base.py#L72)

But downstream helpers explicitly require `response_field` to be a non-empty identifier:

```python
if not response_field or not response_field.strip():
    raise ValueError("response_field cannot be empty or whitespace-only")
if not response_field.isidentifier():
    raise ValueError(...)
```

Source: [__init__.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/__init__.py#L73)

`LLMTransform.__init__()` calls those helpers while building declared output fields and output schemas:

- Single-query path: [transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L1103)
- Multi-query path: [transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L1057)

Verified behavior:

- `LLMConfig.from_dict(..., response_field='bad-field')` succeeds and produces `cfg.response_field == 'bad-field'`.
- `LLMTransform(...)` with the same value raises `ValueError: response_field 'bad-field' is not a valid Python identifier...`.

So the config object accepts a value that the transform cannot legally consume.

## Root Cause Hypothesis

Validation for `response_field` was centralized in helper functions used by schema-building code, but `LLMConfig` never mirrored that contract at the config boundary. The result is a split-brain contract: config parsing says the value is fine, transform initialization says it is not.

## Suggested Fix

Add a `field_validator("response_field")` in `LLMConfig` that enforces the same contract as `get_llm_guaranteed_fields()` / `get_llm_audit_fields()`:

- reject empty or whitespace-only values
- reject non-identifiers
- normalize surrounding whitespace if desired

That keeps invalid configs inside `PluginConfigError`/Pydantic validation instead of leaking them into later initialization code.

## Impact

This is a config-validation gap rather than a runtime data-corruption bug, but it still breaks the plugin contract: invalid field names are caught too late, after config parsing has already succeeded. That makes failures noisier and less local, and it weakens the expectation that `LLMConfig` is the authoritative gate for transform configuration correctness.
