## Summary

`_build_augmented_output_schema()` advertises single-query LLM outputs as `Any | None` instead of their real emitted types, so valid explicit-schema downstream consumers fail Phase 2 compatibility checks.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/llm/__init__.py
- Line(s): 186-239, especially 222-239
- Function/Method: `_build_augmented_output_schema`

## Evidence

[`/home/john/elspeth/src/elspeth/plugins/transforms/llm/__init__.py:222`](/home/john/elspeth/src/elspeth/plugins/transforms/llm/__init__.py#L222) builds every added LLM field as optional `field_type="any"`:

```python
llm_field_names = [*get_llm_guaranteed_fields(response_field)]
extra_fields = tuple(
    FieldDefinition(name=name, field_type="any", required=False) ...
)
```

But the single-query implementation emits concrete types:
- [`/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:339`](/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L339) writes `output[self.response_field] = content`, where `content` is a `str`.
- [`/home/john/elspeth/src/elspeth/plugins/transforms/llm/__init__.py:144-145`](/home/john/elspeth/src/elspeth/plugins/transforms/llm/__init__.py#L144) writes `usage.to_dict()` and `model`.

ELSPETH’s compatibility checker treats producer `Any` as incompatible with a strict consumer expecting `str`/`int`:
- [`/home/john/elspeth/src/elspeth/contracts/data.py:181-185`](/home/john/elspeth/src/elspeth/contracts/data.py#L181)
- [`/home/john/elspeth/src/elspeth/contracts/data.py:292-312`](/home/john/elspeth/src/elspeth/contracts/data.py#L292)

Verified in-repo by instantiating `LLMTransform` and checking the generated schema:
- `llm_response -> typing.Any | None`
- `check_compatibility(producer=transform.output_schema, consumer expects llm_response: str)` returns `compatible=False` with mismatch `('llm_response', 'str', 'typing.Any | None')`

So the helper says “this field is untyped,” while the transform always emits a string response. That makes explicit downstream schemas reject a valid pipeline at graph-build time.

## Root Cause Hypothesis

The helper only models field presence for DAG contract propagation and never maps the LLM-added fields to their actual runtime types. That was sufficient for `guaranteed_fields`, but `output_schema` is also used for structural/type compatibility, so using `any` here erases the contract.

## Suggested Fix

Give the added single-query fields their real types instead of `any`:
- `<response_field>`: `str`
- `<response_field>_usage`: structured object type if supported, otherwise `any`
- `<response_field>_model`: `str`

If `SchemaConfig` cannot yet express dict-shaped usage metadata precisely, at minimum fix the response/model fields so downstream consumers can depend on the common contract.

## Impact

Explicit-schema pipelines cannot safely connect a downstream transform or sink that expects `llm_response: str`, even though the LLM transform always emits a string. This breaks graph construction for valid pipelines and weakens schema contracts by forcing downstream code to accept `Any` instead of the real LLM output type.
---
## Summary

`_build_multi_query_output_schema()` drops the configured types of extracted `output_fields`, advertising them as `Any | None`, so downstream explicit consumers of fields like `quality_score: int` are rejected even when the LLM transform validates and emits that exact type.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/llm/__init__.py
- Line(s): 242-306, especially 293-299
- Function/Method: `_build_multi_query_output_schema`

## Evidence

[`/home/john/elspeth/src/elspeth/plugins/transforms/llm/__init__.py:293-296`](/home/john/elspeth/src/elspeth/plugins/transforms/llm/__init__.py#L293) adds extracted multi-query fields with `field_type="any"`:

```python
for field_name in (extracted_fields or {}).get(query_name, ()):
    if field_name not in existing_names:
        extra_fields.append(FieldDefinition(name=field_name, field_type="any", required=False))
```

But the multi-query executor treats these as typed fields:
- [`/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:656-684`](/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L656) validates each configured `output_fields` entry with `validate_field_value(...)` before writing it to the row.
- [`/home/john/elspeth/src/elspeth/tests/unit/plugins/llm/test_transform.py:1371-1410`](/home/john/elspeth/tests/unit/plugins/llm/test_transform.py#L1371) already documents the schema/contract sensitivity here, but only checks field presence, not field annotations.

Verified in-repo:
- `quality_score -> typing.Any | None`
- `check_compatibility(producer=transform.output_schema, consumer expects quality_score: int)` returns `compatible=False` with mismatch `('quality_score', 'int', 'typing.Any | None')`

This is specifically a bug in the target file: the transform does the right runtime validation, but the schema helper erases that information when building `output_schema`.

## Root Cause Hypothesis

`_build_multi_query_output_schema()` only receives prefixed extracted field names, not their `OutputFieldConfig` definitions, so it cannot preserve the declared type (`integer`, `string`, etc.). The helper therefore falls back to `any`, which breaks ELSPETH’s explicit-schema compatibility checks.

## Suggested Fix

Pass typed extracted-field metadata into `_build_multi_query_output_schema()` instead of only names. For example:
- change `extracted_fields` from `dict[str, tuple[str, ...]]` to something that preserves each field’s configured type
- map ELSPETH output field types to the corresponding `FieldDefinition.field_type`
- build `quality_score` as `integer`, `quality_label` as `string`, etc.

Add a test that asserts both presence and annotation compatibility for extracted fields, not just `model_fields` membership.

## Impact

Valid multi-query pipelines with structured outputs cannot connect to downstream explicit consumers of those extracted columns. The transform validates and emits typed fields, but `output_schema` lies about them, so graph-build compatibility fails before execution. This undermines the plugin contract layer and pushes users toward weaker `Any`-accepting schemas.
