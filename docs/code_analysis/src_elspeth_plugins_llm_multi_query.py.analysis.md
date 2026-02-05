# Analysis: src/elspeth/plugins/llm/multi_query.py

**Lines:** 351
**Role:** Multi-query base configuration and data types. Defines the configuration models (`MultiQueryConfig`, `CaseStudyConfig`, `CriterionConfig`, `OutputFieldConfig`, `QuerySpec`) and enums (`OutputFieldType`, `ResponseFormat`) used by both `AzureMultiQueryLLMTransform` and `OpenRouterMultiQueryLLMTransform`. Handles query expansion (case_studies x criteria cross-product), JSON schema generation for structured outputs, and response format configuration.
**Key dependencies:** Imports from `pydantic`, `elspeth.plugins.config_base.PluginConfig`, `elspeth.plugins.llm.azure.AzureOpenAIConfig`. Imported by `azure_multi_query.py` and `openrouter_multi_query.py`. Also imported (partially) by `openrouter_multi_query.py` for `CaseStudyConfig`, `CriterionConfig`, `OutputFieldConfig`, `QuerySpec`, `ResponseFormat`.
**Analysis depth:** FULL

## Summary
This is a well-designed configuration module with good validation. The cross-product expansion, JSON schema generation, and type validation are clean. The main concern is an architectural coupling issue: `MultiQueryConfig` extends `AzureOpenAIConfig`, meaning it carries Azure-specific fields (`deployment_name`, `endpoint`, etc.) that are meaningless for the OpenRouter variant. The OpenRouter multi-query config (`OpenRouterMultiQueryConfig`) re-declares the multi-query fields separately. There is also a subtle collision potential in output prefixes that is not validated.

## Critical Findings

None.

## Warnings

### [190] MultiQueryConfig inherits from AzureOpenAIConfig -- tight coupling

**What:** `MultiQueryConfig` extends `AzureOpenAIConfig`, which means it carries Azure-specific required fields: `deployment_name`, `endpoint`, `api_key`, `api_version`. This config class is only used by `AzureMultiQueryLLMTransform`. However, the shared types (`QuerySpec`, `OutputFieldConfig`, `CaseStudyConfig`, `CriterionConfig`, `ResponseFormat`) are imported directly from this module by the OpenRouter variant. The OpenRouter variant (`OpenRouterMultiQueryConfig` in `openrouter_multi_query.py`) re-declares `case_studies`, `criteria`, `output_mapping`, `response_format`, `build_json_schema()`, `build_response_format()`, and `expand_queries()` -- approximately 90 lines of duplication.

**Why it matters:** The duplication creates a maintenance burden. Any change to output mapping validation, JSON schema generation, query expansion logic, or response format building must be synchronized across both files. If they diverge, the Azure and OpenRouter multi-query transforms will behave differently for the same configuration, which violates the principle of least surprise.

**Evidence:** Compare:
- `MultiQueryConfig` lines 290-350 (`build_json_schema`, `build_response_format`, `expand_queries`)
- `OpenRouterMultiQueryConfig` in `openrouter_multi_query.py` lines 130-189 (identical methods)

### [329-350] expand_queries() does not validate output_prefix uniqueness

**What:** The `expand_queries()` method generates output prefixes as `f"{case_study.name}_{criterion.name}"`. While the validator on line 246 checks for duplicate case_study names and duplicate criterion names separately, it does not check for collisions in the combined prefix. For example, case_study `"a_b"` with criterion `"c"` would produce the same prefix `"a_b_c"` as case_study `"a"` with criterion `"b_c"`.

**Why it matters:** Duplicate output prefixes would cause later output fields to overwrite earlier ones during the merge step in `_process_single_row_internal()`. The row would silently lose data from the first query that produced that prefix. Since this is an auditable pipeline, silent data loss is a critical audit integrity issue.

**Evidence:** Line 343: `output_prefix=f"{case_study.name}_{criterion.name}"`. No validation ensures uniqueness of the generated prefixes. The `validate_no_output_key_collisions` validator on line 246 only checks names within their own collections and output mapping suffix collisions with reserved suffixes.

### [96-125] QuerySpec.build_template_context uses direct key access -- raises KeyError

**What:** `build_template_context` accesses `row[field_name]` on line 113, preceded by an explicit `if field_name not in row: raise KeyError(...)` check on line 112. The method docstring says "Missing field is a config error, should crash." However, this raises `KeyError`, not a more informative error. More importantly, calling code in `azure_multi_query.py` line 374 and `openrouter_multi_query.py` line 711 calls this without catching the `KeyError`, meaning it will propagate up as an uncaught exception.

**Why it matters:** Per the Three-Tier Trust Model, this field lookup is on pipeline data (Tier 2) -- the row has been through source validation. A missing field here is either a config error (user configured wrong `input_fields`) or an upstream bug (source did not guarantee the field). In either case, the `KeyError` will crash the worker thread for this row. For the Azure variant this is caught by the pool executor; for the OpenRouter variant it may crash the batch. The error message is good but the exception type choice matters for error routing.

**Evidence:** Lines 111-114:
```python
for i, field_name in enumerate(self.input_fields, start=1):
    if field_name not in row:
        raise KeyError(f"Required field '{field_name}' not found in row for query {self.output_prefix}")
    context[f"input_{i}"] = row[field_name]
```

## Observations

### [15-23] OutputFieldType enum covers standard JSON types

**What:** The enum covers `STRING`, `INTEGER`, `NUMBER`, `BOOLEAN`, `ENUM`. This maps cleanly to JSON Schema types. The `ENUM` type is string-based, which is standard for LLM structured outputs.

### [36-71] OutputFieldConfig.to_json_schema() is clean

**What:** The conversion from internal type representation to JSON Schema is straightforward. The enum type correctly uses the `enum` keyword. The `model_validator` ensures enum types have values and non-enum types do not.

### [73-125] QuerySpec is a plain dataclass -- good separation

**What:** `QuerySpec` is a frozen-free dataclass (not frozen), which allows mutation during construction. It cleanly encapsulates the per-query template context building logic. The `max_tokens` per-query override (line 94) is a thoughtful feature for criterion-level token budgets.

### [246-288] validate_no_output_key_collisions is thorough for what it checks

**What:** The validator correctly identifies: (1) duplicate case_study names, (2) duplicate criterion names, (3) output mapping suffix collisions with reserved LLM suffixes. The import of `LLM_AUDIT_SUFFIXES` and `LLM_GUARANTEED_SUFFIXES` is done inside the validator to avoid circular imports.

### [310-328] build_response_format correctly implements both modes

**What:** The STANDARD mode returns `{"type": "json_object"}` and STRUCTURED mode returns the full JSON schema with `"strict": True` and `"additionalProperties": False`. This correctly leverages the OpenAI/Azure structured outputs feature.

### OpenRouterMultiQueryConfig duplication

**What:** The `OpenRouterMultiQueryConfig` in `openrouter_multi_query.py` duplicates `case_studies`, `criteria`, `output_mapping`, `response_format` fields plus `build_json_schema()`, `build_response_format()`, `expand_queries()`, and `parse_output_mapping()`. This is ~90 lines that is character-for-character identical (except that `expand_queries` in the OpenRouter variant does not pass `max_tokens` to `QuerySpec` -- see next finding).

### [339-350 vs openrouter_multi_query.py:169-189] expand_queries diverges on max_tokens

**What:** In `MultiQueryConfig.expand_queries()` (this file, line 347), the `QuerySpec` is constructed with `max_tokens=criterion.max_tokens`. In `OpenRouterMultiQueryConfig.expand_queries()` (openrouter_multi_query.py line 179-187), the `max_tokens` parameter is NOT passed. This means the OpenRouter variant ignores per-criterion `max_tokens` overrides.

**Why it matters:** This is a functional divergence between the Azure and OpenRouter multi-query transforms. Users who configure per-criterion max_tokens will get correct behavior on Azure but silently ignored behavior on OpenRouter. This is the exact maintenance hazard predicted by the duplication concern above.

## Verdict
**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Extract multi-query fields (`case_studies`, `criteria`, `output_mapping`, `response_format`) and methods (`build_json_schema`, `build_response_format`, `expand_queries`, `parse_output_mapping`) into a shared mixin or base config that both Azure and OpenRouter multi-query configs can inherit. This eliminates the ~90-line duplication and prevents divergence like the `max_tokens` bug. (2) Add output_prefix uniqueness validation to `expand_queries()` or the model validator. (3) Fix the OpenRouter variant's `expand_queries` to pass `max_tokens` to `QuerySpec`.
**Confidence:** HIGH -- all findings are verified by side-by-side comparison of the Azure and OpenRouter multi-query implementations.
