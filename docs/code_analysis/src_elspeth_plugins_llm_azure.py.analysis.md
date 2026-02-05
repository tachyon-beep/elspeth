# Analysis: src/elspeth/plugins/llm/azure.py

**Lines:** 759
**Role:** Azure OpenAI single-query LLM transform. Sends one prompt per row to Azure OpenAI via the OpenAI SDK, records results to the audit trail via `AuditedLLMClient`, and optionally records traces to Langfuse or Azure Monitor. Uses `BatchTransformMixin` for concurrent row processing with FIFO output ordering.
**Key dependencies:** Imports `LLMConfig` from `base.py`, `AuditedLLMClient`/`LLMClientError` from `plugins.clients.llm`, `BatchTransformMixin`/`OutputPort` from `plugins.batching`, `PromptTemplate`/`TemplateError` from `plugins.llm.templates`, tracing types from `plugins.llm.tracing`. Imported by the plugin manager for registration.
**Analysis depth:** FULL

## Summary

The file is well-organized and follows the Three-Tier Trust Model correctly for the core processing path. Error handling boundaries are clearly defined: template rendering (Tier 2/row data) and LLM calls (Tier 3/external) are wrapped; internal logic crashes on bugs. There is one critical finding related to a race condition in `_get_underlying_client()`, one warning about missing contract passthrough to templates, and several observations about structural duplication. The Langfuse tracing integration is thorough with proper "No Silent Failures" telemetry emission on trace recording errors.

## Critical Findings

### [C1: LINE 519-533] Race condition in _get_underlying_client() - not thread-safe

**What:** The `_get_underlying_client()` method uses a check-then-act pattern (`if self._underlying_client is None`) without any locking. In the concurrent processing model (`BatchTransformMixin` runs multiple worker threads), multiple threads can execute this method simultaneously.

**Why it matters:** Multiple threads could simultaneously see `self._underlying_client is None`, each create a new `AzureOpenAI` instance, and then write to the same field. The last writer wins and the others are discarded (garbage collected). While the `AzureOpenAI` client is reportedly stateless and this likely produces correct results, there are real risks:
1. **Resource waste:** Multiple `AzureOpenAI` instances are created during initialization, each potentially establishing connection pools or performing network operations.
2. **Hidden connection pool fragmentation:** If the OpenAI SDK maintains internal connection pools, some worker threads may end up using a client instance that is immediately discarded, potentially causing connection errors.
3. **Inconsistent behavior:** Different threads may briefly use different client instances before the field settles.

**Evidence:**
```python
def _get_underlying_client(self) -> AzureOpenAI:
    # No lock! Multiple threads from BatchTransformMixin's ThreadPoolExecutor
    # can enter this simultaneously
    if self._underlying_client is None:
        from openai import AzureOpenAI
        self._underlying_client = AzureOpenAI(...)  # Race: multiple instances created
    return self._underlying_client
```

Compare with `_get_llm_client()` at line 535 which correctly uses `self._llm_clients_lock`. The underlying client should similarly be protected. This is a straightforward fix (use `_llm_clients_lock` or a dedicated lock) but the race exists in production code that runs with concurrent workers.

## Warnings

### [W1: LINE 419] Template rendering does not pass schema contract for dual-name resolution

**What:** The `_process_row()` method calls `self._template.render_with_metadata(row_data)` without passing `contract=row.contract`. The base class `BaseLLMTransform.process()` (base.py line 304) passes the contract, enabling templates to use original header names like `{{ row["Amount USD"] }}`.

**Why it matters:** Users who configure templates with original header names (which is a documented feature of the template system) will get `TemplateError: Undefined variable` errors at runtime. These errors would be correctly caught and returned as `TransformResult.error()`, so they won't crash the pipeline, but users would be confused since the same template pattern works in other contexts.

**Evidence:**
```python
# base.py line 304 (BaseLLMTransform.process):
rendered = self._template.render_with_metadata(row_data, contract=input_contract)

# azure.py line 419 (AzureLLMTransform._process_row):
rendered = self._template.render_with_metadata(row_data)  # No contract!
```

The `PipelineRow` is available at line 415 (`row`), and its contract is accessible via `row.contract`, but it is not passed through.

### [W2: LINE 65] API key stored as plain string attribute

**What:** `AzureOpenAIConfig` stores the API key as a plain string field (`api_key: str`), and `AzureLLMTransform.__init__()` stores it in `self._azure_api_key` (line 147). This string persists in memory for the lifetime of the transform.

**Why it matters:** While secrets in memory are a common reality for API clients, this means the API key is accessible via `transform._azure_api_key` and would appear in any memory dump, debug introspection, or error traceback that includes the transform's state. The ELSPETH security model uses HMAC fingerprinting for audit trail storage (which the `AuditedHTTPClient` implements for headers), but the transform itself holds the raw key. In a multi-tenant or shared-process scenario, this increases exposure surface.

**Evidence:**
```python
# Line 65 - stored as plain string
api_key: str = Field(..., description="Azure OpenAI API key")

# Line 147 - persisted on instance
self._azure_api_key = cfg.api_key
```

This is consistent with how the OpenAI SDK works (it requires the key to create clients), but it is worth noting for security review.

### [W3: LINE 514-517] Client cleanup in finally block may race with _get_llm_client on retry

**What:** The `finally` block in `_process_row()` cleans up the cached LLM client by popping the `state_id` from `self._llm_clients`. However, if the engine's RetryManager retries the same row (same `state_id`), the retry could call `_get_llm_client()` which would create a new client. This is intentional for call_index uniqueness, but the cleanup happens inside the same method that raised the exception.

**Why it matters:** When a retryable `LLMClientError` is raised at line 470-472, the exception propagates through `_process_and_complete()` in the `BatchTransformMixin`. The `finally` block at line 514-517 runs *before* the exception reaches the engine. This means:
1. The client for that `state_id` is removed from the cache.
2. The retry attempt will create a new `AuditedLLMClient` for the same `state_id`.
3. The new client starts with `call_index=0` (from the recorder's allocator, which IS centralized), so call_index uniqueness is actually maintained.

The concern is subtle: if the recorder's `allocate_call_index()` is properly centralized (which it appears to be from reading `base.py`), this is safe. But the cleanup pattern means every row creates and destroys an `AuditedLLMClient`, which is wasteful. The docstring says clients are "cached to preserve call_index across retries," but the `finally` block destroys this caching.

**Evidence:**
```python
# Line 514-517 - always runs, even on success
finally:
    with self._llm_clients_lock:
        self._llm_clients.pop(ctx.state_id, None)
```

This means the "cache" effectively has a lifetime of exactly one `_process_row()` call. The caching only matters if `_get_llm_client()` is called multiple times within a single `_process_row()` invocation, which it is not.

### [W4: LINE 75-80] Model validator mutates frozen-like field on Pydantic model

**What:** The `_set_model_from_deployment` model validator directly assigns `self.model = self.deployment_name`. While `LLMConfig` does not explicitly set `model_config = {"frozen": True}`, this mutation during validation is a common source of confusion.

**Why it matters:** If `LLMConfig` is ever made frozen (immutable), this validator will break. More importantly, the mutation happens after field validation, meaning `model` passes its own validator (empty string is valid since `Field(default="")`) and then is silently replaced. This is a Pydantic-sanctioned pattern for `mode="after"` validators, but it makes the config's `model` field unreliable for debugging until after full validation completes.

**Evidence:**
```python
@model_validator(mode="after")
def _set_model_from_deployment(self) -> Self:
    if not self.model:
        self.model = self.deployment_name  # Mutation in validator
    return self
```

### [W5: LINE 296-307] Azure AI tracing mutates process-level OpenTelemetry state

**What:** The `_setup_azure_ai_tracing()` method calls `configure_azure_monitor()` which is documented as "process-level configuration." Multiple plugins with azure_ai tracing will share the same configuration, and the first to initialize wins.

**Why it matters:** In a pipeline with multiple Azure LLM transforms (e.g., classification then enrichment), the second transform's tracing config is silently ignored. There is a warning log at line 303-307 when an existing OTEL tracer is detected, but no actual prevention. Additionally, if Tier 1 telemetry (the framework-level OTLP exporter) is configured, Azure AI tracing will conflict with it, potentially corrupting both.

**Evidence:**
```python
# Line 303-307: Warning only, no prevention
if otel_trace.get_tracer_provider().__class__.__name__ != "ProxyTracerProvider":
    logger.warning(
        "Existing OpenTelemetry tracer detected - Azure AI tracing may conflict with Tier 1 telemetry",
        ...
    )
# Proceeds to configure anyway at line 309
success = _configure_azure_monitor(tracing_config)
```

## Observations

### [O1: LINE 134-213] __init__ duplicates significant logic from BaseLLMTransform

**What:** `AzureLLMTransform.__init__()` duplicates the entire config parsing, template creation, schema creation, and output schema config building from `BaseLLMTransform.__init__()`. This is 50+ lines of identical logic.

**Why it matters:** Maintenance burden. See base.py analysis W2 for details.

### [O2: LINE 378-393] process() raises NotImplementedError as a redirect

**What:** The `process()` method is overridden to raise `NotImplementedError` with a message directing callers to use `accept()`. This is because the transform uses `BatchTransformMixin` for concurrent processing.

**Why it matters:** This breaks the `BaseTransform` contract where `process()` is the primary interface. The engine must know to call `accept()` instead. This is a design pattern shared with `OpenRouterLLMTransform` and presumably documented in the engine's executor code. It is not a bug but rather an architectural pattern that should be clearly documented for maintainers.

### [O3: LINE 200-208] Batch processing state deferred to connect_output

**What:** The batch processing infrastructure is not initialized in `__init__` but deferred to `connect_output()`. This means the transform exists in a partially initialized state between construction and output connection.

**Why it matters:** Calling `accept()` before `connect_output()` correctly raises `RuntimeError`, so the partial state is defended. However, it creates a two-phase initialization pattern that is not present in the base transform interface.

### [O4: LINE 449] Token ID fallback to "unknown"

**What:** `token_id = ctx.token.token_id if ctx.token else "unknown"` provides a fallback for when `ctx.token` is not set. However, the `accept_row()` method in `BatchTransformMixin` (mixin.py line 176) already validates that `ctx.token` is not None and raises `ValueError` if it is.

**Why it matters:** The `"unknown"` fallback is dead code in the normal flow. If execution reaches line 449, `ctx.token` is guaranteed to be set by the mixin's validation. The fallback could mask a bug if somehow `ctx.token` is set to None between `accept_row()` and the worker thread execution (e.g., if the PluginContext dataclass is mutated by another thread). Since `PluginContext` is a mutable dataclass shared across calls, this is theoretically possible but unlikely given the current engine design.

### [O5: LINE 639-680] Langfuse tracing records prompts in cleartext

**What:** The `_record_langfuse_trace()` method sends the full prompt and response content to Langfuse. While this is the expected behavior for LLM observability, it means prompt content (which may contain sensitive row data) is transmitted to an external service.

**Why it matters:** This is a data exfiltration vector if Langfuse is misconfigured or compromised. The decision to enable tracing should be made with awareness that all prompts and responses are sent to the tracing provider. The configuration model supports this (it's opt-in via the `tracing:` config section), but there is no warning to users that sensitive data will be transmitted.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Fix the race condition in `_get_underlying_client()` (C1) by adding lock protection consistent with `_get_llm_client()`. Evaluate whether the contract passthrough for dual-name template resolution (W1) is needed and either add it or document the intentional omission. Review the client caching pattern (W3) to determine if the `finally` cleanup is necessary given that call_index allocation is centralized.
**Confidence:** HIGH -- Full read of file plus all dependencies. The race condition is clearly present from the concurrent architecture. The contract passthrough gap is confirmed by comparing with base.py.
