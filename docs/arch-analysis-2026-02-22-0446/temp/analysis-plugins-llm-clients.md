# Architecture Analysis: LLM Plugins and Client Infrastructure

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Scope:** `plugins/llm/` (12 files), `plugins/clients/` (5 files)
**Total lines analyzed:** ~5,800 lines across 17 files

---

## File-by-File Analysis

### plugins/llm/base.py (417 lines)

**Purpose:** Abstract base class for single-query LLM transforms. Provides `LLMConfig` (Pydantic) and `BaseLLMTransform` (ABC).

**Key classes:**
- `LLMConfig(TransformDataConfig)` -- Pydantic model with LLM-specific fields (model, template, temperature, max_tokens, response_field) plus flat pool config fields assembled into `PoolConfig` via a property.
- `BaseLLMTransform(BaseTransform)` -- Abstract base. Subclasses implement `_get_llm_client(ctx)`. Provides `process()` with three-tier error handling: template rendering (wrap), LLM call (wrap), output assembly (let crash).

**Dependencies:** `contracts` (TransformResult, propagate_contract, SchemaContract, PipelineRow, PluginContext), `plugins.base` (BaseTransform), `plugins.clients.llm` (AuditedLLMClient, LLMClientError), `plugins.llm.templates` (PromptTemplate), `plugins.llm.__init__` (metadata field helpers), `plugins.schema_factory`, `plugins.config_base`, `plugins.pooling`.

**External call boundaries:** Template rendering wrapped in try/catch (TemplateError). LLM call wrapped in try/catch (LLMClientError). Retryable errors re-raised; non-retryable return `TransformResult.error()`.

**Concerns:**
- The `BaseLLMTransform` is used by *zero* production subclasses in this codebase. Neither `AzureLLMTransform` nor `OpenRouterLLMTransform` inherit from it -- they both inherit directly from `BaseTransform + BatchTransformMixin`. This base class exists only for potential future use or for external plugin authors (which ELSPETH explicitly says it does not support). **SEVERITY: MEDIUM** -- dead abstraction layer.
- The `process()` method does not support row-level pipelining (accept/emit pattern). Any subclass using this base will be limited to synchronous processing.

---

### plugins/llm/base_multi_query.py (712 lines)

**Purpose:** Abstract base class for multi-query LLM transforms. Provides shared cross-product (case_studies x criteria) evaluation pipeline.

**Key classes:**
- `BaseMultiQueryTransform(BaseTransform, BatchTransformMixin, ABC)` -- Two-layer concurrency: row-level pipelining (BatchTransformMixin) and query-level parallelism (PooledExecutor). Subclasses implement provider-specific `_process_single_query()`, `_get_rate_limiter_service_name()`, `_cleanup_clients()`, `_close_all_clients()`, `_setup_tracing()`.

**Dependencies:** `contracts` (TransformResult, propagate_contract, SchemaContract, PluginContext, TokenUsage, QueryFailureDetail, PoolExecutionContext), `plugins.base`, `plugins.batching`, `plugins.clients.llm`, `plugins.llm.multi_query`, `plugins.llm.templates`, `plugins.llm.tracing`, `plugins.pooling`, `plugins.schema_factory`.

**External call boundaries:** Delegated to subclass `_process_single_query()`. Sequential fallback wraps both `CapacityError` and `LLMClientError`.

**Concerns:**
- `_init_multi_query(cfg: Any)` accepts `Any` -- the cfg type is not constrained by a protocol or union type. Relies on convention.
- `_record_row_langfuse_trace()` accesses `result.row.get(...)` on what should be a `PipelineRow` -- this is safe because `PipelineRow` implements the mapping protocol, but the type signature says `TransformResult` which has `row: PipelineRow | None`.

---

### plugins/llm/azure.py (802 lines)

**Purpose:** Azure OpenAI LLM transform with row-level pipelining (single query per row).

**Key classes:**
- `AzureOpenAIConfig(LLMConfig)` -- Adds deployment_name, endpoint, api_key, api_version, tracing config.
- `AzureLLMTransform(BaseTransform, BatchTransformMixin)` -- Self-contained transform. Does NOT inherit from `BaseLLMTransform`. Uses accept/emit pattern via BatchTransformMixin.

**Dependencies:** Same as base.py plus `openai` (AzureOpenAI, TYPE_CHECKING), threading (Lock).

**External call boundaries:** Template rendering wrapped (TemplateError). LLM call wrapped (LLMClientError). Both Langfuse trace recording and error trace recording wrapped in try/except.

**Code duplication:**
- `__init__` duplicates ~80 lines of schema setup, field declaration, and metadata construction identical to `BaseLLMTransform.__init__`.
- `_process_row` duplicates the core template render -> build messages -> call LLM -> build output -> propagate contract sequence from `BaseLLMTransform.process()`.
- `_setup_tracing` / `_setup_langfuse_tracing` / `_record_langfuse_trace` / `_record_langfuse_trace_for_error` / `_flush_tracing` are duplicated nearly verbatim across azure.py, openrouter.py, azure_batch.py, openrouter_batch.py. **SEVERITY: HIGH** -- 5x copy of tracing boilerplate (~80 lines each = ~400 lines).
- `connect_output` / `accept` / `process` (raising NotImplementedError) are duplicated in azure.py, openrouter.py, and the base_multi_query hierarchy. **SEVERITY: MEDIUM** -- 3x copy.

**Concerns:**
- `_get_underlying_client()` and `_get_llm_client()` are identical in structure to `AzureMultiQueryLLMTransform` -- same thread-safe caching pattern repeated. **SEVERITY: MEDIUM**.
- `getattr(batch, "output_file_id", None)` and `getattr(batch, "error_file_id", None)` in `_check_batch_status` (line 782-783) -- uses `getattr` defensively on an external SDK object. This is legitimate Tier 3 boundary handling (SDK attribute availability varies by version).

---

### plugins/llm/azure_batch.py (1,416 lines)

**Purpose:** Azure OpenAI Batch API transform for high-volume 50% cost savings. Two-phase checkpoint approach (submit, then poll/complete).

**Key classes:**
- `AzureBatchConfig(TransformDataConfig)` -- Does NOT inherit from `LLMConfig`. Duplicates template, system_prompt, temperature, max_tokens, response_field fields. **SEVERITY: MEDIUM** -- should compose or inherit from LLMConfig.
- `AzureBatchLLMTransform(BaseTransform)` -- No BatchTransformMixin (batch-aware via `is_batch_aware = True` flag). Uses checkpoint-based crash recovery.

**Dependencies:** Same as azure.py plus `hashlib`, `io`, `json`, `uuid`, `datetime`, `contracts.batch_checkpoint`.

**External call boundaries:** Excellent Tier 3 handling:
- JSONL parsing: each line individually parsed, malformed lines recorded but processing continues.
- Response structure validation: explicit checks for `choices`, `message`, `content` structure before accessing.
- Error file: separately downloaded and parsed with same validation.
- All Azure API calls wrapped with audit recording (upload, batch create, batch retrieve, file download).

**Code duplication:**
- Schema setup (~30 lines) duplicated from other transforms.
- `_setup_tracing` / `_setup_langfuse_tracing` / `_flush_tracing` duplicated (~60 lines).
- `populate_llm_metadata_fields` call pattern duplicated.

**Concerns:**
- `hasattr(batch, "errors")` on line 833 -- defensive check on SDK object. Marked with comment "Tier 3: SDK errors attr is optional". This is borderline; the comment justifies it.
- At 1,416 lines, this is the largest file in the LLM subsystem. The `_download_results` method alone is ~400 lines.
- `_process_single` wraps single row in list and delegates to `_process_batch` -- adds unnecessary overhead but maintains consistency.

---

### plugins/llm/azure_multi_query.py (612 lines)

**Purpose:** Azure multi-query LLM transform (case_studies x criteria per row).

**Key classes:**
- `AzureMultiQueryLLMTransform(BaseMultiQueryTransform)` -- Inherits row pipeline and query concurrency from base. Implements Azure-specific client management and tracing.

**Dependencies:** Same as azure.py plus `base_multi_query`, `multi_query`, `validation`.

**External call boundaries:** Good Tier 3 handling:
- Response truncation detection via `finish_reason` (authoritative) and token count heuristic (fallback).
- JSON response validation via `validate_json_object_response()` (shared utility).
- Output field type validation via `_validate_field_type()` (inherited from base).
- Code fence stripping for standard response format.

**Code duplication:**
- `_get_underlying_client()` / `_get_llm_client()` -- identical pattern to azure.py (~40 lines).
- `_setup_azure_ai_tracing` / `_setup_langfuse_tracing` / `_record_langfuse_trace` / `_record_langfuse_trace_for_error` -- near-verbatim copies (~120 lines).
- `_process_single_query` is ~260 lines. The JSON parsing and validation section (steps 6-8) is very similar to `openrouter_multi_query._process_single_query` but uses `validate_json_object_response()` while OpenRouter does inline `json.loads()`. **SEVERITY: HIGH** -- inconsistent validation approach between Azure and OpenRouter multi-query.

---

### plugins/llm/openrouter.py (755 lines)

**Purpose:** OpenRouter LLM transform with row-level pipelining (single query per row).

**Key classes:**
- `OpenRouterConfig(LLMConfig)` -- Adds api_key, base_url, timeout_seconds, tracing config.
- `OpenRouterLLMTransform(BaseTransform, BatchTransformMixin)` -- Uses HTTP client (AuditedHTTPClient) instead of SDK-based AuditedLLMClient.

**Dependencies:** Same as base.py plus `httpx`, `json`, `math`, `plugins.clients.http` (AuditedHTTPClient), `plugins.llm.validation` (_reject_nonfinite_constant).

**External call boundaries:** Good Tier 3 handling:
- JSON parsing with `_reject_nonfinite_constant` via `json.loads(parse_constant=...)`.
- Response structure validation: checks `choices`, `message.content`.
- Null content check (content filtering detection).
- NaN/Infinity rejection on usage values.
- `response.raise_for_status()` then classification: 429 -> RateLimitError, 5xx -> ServerError, 4xx -> TransformResult.error, RequestError -> NetworkError.

**Code duplication:**
- Init boilerplate (~60 lines schema setup) duplicated.
- `connect_output` / `accept` / `process` (NotImplementedError) duplicated.
- `_setup_tracing` / `_setup_langfuse_tracing` / `_record_langfuse_trace` / `_record_langfuse_trace_for_error` / `_flush_tracing` duplicated (~120 lines).
- Response parsing logic (JSON parse -> extract choices -> extract content -> null check -> usage extraction) is very similar to `openrouter_batch._process_single_row` but subtly different.

**Concerns:**
- `self.output_schema = schema` (line 167) -- sets output_schema to the INPUT schema, unlike azure.py which uses `_build_augmented_output_schema()`. **SEVERITY: MEDIUM** -- inconsistency that could cause DAG validation issues.

---

### plugins/llm/openrouter_batch.py (839 lines)

**Purpose:** OpenRouter batch transform using synchronous parallel HTTP requests (ThreadPoolExecutor). Unlike azure_batch.py which uses Azure's async batch API.

**Key classes:**
- `_RowOutcome` -- Internal frozen dataclass for per-row success/failure (avoids field name collision with user data).
- `OpenRouterBatchConfig(LLMConfig)` -- Mirrors OpenRouterConfig.
- `OpenRouterBatchLLMTransform(BaseTransform)` -- `is_batch_aware = True`. Uses `ThreadPoolExecutor` for parallelism.

**Dependencies:** Same as openrouter.py plus `concurrent.futures`.

**External call boundaries:** Adequate:
- JSON parsing via `response.json()` (does NOT use `_reject_nonfinite_constant`). **SEVERITY: MEDIUM** -- inconsistent with openrouter.py which rejects NaN/Infinity.
- Response structure validation: checks dict type, choices, message.content.
- Template errors recorded to audit trail via `ctx.record_call()`.
- StreamError caught at batch level and recorded to audit trail.

**Code duplication:**
- Init boilerplate duplicated.
- Tracing boilerplate duplicated.
- Response parsing (~40 lines) nearly identical to openrouter.py.
- _process_single_row has the same render -> build messages -> HTTP call -> parse JSON -> extract content -> build output pattern.

---

### plugins/llm/openrouter_multi_query.py (522 lines)

**Purpose:** OpenRouter multi-query transform (case_studies x criteria per row via HTTP).

**Key classes:**
- `OpenRouterMultiQueryConfig(OpenRouterConfig, MultiQueryConfigMixin)` -- Composition via multiple inheritance.
- `OpenRouterMultiQueryLLMTransform(BaseMultiQueryTransform)` -- HTTP-based multi-query.

**Dependencies:** Same as openrouter.py plus `base_multi_query`, `multi_query`.

**External call boundaries:** Adequate:
- JSON parsing via `json.loads(content_str, parse_constant=_reject_nonfinite_constant)` -- correctly rejects NaN/Infinity.
- Explicit null content check and type validation (`isinstance(content, str)`).
- Manual response structure validation (choices, message, content).
- Output field type validation via inherited `_validate_field_type()`.

**Code duplication:**
- `_process_single_query` is ~280 lines. Steps 6-10 (HTTP call, parse, validate, map) are nearly identical to the Azure variant but with HTTP-specific error handling. **SEVERITY: HIGH**.
- `_setup_tracing` / `_setup_langfuse_tracing` duplicated.
- `_get_http_client` pattern identical to openrouter.py and openrouter_batch.py.

**Concerns:**
- Does NOT check `finish_reason` for truncation detection (unlike Azure multi-query which has authoritative finish_reason check). Uses only token count heuristic. **SEVERITY: LOW** -- OpenRouter may not reliably provide finish_reason, but the inconsistency should be documented.

---

### plugins/llm/multi_query.py (418 lines)

**Purpose:** Multi-query configuration models, QuerySpec dataclass, and key collision validation.

**Key classes:**
- `OutputFieldType(StrEnum)` -- STRING, INTEGER, NUMBER, BOOLEAN, ENUM.
- `ResponseFormat(StrEnum)` -- STANDARD (json_object), STRUCTURED (json_schema).
- `OutputFieldConfig(PluginConfig)` -- Single output field config with type and optional enum values.
- `QuerySpec` -- Dataclass for one (case_study, criterion) pair. Includes `build_template_context()`.
- `CaseStudyConfig(PluginConfig)` -- Case study definition.
- `CriterionConfig(PluginConfig)` -- Criterion definition with optional per-criterion max_tokens.
- `MultiQueryConfigMixin(PluginConfig)` -- Mixin with case_studies, criteria, output_mapping, response_format. Provides `expand_queries()`, `build_json_schema()`, `build_response_format()`.
- `MultiQueryConfig(AzureOpenAIConfig, MultiQueryConfigMixin)` -- Azure-specific multi-query config.
- `validate_multi_query_key_collisions()` -- Standalone validation function for cross-product collision detection.

**Dependencies:** `contracts.schema_contract` (PipelineRow), `plugins.config_base` (PluginConfig), `plugins.llm.azure` (AzureOpenAIConfig).

**Concerns:**
- `MultiQueryConfig` imports `AzureOpenAIConfig` directly, creating a hard dependency from the shared config module to the Azure-specific module. This means OpenRouter multi-query must work around it. **SEVERITY: LOW** -- the config hierarchy is functional but could be cleaner.
- `QuerySpec` is a regular (non-frozen) dataclass. Given ELSPETH's preference for frozen dataclasses at boundaries, this could be `frozen=True`. **SEVERITY: LOW**.

---

### plugins/llm/templates.py (253 lines)

**Purpose:** Jinja2 prompt templating with audit metadata (hashes for template, variables, rendered output, lookup data, and contract).

**Key classes:**
- `TemplateError(Exception)` -- Raised for all template rendering failures.
- `RenderedPrompt` -- Frozen dataclass with prompt string and all audit hashes.
- `PromptTemplate` -- Wraps Jinja2 `ImmutableSandboxedEnvironment` with `StrictUndefined`. Provides `render()` and `render_with_metadata()`.

**Dependencies:** `jinja2` (sandbox, StrictUndefined), `contracts.schema_contract` (PipelineRow, SchemaContract), `core.canonical` (canonical_json).

**External call boundaries:** N/A -- templates process internal data only. The sandbox prevents dangerous Jinja2 operations.

**Concerns:** None significant. Clean implementation. The sandbox is correctly configured. Hash computation uses canonical_json which correctly rejects NaN/Infinity.

---

### plugins/llm/tracing.py (179 lines)

**Purpose:** Configuration dataclasses for plugin-internal (Tier 2) tracing. Supports azure_ai, langfuse, and none providers.

**Key classes:**
- `TracingConfig` -- Base frozen dataclass with provider field.
- `AzureAITracingConfig(TracingConfig)` -- connection_string, enable_content_recording, enable_live_metrics.
- `LangfuseTracingConfig(TracingConfig)` -- public_key, secret_key, host, tracing_enabled.
- `parse_tracing_config()` -- Factory function from dict.
- `validate_tracing_config()` -- Returns list of error strings.

**Dependencies:** None external (pure Python dataclasses).

**Concerns:** None significant. Clean and minimal.

---

### plugins/llm/validation.py (80 lines)

**Purpose:** Shared LLM response validation utilities. Extracts common Tier 3 boundary validation pattern.

**Key classes/functions:**
- `_reject_nonfinite_constant()` -- Used as `parse_constant` for `json.loads()` to reject NaN/Infinity.
- `ValidationSuccess` / `ValidationError` -- Frozen dataclasses for parse results.
- `validate_json_object_response()` -- Parses JSON and verifies type is dict.

**Dependencies:** `json` only.

**Concerns:**
- Only used by `azure_multi_query.py`. The `openrouter_multi_query.py` does inline `json.loads()` + `isinstance` check instead of using this utility. **SEVERITY: MEDIUM** -- missed consolidation opportunity.

---

### plugins/clients/base.py (115 lines)

**Purpose:** Abstract base for audited clients. Provides recorder reference, state_id, run_id, telemetry emit callback, rate limiter, call index allocation.

**Key classes:**
- `AuditedClientBase` -- Base with `_next_call_index()` (thread-safe, delegated to LandscapeRecorder), `_acquire_rate_limit()`, and common fields.

**Dependencies:** `contracts.events` (ExternalCallCompleted), `core.landscape.recorder` (LandscapeRecorder), `core.rate_limit` (TYPE_CHECKING).

**Concerns:** None. Clean minimal base class with well-documented thread safety.

---

### plugins/clients/http.py (988 lines)

**Purpose:** Audited HTTP client wrapping httpx with automatic call recording, header fingerprinting, SSRF-safe requests, and redirect handling.

**Key classes:**
- `AuditedHTTPClient(AuditedClientBase)` -- Full HTTP client with `post()`, `get()`, `get_ssrf_safe()`. Automatic audit recording via `_record_and_emit()`. HMAC fingerprinting for sensitive headers. SSRF-safe IP-pinned connections with per-hop redirect validation.

**Dependencies:** `httpx`, `contracts` (CallStatus, CallType, call_data DTOs, events), `core.canonical` (stable_hash), `core.security.web` (SSRF validation).

**External call boundaries:** Excellent:
- Response body parsed at Tier 3 boundary with NaN/Infinity rejection.
- Sensitive headers fingerprinted (never stored raw in audit trail).
- Each redirect hop independently SSRF-validated.
- Error and success paths both record to audit trail.

**Concerns:**
- `get_ssrf_safe` has significant code duplication with `_execute_request` (~100 lines of response parsing, recording, and telemetry emission). **SEVERITY: MEDIUM** -- could extract shared _record_response_and_emit method.
- The `_follow_redirects_safe` method is well-implemented but complex (100 lines). Acceptable given the security requirements.

---

### plugins/clients/llm.py (470 lines)

**Purpose:** Audited LLM client wrapping OpenAI-compatible SDK with automatic call recording, error classification, and telemetry.

**Key classes:**
- `LLMResponse` -- Dataclass with content, model, usage (TokenUsage), latency_ms, raw_response.
- Error hierarchy: `LLMClientError` (base), `RateLimitError`, `NetworkError`, `ServerError`, `ContentPolicyError`, `ContextLengthError` -- all with `retryable` flag.
- `_classify_llm_error()` -- Regex-based error classification from exception message strings.
- `AuditedLLMClient(AuditedClientBase)` -- Wraps `client.chat.completions.create()`. Records to audit trail. Emits telemetry.

**Dependencies:** `contracts` (CallStatus, CallType, call_data DTOs, events, TokenUsage), `core.canonical` (stable_hash).

**External call boundaries:** Good:
- SDK call wrapped in try/except.
- Error classification happens outside the try block (success path processing won't be misclassified as LLM error).
- `response.usage` guarded with `is not None` check (Tier 3: providers may omit usage).
- `response.choices[0].message.content or ""` -- handles None content.

**Concerns:**
- `LLMResponse` is a regular (non-frozen) dataclass. Per MEMORY.md, there are known open bugs about "untyped dict[str, Any] crossing into audit trail from plugin clients". The `raw_response: dict[str, Any] | None` field is one such boundary. **SEVERITY: MEDIUM** -- known issue, tracked.
- `_classify_llm_error` uses regex pattern matching on error message strings, which is fragile and provider-specific. If a provider changes error message wording, classification may break. **SEVERITY: LOW** -- pragmatic approach, no great alternative.

---

### plugins/clients/replayer.py (257 lines)

**Purpose:** Replay mode support. Returns previously recorded responses from the audit trail instead of making live calls. Matches by `request_hash` (canonical hash of request data).

**Key classes:**
- `ReplayedCall` -- Dataclass with response_data, original_latency_ms, request_hash, was_error, error_data.
- `ReplayMissError` -- No matching recorded call found.
- `ReplayPayloadMissingError` -- Call exists but payload purged.
- `CallReplayer` -- Caches replayed calls in memory. Supports sequence indexing for repeated identical requests.

**Dependencies:** `contracts` (CallStatus), `core.canonical` (stable_hash).

**Concerns:**
- Thread safety: documented as requiring external synchronization. This is appropriate for the current usage pattern.
- `json.loads(call.error_json)` on line 207 -- this is Tier 1 data (our audit trail), so no defensive wrapping needed. Correct.

---

### plugins/clients/verifier.py (321 lines)

**Purpose:** Verify mode support. Makes live calls and compares against recorded baseline using DeepDiff. Detects API drift.

**Key classes:**
- `VerificationResult` -- Dataclass with live_response, recorded_response, is_match, differences.
- `VerificationReport` -- Aggregate statistics (matches, mismatches, missing_recordings, missing_payloads, success_rate).
- `CallVerifier` -- Compares live responses against recorded baseline with configurable ignore_paths and ignore_order.

**Dependencies:** `deepdiff` (DeepDiff), `core.canonical` (stable_hash).

**External call boundaries:** N/A -- verifier receives already-made responses, does not make calls itself.

**Concerns:**
- Hash-based verification when payload is purged (lines 231-253) is a good design -- "hashes survive payload deletion" per CLAUDE.md. Well-implemented.
- Thread safety same caveat as replayer.

---

## Overall Analysis

### 1. LLM Architecture: Base -> Provider Hierarchy

The hierarchy has an interesting disconnect:

```
BaseLLMTransform (abstract, single-query)
  |-- (no production subclasses)

BaseMultiQueryTransform (abstract, multi-query, BatchTransformMixin)
  |-- AzureMultiQueryLLMTransform
  |-- OpenRouterMultiQueryLLMTransform

BaseTransform + BatchTransformMixin (direct composition)
  |-- AzureLLMTransform
  |-- OpenRouterLLMTransform

BaseTransform (direct)
  |-- AzureBatchLLMTransform
  |-- OpenRouterBatchLLMTransform
```

`BaseLLMTransform` is an orphan -- it provides `process()` but all production transforms use the accept/emit pattern via `BatchTransformMixin` instead. The base class exists but has no concrete subclasses, making it dead code.

`BaseMultiQueryTransform` is well-designed and properly used by both Azure and OpenRouter multi-query variants. It correctly abstracts the shared pipeline while delegating provider-specific concerns.

The single-query transforms (azure.py, openrouter.py) do NOT share a base class despite having ~80% identical code structure. They both independently compose `BaseTransform + BatchTransformMixin`.

**Assessment:** The multi-query hierarchy is well-layered. The single-query hierarchy is not layered at all -- it is copy-paste. `BaseLLMTransform` exists but is unused.

### 2. Multi-Query Pattern

Multi-query works as a cross-product evaluation:
1. Configuration defines `case_studies` (each with `input_fields`) and `criteria` (each with optional `max_tokens`).
2. `MultiQueryConfigMixin.expand_queries()` produces `list[QuerySpec]` -- one per (case_study, criterion) pair.
3. `BaseMultiQueryTransform._process_row()` iterates all queries (parallel via PooledExecutor or sequential fallback).
4. Each query: build synthetic template context -> render prompt -> call LLM -> parse JSON -> validate types -> map to output fields.
5. All-or-nothing semantics: if any query fails, the entire row fails.
6. Results merged into single output row with prefixed field names.

Template-based: yes, uses `PromptTemplate` (Jinja2) with `{{ input_1 }}`, `{{ criterion.name }}`, `{{ lookup.data }}` namespaces.

Duplication: moderate. The `_process_single_query` implementations differ in:
- Azure uses `AuditedLLMClient.chat_completion()` (SDK-based)
- OpenRouter uses `AuditedHTTPClient.post()` (HTTP-based)
- Azure uses `validate_json_object_response()` (shared utility)
- OpenRouter does inline `json.loads()` + `isinstance` check

The response parsing and field mapping sections are near-identical (~80 lines each).

### 3. Azure vs OpenRouter: Shared vs Duplicated

**Shared code (via BaseMultiQueryTransform):**
- Row processing pipeline
- Query expansion
- Sequential/parallel execution
- Result merging
- Field type validation
- Schema construction
- Batch processing lifecycle

**Duplicated code (copy-paste across providers):**

| Component | Azure files | OpenRouter files | Lines duplicated (est.) |
|-----------|------------|-----------------|------------------------|
| Schema setup in `__init__` | azure.py, azure_batch.py, azure_multi_query.py | openrouter.py, openrouter_batch.py, openrouter_multi_query.py | ~180 (6x30) |
| Langfuse setup | azure.py, azure_batch.py, azure_multi_query.py | openrouter.py, openrouter_batch.py, openrouter_multi_query.py | ~360 (6x60) |
| Langfuse trace recording | azure.py, azure_multi_query.py | openrouter.py, openrouter_multi_query.py | ~240 (4x60) |
| Langfuse error recording | azure.py, azure_multi_query.py | openrouter.py | ~180 (3x60) |
| Flush tracing | all 6 files | - | ~60 (6x10) |
| connect_output / accept | azure.py | openrouter.py | ~40 (2x20) |
| Client caching pattern | azure.py, azure_multi_query.py | openrouter.py, openrouter_batch.py, openrouter_multi_query.py | ~150 (5x30) |
| Response parsing (HTTP) | - | openrouter.py, openrouter_batch.py, openrouter_multi_query.py | ~120 (3x40) |
| **Total estimated** | | | **~1,330 lines** |

This aligns with MEMORY.md's note: "LLM plugin duplication (~6 files with shared logic)".

### 4. Batch Processing

Two distinct batch paradigms:

**Azure Batch (`azure_batch.py`):** Asynchronous. Uses Azure's Batch API:
1. Render all templates, build JSONL, upload, submit batch -> checkpoint batch_id.
2. Raise `BatchPendingError`. Engine schedules retry.
3. On resume: check Azure batch status -> download results when complete.
4. Crash recovery via frozen `BatchCheckpointState` dataclass.

**OpenRouter Batch (`openrouter_batch.py`):** Synchronous parallel. Uses `ThreadPoolExecutor`:
1. Submit all rows to thread pool.
2. Each worker makes HTTP request to OpenRouter.
3. Collect results, assemble output.
4. No checkpointing needed (completes in one call).

Both use `is_batch_aware = True` flag, receiving `list[PipelineRow]` from the engine's aggregation flush.

### 5. Client Architecture

```
AuditedClientBase
  |-- AuditedHTTPClient (httpx-based, HTTP calls)
  |-- AuditedLLMClient (OpenAI SDK-based, LLM calls)
```

Good abstraction:
- Base provides: recorder reference, state_id, run_id, telemetry, rate limiting, call index allocation.
- `AuditedHTTPClient`: Full HTTP with SSRF protection, header fingerprinting, redirect handling, response body parsing.
- `AuditedLLMClient`: OpenAI SDK wrapper with error classification, retryable/non-retryable distinction.

The split between HTTP and LLM clients maps cleanly to the Azure (SDK) vs OpenRouter (HTTP) distinction.

`CallReplayer` and `CallVerifier` sit alongside these but serve different purposes (replay/verify modes). They interact with the LandscapeRecorder directly rather than inheriting from `AuditedClientBase`.

### 6. Replayer/Verifier

**CallReplayer:** Supports replay mode. Matches by `request_hash`. Supports sequence indexing (Nth occurrence of same request). Caches in memory. Raises `ReplayMissError` or `ReplayPayloadMissingError` on failure.

**CallVerifier:** Supports verify mode. Makes live calls, then compares against recorded baseline using DeepDiff. Supports configurable ignore_paths (for fields like latency that naturally vary). Produces `VerificationReport` with aggregate statistics. Falls back to hash-based comparison when payload is purged.

Both support the ELSPETH principle: "hashes survive payload deletion."

### 7. Template System

Jinja2-based via `ImmutableSandboxedEnvironment`:
- `StrictUndefined`: missing variables raise errors (no silent empty string).
- Sandboxed: prevents dangerous operations.
- Namespaced: `{{ row.field }}`, `{{ lookup.key }}`.
- Audit metadata: SHA-256 hashes for template, variables, rendered output, lookup data, contract.
- Dual-name access: when `SchemaContract` is provided, templates can use original field names (pre-normalization).
- `extract_jinja2_fields()` (in `core/templates.py`, not analyzed here) discovers template dependencies at config time for DAG validation.

### 8. Trust Tier Compliance

**Azure single-query (azure.py):** Compliant. LLM call wrapped. Template rendering wrapped. Output assembly unwrapped (our code).

**Azure batch (azure_batch.py):** Excellent compliance. JSONL response parsing has thorough boundary validation. Every Azure API call recorded to audit trail.

**Azure multi-query (azure_multi_query.py):** Good. Uses `validate_json_object_response()` (shared utility). Finish_reason + token count heuristic for truncation. Type validation on parsed fields.

**OpenRouter single-query (openrouter.py):** Good. `json.loads(parse_constant=_reject_nonfinite_constant)`. Null content check. NaN/Infinity check on usage values.

**OpenRouter batch (openrouter_batch.py):** PARTIALLY COMPLIANT. Uses `response.json()` instead of `json.loads(parse_constant=_reject_nonfinite_constant)`. Does not reject NaN/Infinity in response JSON. **SEVERITY: MEDIUM**.

**OpenRouter multi-query (openrouter_multi_query.py):** Good. Uses `_reject_nonfinite_constant`. Explicit null content and type checks.

**Summary:** 5/6 transforms have good Tier 3 compliance. `openrouter_batch.py` is the outlier.

### 9. Tracing

Tier 2 (plugin-internal) tracing supports two providers:
- **Azure AI / Application Insights:** Auto-instruments OpenAI SDK. Process-level. Only works with Azure SDK (not HTTP).
- **Langfuse v3:** Manual spans via context managers. Per-instance clients. Works with both SDK and HTTP.

Each transform independently initializes its own tracing. The configuration parsing (`parse_tracing_config`, `validate_tracing_config`) is shared from `tracing.py`, but the setup and recording methods are duplicated in every transform.

### 10. Known Issues

**From MEMORY.md:**
1. "LLM plugin duplication (~6 files with shared logic)" -- CONFIRMED. Estimated ~1,330 duplicated lines across schema setup, tracing, client caching, and response parsing.
2. "Untyped dicts at Tier 1 boundary" -- CONFIRMED. `LLMResponse.raw_response: dict[str, Any]`, `populate_llm_metadata_fields` writes `usage.to_dict()` (returns dict), error reasons are `dict[str, Any]`.

**New findings:**
3. `BaseLLMTransform` has zero production subclasses -- orphaned abstraction.
4. `openrouter_batch.py` does not reject NaN/Infinity in JSON responses.
5. `openrouter.py` does not use `_build_augmented_output_schema()` for output_schema -- inconsistency.
6. Azure multi-query checks `finish_reason` for truncation; OpenRouter multi-query does not.
7. Azure multi-query uses `validate_json_object_response()`; OpenRouter multi-query does inline parsing -- inconsistent validation approach.

---

## Concerns and Recommendations (Ranked by Severity)

### CRITICAL -- None

No data corruption, security, or audit integrity issues found. The codebase handles Tier 3 boundaries correctly in most cases.

### HIGH

**H1. Massive Code Duplication (~1,330 lines)**
- **Files:** All 6 provider-specific LLM transform files.
- **Pattern:** Schema setup, Langfuse tracing (setup/record/flush), client caching, connect_output/accept/process boilerplate, response parsing.
- **Risk:** Divergence bugs. Already manifesting: openrouter_batch.py missing NaN/Infinity rejection (H2), openrouter.py missing augmented output schema (H3), inconsistent validation approaches (H4).
- **Recommendation:** Extract shared functionality into mixins or composition helpers:
  1. `LLMTracingMixin` -- _setup_tracing, _setup_langfuse_tracing, _record_langfuse_trace, _record_langfuse_trace_for_error, _flush_tracing (~120 lines saved per consumer, ~600 total).
  2. `LLMSchemaSetupMixin` -- schema construction, declared_output_fields, _output_schema_config (~30 lines saved per consumer, ~180 total).
  3. `AzureClientMixin` / `OpenRouterClientMixin` -- _get_underlying_client, _get_llm_client / _get_http_client (~30 lines saved per consumer, ~150 total).
  4. Consider making `BaseLLMTransform` actually useful by incorporating `BatchTransformMixin` support.

**H2. Inconsistent NaN/Infinity Rejection in openrouter_batch.py**
- **File:** `/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter_batch.py`, line 740.
- **Pattern:** Uses `response.json()` instead of `json.loads(text, parse_constant=_reject_nonfinite_constant)`.
- **Risk:** NaN or Infinity values in OpenRouter response JSON could enter the pipeline, violating the canonical JSON contract and potentially corrupting the audit trail.
- **Recommendation:** Replace `response.json()` with `json.loads(response.text, parse_constant=_reject_nonfinite_constant)`.

**H3. Inconsistent Output Schema in openrouter.py**
- **File:** `/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter.py`, line 167.
- **Pattern:** `self.output_schema = schema` (same as input schema) instead of `_build_augmented_output_schema()`.
- **Risk:** DAG validation may fail for explicit-schema pipelines where downstream transforms require LLM output fields.
- **Recommendation:** Use `_build_augmented_output_schema()` as in azure.py and other transforms.

**H4. Inconsistent Response Validation Between Azure and OpenRouter Multi-Query**
- **Files:** `azure_multi_query.py` uses `validate_json_object_response()`, `openrouter_multi_query.py` uses inline `json.loads()` + `isinstance` check.
- **Risk:** Subtle behavioral differences in edge cases (e.g., error detail messages differ).
- **Recommendation:** Both should use `validate_json_object_response()`.

### MEDIUM

**M1. `BaseLLMTransform` is Orphaned**
- **File:** `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py`
- **Pattern:** Abstract base class with zero production subclasses. All single-query transforms use `BaseTransform + BatchTransformMixin` directly.
- **Recommendation:** Either evolve `BaseLLMTransform` to support the accept/emit pattern (making it useful for azure.py and openrouter.py), or delete it per "No Legacy Code Policy."

**M2. `AzureBatchConfig` Does Not Inherit from `LLMConfig`**
- **File:** `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure_batch.py`, line 53.
- **Pattern:** Inherits from `TransformDataConfig` and redeclares template, system_prompt, temperature, max_tokens, response_field.
- **Recommendation:** Inherit from `LLMConfig` or extract shared LLM fields into a mixin.

**M3. `_init_multi_query()` Accepts `Any`**
- **File:** `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base_multi_query.py`, line 70.
- **Pattern:** No type constraint on cfg parameter.
- **Recommendation:** Define a `Protocol` for the expected cfg interface.

**M4. Thread Safety Documentation Gap for Tracing**
- Multiple transforms store `self._langfuse_client` and call it from worker threads without explicit synchronization.
- Langfuse client may or may not be thread-safe -- this should be documented.

**M5. `LLMResponse` and Error Dicts Cross Tier 1 Boundary as Untyped Dicts**
- Already tracked in MEMORY.md. The `raw_response: dict[str, Any]` and `usage.to_dict()` patterns allow untyped data to flow into the audit trail.
- **Recommendation:** Replace with frozen dataclasses as per existing bug pattern.

### LOW

**L1. `QuerySpec` is not frozen** -- `/home/john/elspeth-rapid/src/elspeth/plugins/llm/multi_query.py`, line 74.

**L2. Missing finish_reason check in OpenRouter multi-query** -- Token count heuristic may be less accurate.

**L3. `MultiQueryConfig` creates hard dependency from multi_query.py -> azure.py** -- Could use a provider-agnostic base config.

---

## Confidence: HIGH

All 17 files were read in full. All cross-references were traced. The duplication analysis is based on direct comparison of code structure and content. The trust tier compliance assessment is based on checking every external call boundary in every file against CLAUDE.md's rules.

The one area of uncertainty is Langfuse v3 thread safety -- this depends on the Langfuse SDK's internal implementation which was not reviewed.
