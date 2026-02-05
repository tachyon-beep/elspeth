# Analysis: src/elspeth/plugins/llm/base.py

**Lines:** 374
**Role:** Base LLM transform providing shared logic for all LLM transforms. Defines `LLMConfig` (Pydantic model for configuration), `BaseLLMTransform` (abstract base class for single-query LLM transforms), and the canonical `process()` method implementing template rendering, LLM API call, and output building.
**Key dependencies:** Imports from `elspeth.contracts` (Determinism, TransformResult, propagate_contract, SchemaConfig, PipelineRow), `elspeth.plugins.base` (BaseTransform), `elspeth.plugins.clients.llm` (AuditedLLMClient, LLMClientError), `elspeth.plugins.llm.templates` (PromptTemplate, TemplateError), `elspeth.plugins.config_base` (TransformDataConfig), `elspeth.plugins.llm` (__init__ field helpers). Imported by `azure.py` and `openrouter.py` for `LLMConfig`. `BaseLLMTransform` is the abstract base for simple synchronous LLM transforms.
**Analysis depth:** FULL

## Summary

The file is well-structured and follows the Three-Tier Trust Model correctly. The `LLMConfig` has good validation including template syntax checking and a model validator that enforces explicit field declarations for template row references. The `BaseLLMTransform.process()` method properly separates error handling tiers: wraps template rendering and LLM calls, lets internal logic crash. There are two findings that warrant attention: a missing contract passthrough in template rendering (causing dual-name resolution to silently stop working in subclasses that call `render_with_metadata` without contract), and a subtle behavioral divergence between `BaseLLMTransform` and `AzureLLMTransform` where the base class passes contract to template rendering but the Azure subclass does not.

## Critical Findings

_None identified._

## Warnings

### [W1: LINE 281-370] BaseLLMTransform.process() is not used by any concrete subclass in production

**What:** `BaseLLMTransform.process()` provides a complete synchronous processing implementation, but the two production subclasses (`AzureLLMTransform` and `OpenRouterLLMTransform`) do NOT extend `BaseLLMTransform` at all. They extend `BaseTransform` + `BatchTransformMixin` directly and implement their own `_process_row()` methods. The only relationship is that they import `LLMConfig` from this module.

**Why it matters:** This creates a divergence risk. The base class `process()` method has features (like passing `contract=input_contract` to template rendering at line 304) that the concrete subclasses do not replicate. If someone adds a new LLM transform extending `BaseLLMTransform`, they get contract-aware template rendering. If they copy the pattern from `AzureLLMTransform`, they do not. This is confusing and could lead to subtle template resolution bugs.

**Evidence:**
```python
# base.py line 304 - passes contract for dual-name resolution
rendered = self._template.render_with_metadata(row_data, contract=input_contract)

# azure.py line 419 - does NOT pass contract
rendered = self._template.render_with_metadata(row_data)

# openrouter.py line 505 - does NOT pass contract
rendered = self._template.render_with_metadata(row_data)
```

The `contract` parameter enables templates to use original header names (e.g., `{{ row["Amount USD"] }}`). Without it, only normalized names work. This means templates with original-name references will silently fail (raise TemplateError for undefined variable) in Azure/OpenRouter but work in any future transform extending `BaseLLMTransform`.

### [W2: LINE 218-260] Significant code duplication between BaseLLMTransform.__init__ and concrete subclass __init__ methods

**What:** The `__init__` method of `BaseLLMTransform` (lines 218-260) performs config parsing, template creation, schema creation, and output schema config building. The `AzureLLMTransform.__init__` (azure.py lines 134-213) and `OpenRouterLLMTransform.__init__` (openrouter.py lines 117-193) duplicate this entire block almost verbatim, because they inherit from `BaseTransform` instead of `BaseLLMTransform`.

**Why it matters:** This is a maintenance risk. Any bug fix or enhancement to the init logic (e.g., adding a new audit field, changing schema construction) must be replicated in three places. The fact that the contract passthrough divergence (W1) already exists suggests this is not hypothetical.

**Evidence:** All three init methods contain identical blocks for:
- `PromptTemplate` construction (lines 223-228 in base, 155-160 in azure, 137-142 in openrouter)
- Schema creation (lines 237-244 in base, 169-176 in azure, 150-158 in openrouter)
- Output schema config building (lines 246-260 in base, 178-192 in azure, 160-174 in openrouter)

### [W3: LINE 97-116] LLMConfig.pool_config property returns None for pool_size=1 but PoolConfig fields still validated

**What:** When `pool_size` is 1 (sequential mode), `pool_config` returns `None`, but the other pool-related fields (`min_dispatch_delay_ms`, `max_dispatch_delay_ms`, etc.) are still validated by Pydantic. A user who sets `pool_size: 1` with `backoff_multiplier: 0.5` (invalid, must be > 1) will get a validation error even though pooling is disabled.

**Why it matters:** This is a minor UX issue but could confuse users who configure `pool_size: 1` and get errors about pooling parameters they're not using. Low severity since it's an edge case in config validation.

**Evidence:**
```python
# Line 93: backoff_multiplier always validated
backoff_multiplier: float = Field(2.0, gt=1.0, ...)

# Line 97-108: pool_config returns None if pool_size <= 1
@property
def pool_config(self) -> PoolConfig | None:
    if self.pool_size <= 1:
        return None  # But fields were already validated above
```

## Observations

### [O1: LINE 150-165] Model validator uses inline import for extract_jinja2_fields

**What:** The `_validate_required_input_fields_declared` model validator imports `extract_jinja2_fields` from `elspeth.core.templates` inside the validator body. This is a runtime import during config validation.

**Why it matters:** While inline imports to avoid circular dependencies are common, this one runs during Pydantic model construction, which happens frequently (every config parse). The import itself is cached by Python after the first call, so the performance impact is negligible. However, the import path (`elspeth.core.templates`) should be verified to not pull in heavy dependencies that would slow down config validation in batch scenarios.

### [O2: LINE 372-374] BaseLLMTransform.close() is empty

**What:** The `close()` method is a pass-through. The concrete subclasses (`AzureLLMTransform`, `OpenRouterLLMTransform`) implement their own close logic with tracing flush and batch processing shutdown.

**Why it matters:** If `BaseLLMTransform` were used directly (which it cannot be, it's abstract), there would be no resource cleanup. This is fine architecturally since the abstract method prevents instantiation, but it means the base class does not provide a template for resource cleanup that subclasses should follow.

### [O3: LINE 34-166] LLMConfig is well-designed with appropriate validation

**What:** `LLMConfig` provides:
- Template syntax validation at config time (line 118-129)
- Required input field enforcement for template row references (line 131-165)
- Pool configuration as flat fields assembled into `PoolConfig` when needed

This follows the ELSPETH configuration philosophy of catching errors early at config time rather than runtime.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The primary concern is the behavioral divergence between `BaseLLMTransform.process()` and the concrete subclass `_process_row()` methods (W1). The contract passthrough is missing in both Azure and OpenRouter, which means templates using original header names will fail in production. If dual-name template access is an intended feature, the concrete subclasses need to be updated. If it is not needed for LLM transforms, the contract parameter in the base class process method should be documented as intentionally omitted in batch subclasses. The code duplication (W2) should be addressed to prevent further divergence.
**Confidence:** HIGH -- Full read of all three files plus dependencies. The divergence between base and concrete classes is clearly evidenced in the code.
