## Summary

`extract_jinja2_fields()` treats `PipelineRow` helper APIs like `row.keys()` and `row.contract.mode` as if they were input data fields, so valid templates trigger false `required_input_fields` errors for non-existent columns.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/core/templates.py`
- Line(s): 111-124, 174-184
- Function/Method: `_walk_ast`, `extract_jinja2_fields_with_details`

## Evidence

`_walk_ast()` adds every top-level `Getattr` on `row` except `get` as a field:

```python
if isinstance(node, Getattr) and isinstance(node.node, Name) and node.node.name == namespace and node.attr != "get":
    fields.add(node.attr)
```

That means method/property access is misclassified.

Evidence in the target file:
- [`templates.py:111`]( /home/john/elspeth/src/elspeth/core/templates.py#L111 ) through [`templates.py:124`]( /home/john/elspeth/src/elspeth/core/templates.py#L124 )
- [`templates.py:174`]( /home/john/elspeth/src/elspeth/core/templates.py#L174 ) through [`templates.py:184`]( /home/john/elspeth/src/elspeth/core/templates.py#L184 )

`PipelineRow` really does expose non-field APIs that templates can access:
- [`schema_contract.py:659`]( /home/john/elspeth/src/elspeth/contracts/schema_contract.py#L659 ) defines `keys()`
- [`schema_contract.py:675`]( /home/john/elspeth/src/elspeth/contracts/schema_contract.py#L675 ) defines `contract`

Live behavior confirms the mismatch:
- `PromptTemplate('{{ row.keys() | list | join(",") }}')` renders successfully to `customer_id`
- `extract_jinja2_fields('{{ row.keys() | length }}')` returns `frozenset({'keys'})`
- `extract_jinja2_fields('{{ row.contract.mode }}')` returns `frozenset({'contract'})`

That false extraction feeds config validation:
- [`base.py:140`]( /home/john/elspeth/src/elspeth/plugins/transforms/llm/base.py#L140 ) through [`base.py:153`]( /home/john/elspeth/src/elspeth/plugins/transforms/llm/base.py#L153 ) use `extract_jinja2_fields()` to force `required_input_fields`

Reproduced error:
- `LLMConfig.from_dict(..., template='{{ row.keys() | length }}')`
- raises: `LLM template references row fields ['keys'] but required_input_fields is not declared.`

What the code does:
- Flags any `row.<name>` as a data dependency.

What it should do:
- Distinguish row data access from `PipelineRow` API access, and avoid reporting method/property calls like `keys`, `contract`, and similar engine-owned members as schema fields.

## Root Cause Hypothesis

The AST walk assumes all top-level `row.<attr>` accesses are field reads, with a one-off special case only for `row.get(...)`. That shortcut breaks once `row` is not a plain dict but a `PipelineRow` object with its own methods/properties. The extractor was written around syntax shape, not around the actual runtime surface of the object templates render against.

## Suggested Fix

Teach the walker to exclude non-field `PipelineRow` members.

A safe direction in `templates.py`:
- Skip `Getattr` nodes when they are the callee of a `Call` unless the call is the supported `row.get("field")` form.
- Maintain a small denylist for engine-owned top-level attributes exposed on `PipelineRow` such as `contract`, `keys`, and `get`.
- Mirror the same filtering in `extract_jinja2_fields_with_details()`.

Helpful regression cases:
- `{{ row.keys() | length }}` -> no extracted fields
- `{{ row.contract.mode }}` -> no extracted fields
- `{{ row.customer_id }}` -> `{"customer_id"}`
- `{{ row.get("customer_id") }}` -> `{"customer_id"}`

## Impact

This breaks config-time contract enforcement for valid templates that use `PipelineRow` helper APIs. Users are pushed toward either bogus `required_input_fields` declarations or `[]` opt-out, so DAG validation becomes noisier and less trustworthy. The failure is pre-runtime, but it degrades the explicit-contract workflow the helper is supposed to support.
---
## Summary

`extract_jinja2_fields()` returns original header names from bracket syntax verbatim, even though its own documented use is to populate `required_input_fields`, and `required_input_fields` rejects non-identifier names like `"Customer ID"`.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/core/templates.py`
- Line(s): 51-55, 116-124, 193-260
- Function/Method: `extract_jinja2_fields`, `extract_jinja2_fields_with_names`

## Evidence

The module-level docs explicitly tell developers to use extracted fields to fill `required_input_fields`:
- [`templates.py:15`]( /home/john/elspeth/src/elspeth/core/templates.py#L15 ) through [`templates.py:18`]( /home/john/elspeth/src/elspeth/core/templates.py#L18 )

`extract_jinja2_fields()` returns bracket keys exactly as written:
- [`templates.py:116`]( /home/john/elspeth/src/elspeth/core/templates.py#L116 ) through [`templates.py:124`]( /home/john/elspeth/src/elspeth/core/templates.py#L124 )

So for `{{ row["Customer ID"] }}`, extraction returns `frozenset({"Customer ID"})`.

But config validation requires identifiers only:
- [`config_base.py:309`]( /home/john/elspeth/src/elspeth/plugins/infrastructure/config_base.py#L309 ) through [`config_base.py:316`]( /home/john/elspeth/src/elspeth/plugins/infrastructure/config_base.py#L316 )

Reproduced end-to-end:
1. `LLMConfig.from_dict(..., template='{{ row["Customer ID"] }}')` raises:
   `LLM template references row fields ['Customer ID'] but required_input_fields is not declared.`
   Evidence path:
   - [`base.py:145`]( /home/john/elspeth/src/elspeth/plugins/transforms/llm/base.py#L145 ) through [`base.py:153`]( /home/john/elspeth/src/elspeth/plugins/transforms/llm/base.py#L153 )

2. If the user follows that guidance and sets `required_input_fields: ['Customer ID']`, validation fails with:
   `required_input_fields[0] must be a valid Python identifier, got 'Customer ID'`

The target file already contains a resolver that knows how to normalize names with a contract:
- [`templates.py:193`]( /home/john/elspeth/src/elspeth/core/templates.py#L193 ) through [`templates.py:260`]( /home/john/elspeth/src/elspeth/core/templates.py#L260 )

What the code does:
- Returns raw original-name strings from `extract_jinja2_fields()`, then separately offers `extract_jinja2_fields_with_names()` that can normalize them.

What it should do:
- The helper used for required-field discovery must return names that are valid for `required_input_fields`, or expose a contract-aware path that callers can actually use for that purpose.

## Root Cause Hypothesis

The module mixes two incompatible conventions:
- discovery from template syntax “as written”
- config declaration in normalized schema-field names

That split is visible in `extract_jinja2_fields_with_names()`, but the main helper and its docs still present raw extracted names as directly usable config. Once original headers are referenced via bracket syntax, the helper produces output that the config layer cannot accept.

## Suggested Fix

Make field-discovery output align with config semantics.

Practical fixes in `templates.py`:
- Add a contract-aware extraction mode to `extract_jinja2_fields()` that resolves original names to normalized names before returning them.
- Or promote `extract_jinja2_fields_with_names()` into the primary API for config guidance and ensure callers can pass a `SchemaContract`.
- At minimum, stop documenting raw `extract_jinja2_fields()` output as directly suitable for `required_input_fields` when bracket syntax can produce invalid identifiers.

Regression cases to add:
- `{{ row["Customer ID"] }}` with a contract mapping `Customer ID -> customer_id` should produce `customer_id` for config-facing discovery.
- The LLM validation error path should never recommend `required_input_fields: ['Customer ID']`.

## Impact

Templates that correctly use original source headers cannot participate in the explicit `required_input_fields` workflow. Users either get unusable guidance or must opt out of DAG validation entirely with `required_input_fields: []`, weakening config-time contract checks for a legitimate template style.
