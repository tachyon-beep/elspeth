# Analysis: src/elspeth/plugins/llm/azure_multi_query.py

**Lines:** 1,089
**Role:** Azure OpenAI multi-query LLM transform. Executes multiple LLM queries per row (case_studies x criteria cross-product), merges all results into a single output row with all-or-nothing error semantics. Uses `BatchTransformMixin` for row-level pipelining and `PooledExecutor` for query-level concurrency within each row.
**Key dependencies:**
- Imports from: `contracts` (TransformResult, propagate_contract, etc.), `plugins.base` (BaseTransform), `plugins.batching` (BatchTransformMixin, OutputPort), `plugins.clients.llm` (AuditedLLMClient, LLMClientError, RateLimitError), `plugins.llm.multi_query` (MultiQueryConfig, QuerySpec, ResponseFormat, etc.), `plugins.llm.templates` (PromptTemplate), `plugins.llm.tracing` (TracingConfig, LangfuseTracingConfig, etc.), `plugins.llm.validation` (validate_json_object_response), `plugins.pooling` (PooledExecutor, CapacityError)
- Imported by: Plugin discovery system, engine executors (via `transform.accept()` path)
- Sibling: `openrouter_multi_query.py` is the OpenRouter counterpart with HTTP-based communication

**Analysis depth:** FULL

## Summary

The file is well-structured and follows ELSPETH's trust tier model correctly at LLM response boundaries. However, there is one critical finding: the sequential execution path does not catch retryable `LLMClientError` exceptions, which will propagate uncaught and crash the pipeline for transient network/server errors. There are also several warnings around missing `transforms_adds_fields` flag, potential resource leaks, and inconsistency with the OpenRouter counterpart in Langfuse tracing granularity.

## Critical Findings

### [842-854] Sequential path does not catch retryable LLMClientError

**What:** In `_execute_queries_sequential()`, only `CapacityError` is caught. But `_process_single_query()` (line 442-443) re-raises retryable `LLMClientError` subclasses (`NetworkError`, `ServerError`) with the comment "Pool catches LLMClientError and applies AIMD retry." The sequential path has no pool -- these exceptions propagate uncaught.

**Why it matters:** When `pool_size=1` (or no pool configured), any transient network error or 5xx server error during a single query will crash the entire row processing. The `CapacityError` catch on line 845 only handles `RateLimitError` (which is converted to `CapacityError` on line 428). `NetworkError` and `ServerError` propagate through `_execute_queries_sequential()`, through `_process_single_row_internal()`, through `_process_row()`, and into the batch worker -- ultimately crashing the pipeline for what should be a recoverable per-row error.

**Evidence:**
```python
# _process_single_query line 440-443:
# Re-raise retryable errors (NetworkError, ServerError) - let pool retry
# Return error for non-retryable (ContentPolicyError, ContextLengthError)
if e.retryable:
    raise  # Pool catches LLMClientError and applies AIMD retry

# _execute_queries_sequential line 843-853:
try:
    result = self._process_single_query(row, spec, state_id, token_id)
except CapacityError as e:  # Only catches CapacityError, not LLMClientError!
    result = TransformResult.error(...)
```

The comment on line 440 says "Pool catches LLMClientError" but the sequential path is used precisely when there is no pool. The OpenRouter counterpart has the same bug at its line 1206-1217.

## Warnings

### [N/A] Missing `transforms_adds_fields = True` class attribute

**What:** The class does not set `transforms_adds_fields = True`, even though multi-query transforms add multiple output fields per row (score, rationale, usage, model, template metadata per query spec). The base class default is `False`.

**Why it matters:** The engine's `TransformExecutor.execute_transform()` (executors.py line 409) checks `transform.transforms_adds_fields` to decide whether to compute evolved contracts and record schema evolution to the audit trail. Without this flag, schema evolution is not recorded for the batch path via `execute_transform()`. However, the `_process_row()` method (line 657-664) manually calls `propagate_contract()` on success, so contracts are propagated correctly for the batch/accept path. The risk is that if the engine ever routes this transform through the non-batch `process()` path (which raises `NotImplementedError`), the flag discrepancy would not matter. The flag being `False` is inconsistent with the actual behavior -- the transform definitively adds fields. The OpenRouter counterpart also lacks this flag.

**Evidence:**
```python
# azure_multi_query.py class attributes (line 122-125):
name = "azure_multi_query_llm"
creates_tokens = False
determinism: Determinism = Determinism.NON_DETERMINISTIC
plugin_version = "1.0.0"
# transforms_adds_fields is missing -- inherits False from BaseTransform
```

### [726-732] Merge via `output.update(result.row)` assumes result.row is always a dict

**What:** In `_process_single_row_internal()`, the merge loop does `output.update(result.row)`. `TransformResult.row` has type `dict[str, Any] | PipelineRow | None`. The `if result.row is not None` guard handles the `None` case, but `PipelineRow` is not `dict` -- calling `.update()` with a `PipelineRow` argument would work only if `PipelineRow` implements the mapping protocol (which it does per CLAUDE.md). However, this is fragile: `_process_single_query()` returns `TransformResult.success(output, ...)` where `output` is always a plain `dict`, so in practice this always works. But the type contract allows `PipelineRow` and the code does not explicitly convert.

**Why it matters:** If a future refactor causes `_process_single_query()` to return a `PipelineRow` as the row, the `.update()` call would silently lose contract metadata without explicit conversion. This is a latent fragility, not a current bug.

**Evidence:**
```python
# Line 727-732:
for result in results:
    if result.row is not None:
        output.update(result.row)  # result.row could be PipelineRow per type contract
```

### [657-664] Dual contract propagation: _process_row and execute_transform

**What:** `_process_row()` manually calls `propagate_contract()` on successful results (line 660-664) and sets `result.contract`. The engine's `TransformExecutor.execute_transform()` also performs contract propagation when `transforms_adds_fields` is True (executors.py line 409-426). Since `transforms_adds_fields` is `False`, the executor path is skipped. This creates a hidden coupling: the correctness of contract propagation depends on the flag being `False`. If someone sets it to `True` to fix the flag omission (per the warning above), contracts would be propagated twice, potentially causing inconsistency.

**Why it matters:** The dual propagation paths create a maintenance hazard. If the flag is corrected to `True`, the executor would also propagate contracts, resulting in double propagation. The `_process_row()` propagation would set `result.contract`, then the executor would recompute from the token's input contract and set `update_node_output_contract`. This might produce slightly different results depending on timing and state.

**Evidence:**
```python
# _process_row line 657-664:
if result.status == "success" and result.row is not None:
    output_row = result.row.to_dict() if isinstance(result.row, PipelineRow) else result.row
    result.contract = propagate_contract(
        input_contract=input_contract,
        output_row=output_row,
        transform_adds_fields=True,
    )
```

### [209-216] Unbounded LLM client cache growth if _process_row cleanup is bypassed

**What:** `_llm_clients` is a dict keyed by `state_id`. Entries are created in `_get_llm_client()` (line 282-294) and cleaned up in `_process_row()`'s `finally` block (line 667-669). However, if `_get_llm_client()` is called outside `_process_row()` (e.g., during testing or if the call flow changes), clients accumulate without cleanup. Additionally, the `finally` block only cleans up `ctx.state_id` -- if an exception occurs before `_process_row()` is entered (e.g., in the batch mixin's `_process_and_complete()`), the client may not be cleaned up.

**Why it matters:** In long-running pipelines processing many rows, leaked `AuditedLLMClient` instances hold references to the `LandscapeRecorder` and underlying `AzureOpenAI` client. The `close()` method (line 954-955) clears all clients, but between close() and the leak, memory grows. The current architecture routes all calls through `_process_row()`, so this is a latent risk rather than an active leak.

**Evidence:**
```python
# Line 214-215:
self._llm_clients: dict[str, AuditedLLMClient] = {}
self._llm_clients_lock = Lock()

# Line 667-669 (cleanup only in _process_row finally):
finally:
    with self._llm_clients_lock:
        self._llm_clients.pop(ctx.state_id, None)
```

### [267-277] Single shared AzureOpenAI client across all concurrent queries

**What:** `_get_underlying_client()` creates a single `AzureOpenAI` instance shared across all concurrent LLM calls (multiple rows, multiple queries per row). The OpenAI Python SDK's `AzureOpenAI` client uses `httpx` internally and is documented as thread-safe, but this is a single connection pool serving all concurrent requests.

**Why it matters:** Under high concurrency (many rows in flight, each with N queries), the single `httpx` client's connection pool may become a bottleneck. The default `httpx` pool limits are 100 connections (10 per host), which could throttle throughput below what `pool_size` requests. This is not a correctness issue but a performance concern that may manifest as unexplained latency spikes in production under load.

**Evidence:**
```python
# Line 267-277:
def _get_underlying_client(self) -> AzureOpenAI:
    if self._underlying_client is None:
        from openai import AzureOpenAI
        self._underlying_client = AzureOpenAI(...)
    return self._underlying_client
```

## Observations

### [973-1034 vs OpenRouter counterpart] Langfuse tracing granularity inconsistency

**What:** The Azure multi-query records Langfuse traces at the individual query level (`_record_langfuse_trace` takes `query_prefix`, `prompt`, `response_content`), creating one span per LLM call. The OpenRouter counterpart records at the row level (`_record_langfuse_trace` takes `query_count`, `succeeded_count`, `total_usage`), creating one summary span per row. The error tracing methods (`_record_langfuse_trace_for_error`) are identical in both.

**Why it matters:** This means the same pipeline running on Azure vs OpenRouter will produce fundamentally different Langfuse trace structures. Users switching providers would get different observability. Neither approach is wrong, but the inconsistency may confuse users comparing traces across providers.

### [186-192] `_output_schema_config` uses `schema_config` for mode/fields but computed guaranteed/audit fields

**What:** The `_output_schema_config` is correctly built with computed `guaranteed_fields` and `audit_fields` from all query specs and output mappings. However, the `input_schema` and `output_schema` (lines 195-201) are both created from the base `schema_config` (not `_output_schema_config`). The `_output_schema_config` is only consumed by the DAG via `getattr(transform, "_output_schema_config", None)` for schema validation.

**Why it matters:** The `output_schema` does not reflect the actual output fields (which include all the query-specific fields). This is currently fine because the DAG uses `_output_schema_config` for validation, but the `output_schema` attribute is misleading -- it represents the input schema, not the true output schema.

### [879] Match statement catch-all pattern `"none" | _` is overly broad

**What:** The tracing setup match statement uses `case "none" | _:` which silently accepts any unknown provider string. A typo in the provider name (e.g., `"langfues"`) would be silently ignored.

**Why it matters:** Users could misconfigure tracing and never know it. The `validate_tracing_config()` function only validates required fields for known providers, not that the provider name itself is valid. A warning log for unrecognized provider would improve debuggability.

### [488] `response.content.strip()` could produce empty string for JSON parsing

**What:** If the LLM returns empty or whitespace-only content, `content` becomes `""` after `.strip()`. This is then passed to `validate_json_object_response("")` which correctly returns `ValidationError(reason="invalid_json")` via `json.loads("")`. This is handled correctly.

**Why it matters:** No issue -- this is an observation that the edge case is correctly handled.

### [154] `_on_error` stored but not obvious where it's consumed

**What:** The transform stores `self._on_error = cfg.on_error` (line 154), inheriting from `BaseTransform._on_error`. This is consumed by the engine's `TransformExecutor` when the transform returns `TransformResult.error()`. The engine reads `transform._on_error` to determine the error sink. The batch path goes through the executor, so this works correctly.

**Why it matters:** No issue for correctness. The indirect consumption pattern is documented in `executors.py` and `processor.py`.

### [195-201] Schema created from `schema_config` with `allow_coercion=False`

**What:** Schema is created with `allow_coercion=False`, which is correct per CLAUDE.md -- transforms are Tier 2 and must not coerce types. This is consistent with the trust model.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Fix the critical sequential path bug where retryable `LLMClientError` (NetworkError, ServerError) is not caught in `_execute_queries_sequential()`. This is a one-line fix (catch `LLMClientError` in addition to `CapacityError`). Also consider setting `transforms_adds_fields = True` and reconciling the dual contract propagation paths. The Langfuse tracing granularity inconsistency with the OpenRouter counterpart should be tracked for future alignment.
**Confidence:** HIGH -- The critical finding is verifiable by reading the exception flow: `_process_single_query` re-raises retryable `LLMClientError` on line 443, and `_execute_queries_sequential` only catches `CapacityError` on line 845. The sequential path is exercised when `pool_size` is not configured or is 1.
