## Summary

Shared template sandbox allows helper/introspection methods like `row.to_dict()`, `row.keys()`, `row.get(...)`, and `row.contract.mode`, so prompt/query templates can bypass the field-access contract model and even trigger bogus `required_input_fields` validation errors.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [/home/john/elspeth/src/elspeth/plugins/infrastructure/templates.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/templates.py#L21)
- Line(s): 21-33
- Function/Method: `create_sandboxed_environment`

## Evidence

[target file](/home/john/elspeth/src/elspeth/plugins/infrastructure/templates.py#L21) returns a plain `ImmutableSandboxedEnvironment` with `StrictUndefined`. Its docstring says this factory “blocks attribute access and method calls,” but the actual environment does not enforce that.

Callers trust this factory for runtime safety:

- [PromptTemplate.__init__](/home/john/elspeth/src/elspeth/plugins/transforms/llm/templates.py#L107) uses it for all LLM prompt rendering.
- [QueryBuilder.__init__](/home/john/elspeth/src/elspeth/plugins/transforms/rag/query.py#L88) uses it for RAG query templates.

Verified against the repo code at runtime:

- `PromptTemplate("{{ row.to_dict() }}").render(row)` succeeds and renders the full row dict.
- `PromptTemplate("{{ row.contract.mode }}").render(row)` succeeds and exposes schema metadata.
- `PromptTemplate("Value: {{ row.get('missing', 'N/A') }}").render({})` succeeds and fabricates a default instead of raising `TemplateError`.
- `PromptTemplate("{{ row.keys() | list }}").render(row)` succeeds.

Those capabilities are not modeled by the field-extraction / contract tooling:

- [field extractor](/home/john/elspeth/src/elspeth/core/templates.py#L98) only has explicit handling for `row.get("field")`, `row.field`, and `row["field"]`.
- For `{{ row.to_dict() }}`, `extract_jinja2_fields()` returns `{'to_dict'}`.
- For `{{ row.contract.mode }}`, it returns `{'contract'}`.

That flows directly into config validation:

- [LLMConfig validator](/home/john/elspeth/src/elspeth/plugins/transforms/llm/base.py#L140) uses `extract_jinja2_fields(self.template)` to enforce `required_input_fields`.
- A template of `{{ row.to_dict() }}` therefore fails validation with a bogus suggestion to declare `required_input_fields: ['to_dict']`.

At execution time, successful helper-method calls avoid the normal row-quarantine path:

- [LLMTransform.execute](/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L244) only quarantines template problems when `PromptTemplate.render_with_metadata()` raises `TemplateError`.
- Because these helper/introspection calls succeed, the transform proceeds with undeclared whole-row access or fabricated defaults.

Tests only cover a narrower case:

- [LLM template tests](/home/john/elspeth/tests/unit/plugins/llm/test_templates.py#L207) verify mutation methods like `lookup.update()` are blocked.
- They do not cover read-only/introspection methods such as `to_dict`, `keys`, `get`, or `contract`.

## Root Cause Hypothesis

`create_sandboxed_environment()` assumes `ImmutableSandboxedEnvironment` is sufficient to ban method calls and internal attribute access, but Jinja only blocks unsafe/ mutating attributes by default. Read-only methods and non-underscore properties remain callable/readable, so ELSPETH’s higher-level template contract is broader than what the stock sandbox actually enforces.

## Suggested Fix

Replace the raw `ImmutableSandboxedEnvironment` with a project-specific subclass in this file that:

- Rejects callable attributes on template namespaces like `row` and `lookup`.
- Rejects non-field introspection attributes on `PipelineRow` such as `contract` and helper methods such as `to_dict`, `keys`, and `get`.
- Continues to allow normal field/item access (`row.field`, `row["field"]`, `lookup["key"]`).

Add regression tests covering at least:

- `row.to_dict()`
- `row.keys()`
- `row.contract.mode`
- `row.get('missing', 'N/A')`

and assert they raise `TemplateError`/sandbox violations.

## Impact

This breaks ELSPETH’s template contract guarantees in two ways:

- Templates can consume data outside the declared `required_input_fields` model by serializing or iterating the whole row.
- Templates can hide missing data with `row.get(..., default)`, producing prompts from fabricated values instead of surfacing row-scoped template failures.

It also produces false config-time guidance (`required_input_fields: ['to_dict']`, `['contract']`) and weakens schema/DAG validation for both LLM and RAG template paths.
