# Analysis: src/elspeth/plugins/llm/openrouter_multi_query.py

**Lines:** 1,253
**Role:** OpenRouter multi-query LLM transform. Sends a cross-product of case studies x criteria as individual LLM queries per row to OpenRouter's HTTP API, merging all results into a single output row with all-or-nothing error semantics. Uses BatchTransformMixin for row-level pipelining and PooledExecutor for query-level concurrency.
**Key dependencies:**
- Imports: `OpenRouterConfig` (openrouter.py), `QuerySpec`/`CaseStudyConfig`/`CriterionConfig`/`OutputFieldConfig`/`OutputFieldType`/`ResponseFormat` (multi_query.py), `BatchTransformMixin`/`OutputPort` (batching), `AuditedHTTPClient` (clients/http.py), `PooledExecutor`/`CapacityError`/`is_capacity_error` (pooling), `PromptTemplate` (templates.py), tracing config types (tracing.py), `TransformResult`/`propagate_contract`/`PipelineRow` (contracts), `SchemaConfig` (contracts/schema.py)
- Imported by: Plugin discovery system via `PluginManager`
- Azure equivalent: `azure_multi_query.py` (same architecture, different transport)
**Analysis depth:** FULL

## Summary

This file has several concrete bugs that would cause production incidents, the most severe being a `NoneType` crash on content-filtered responses, missing per-criterion `max_tokens` propagation (silently ignored configuration), and missing output key collision validation. There are also multiple divergences from the Azure equivalent that break consistency guarantees, including the absence of the shared `validate_json_object_response()` utility and missing Langfuse error-path tracing. The core architecture (two-layer concurrency, all-or-nothing semantics, audit metadata) is sound, but the implementation has enough gaps to warrant NEEDS_REFACTOR status. Confidence is HIGH due to direct line-by-line comparison with the working Azure equivalent.

## Critical Findings

### [846] NoneType crash on content-filtered responses

**What:** Line 807 extracts `content = choices[0]["message"]["content"]`. OpenRouter returns `null` for `content` when a response is blocked by content filtering or other provider-specific reasons (e.g., `finish_reason: "content_filter"`). At line 846, `content.strip()` is called unconditionally. If `content` is `None`, this throws `AttributeError: 'NoneType' object has no attribute 'strip'`.

**Why it matters:** This is an unhandled crash on external data. Per the Three-Tier Trust Model, external API responses are Tier 3 (zero trust) and must be validated at the boundary. A content-filtered response would crash the worker thread rather than returning a proper `TransformResult.error()`. Since this runs in a `BatchTransformMixin` worker pool, the crash propagates as an `ExceptionResult`, killing the row and potentially triggering the "plugin bugs must crash" behavior rather than graceful quarantine. In production with content filtering enabled on the provider side, this would be triggered by any prompt that hits content safety limits.

**Evidence:**
```python
# Line 807 - content can be None from OpenRouter API
content = choices[0]["message"]["content"]

# Line 846 - unconditional .strip() on potentially None value
content_str = content.strip()  # AttributeError if content is None
```

The Azure equivalent avoids this because `response.content` from the OpenAI SDK is always a string (the SDK normalizes `null` to `""`).

### [169-189] Per-criterion max_tokens silently ignored

**What:** `OpenRouterMultiQueryConfig.expand_queries()` does not pass `max_tokens=criterion.max_tokens` to `QuerySpec`, while the Azure `MultiQueryConfig.expand_queries()` does (multi_query.py line 346). The `CriterionConfig` class has a `max_tokens` field (multi_query.py line 178), and `QuerySpec` has a `max_tokens` attribute (multi_query.py line 94), but the OpenRouter config never wires them together.

**Why it matters:** Users who configure per-criterion `max_tokens` overrides (e.g., short answers for classification, longer for rationale) will have their configuration silently validated by Pydantic but completely ignored at runtime. Every query will use the transform-level `max_tokens` default. This is exactly the "orphaned settings field" pattern described in CLAUDE.md (P2-2026-01-21). For an emergency dispatch system, a criterion that needs 2000 tokens for detailed triage reasoning would be truncated to the global default, potentially cutting off critical information.

**Evidence:**
```python
# OpenRouter (BUGGY) - line 179-186
spec = QuerySpec(
    case_study_name=case_study.name,
    criterion_name=criterion.name,
    input_fields=case_study.input_fields,
    output_prefix=f"{case_study.name}_{criterion.name}",
    criterion_data=criterion.to_template_data(),
    case_study_data=case_study.to_template_data(),
    # max_tokens NOT passed - silently defaults to None
)

# Azure (CORRECT) - multi_query.py line 339-348
spec = QuerySpec(
    ...
    max_tokens=criterion.max_tokens,  # Wired through
)
```

### [57-193] Missing output key collision validation

**What:** `OpenRouterMultiQueryConfig` does not have the `validate_no_output_key_collisions` model validator that exists in `MultiQueryConfig` (multi_query.py lines 245-288). This validator checks for: (1) duplicate case_study names, (2) duplicate criterion names, (3) output_mapping suffixes that collide with reserved LLM suffixes (`_usage`, `_model`, etc.).

**Why it matters:** Without this validation, a user could configure two case studies with the same name (e.g., both named "cs1"), resulting in output field collisions where the second query's results silently overwrite the first's. The all-or-nothing merge at line 1094-1100 (`output.update(result.row)`) would produce incorrect data in the audit trail -- the worst possible outcome per CLAUDE.md ("silently produces wrong results is worse than a crash"). For an emergency dispatch system, this means two different patient assessments could be conflated into one row, with one set of scores silently lost.

**Evidence:**
```python
# Azure MultiQueryConfig has this validator (multi_query.py lines 245-288)
@model_validator(mode="after")
def validate_no_output_key_collisions(self) -> MultiQueryConfig:
    # Checks duplicate case_study names, criterion names, reserved suffix collisions
    ...

# OpenRouterMultiQueryConfig - NO equivalent validator exists
class OpenRouterMultiQueryConfig(OpenRouterConfig):
    # Only has parse_output_mapping, build_json_schema, build_response_format, expand_queries
    # Missing: validate_no_output_key_collisions
```

## Warnings

### [758-779] Non-retryable network and server errors (inconsistent with single-query OpenRouter)

**What:** When `httpx.HTTPStatusError` with a non-capacity status code occurs (e.g., 500 Internal Server Error that isn't 503), the multi-query variant returns `retryable=False`. When `httpx.RequestError` occurs (connection timeout, DNS failure), it also returns `retryable=False`. The single-query OpenRouter variant (openrouter.py lines 564-584) raises `ServerError` for 500+ and `NetworkError` for connection errors, making them retryable by the engine's RetryManager.

**Why it matters:** Transient server failures (500) and network issues (timeouts, connection resets) that would be automatically retried in the single-query path are permanently failed in the multi-query path. In production, a momentary network blip would fail the entire row with all-or-nothing semantics, rather than retrying. The PooledExecutor only retries `CapacityError` (429/503/529), so 500 errors and network errors are not retried at all in the multi-query path.

**Evidence:**
```python
# Multi-query (non-retryable) - lines 771-779
except httpx.RequestError as e:
    return TransformResult.error(
        {"reason": "api_call_failed", "error": str(e), "query": spec.output_prefix},
        retryable=False,  # Network errors permanently fail!
    )

# Single-query (retryable) - openrouter.py line 584
except httpx.RequestError as e:
    raise NetworkError(f"Network error: {e}") from e  # Engine retries this
```

### [556-608] Dead code: `_record_langfuse_trace_for_error` defined but never called

**What:** The `_record_langfuse_trace_for_error` method is defined at line 556 but never invoked anywhere in the file. In the Azure multi-query equivalent, it is called at lines 421 and 432 when LLM API errors occur, ensuring failed attempts are visible in Langfuse for debugging. The OpenRouter multi-query variant's `_process_single_query` method does not call it for any error path (capacity errors, HTTP errors, request errors, JSON parse failures).

**Why it matters:** Failed LLM calls are invisible in Langfuse tracing, making production debugging significantly harder. When investigating why a row failed, the operator would see the error in the audit trail but not in Langfuse, breaking the correlation workflow described in CLAUDE.md's telemetry section. This also means the error-trace recording that the Azure variant provides for capacity errors (before raising for retry) is completely absent, so retried-then-succeeded calls have no trace of the initial failures.

**Evidence:**
```python
# Defined at line 556 but grep for _record_langfuse_trace_for_error call sites
# returns only the definition itself - zero callers
def _record_langfuse_trace_for_error(self, token_id, query_prefix, prompt, error_message, latency_ms):
    ...
```

### [508-554, 604-608] Missing telemetry emission on Langfuse trace failures

**What:** When Langfuse trace recording fails (lines 550, 604), the exception is caught and logged via structlog, but no telemetry event is emitted via `self._telemetry_emit()`. The single-query OpenRouter variant (openrouter.py lines 371-383, 433-445) emits `langfuse_trace_failed` and `langfuse_error_trace_failed` telemetry events on failure.

**Why it matters:** This violates CLAUDE.md's "No Silent Failures" telemetry principle: "Any time an object is polled or has an opportunity to emit telemetry, it MUST either send what it has or explicitly acknowledge 'I have nothing'." A Langfuse connection failure in production would be logged locally but not visible in the telemetry pipeline (Datadog, Grafana, etc.), meaning operators monitoring dashboards would miss the problem.

**Evidence:**
```python
# Multi-query (missing telemetry) - line 550-554
except Exception as e:
    import structlog
    logger = structlog.get_logger(__name__)
    logger.warning("Failed to record Langfuse trace", error=str(e))
    # No telemetry_emit call!

# Single-query (correct) - openrouter.py lines 371-383
except Exception as e:
    ctx.telemetry_emit({
        "event": "langfuse_trace_failed",
        "plugin": self.name,
        "error": str(e),
    })
```

### [845-869] Missing shared validation utility (validate_json_object_response)

**What:** The OpenRouter multi-query variant manually implements JSON parsing and type validation (lines 858-880) instead of using the shared `validate_json_object_response()` from `validation.py`. The Azure multi-query variant uses this shared utility (azure_multi_query.py line 501).

**Why it matters:** Code duplication of critical validation logic. If a bug is found in JSON validation or a new edge case is discovered (e.g., a model returning a JSON array instead of an object), fixing it in `validation.py` would fix Azure but not OpenRouter. The inline implementation also lacks the structured `ValidationError` return type that the shared utility provides, meaning error reporting is slightly different between the two variants.

**Evidence:**
```python
# Azure multi-query - uses shared utility
from elspeth.plugins.llm.validation import ValidationSuccess, validate_json_object_response
validation_result = validate_json_object_response(content)

# OpenRouter multi-query - reimplements inline
try:
    parsed = json.loads(content_str)
except json.JSONDecodeError as e:
    ...
if not isinstance(parsed, dict):
    ...
```

### [914] Usage metadata inconsistency with Azure

**What:** When usage data is available, OpenRouter stores `usage` directly (which may be `{}`) at line 914. Azure (lines 558-565) provides a default structure `{"prompt_tokens": 0, "completion_tokens": 0}` when usage is empty. This means downstream consumers cannot reliably access `usage["prompt_tokens"]` without risking a `KeyError` on OpenRouter results, but can on Azure results.

**Why it matters:** Any downstream transform, sink, or audit query that accesses `{prefix}_usage["prompt_tokens"]` will get `KeyError` for OpenRouter rows but work fine for Azure rows. This inconsistency in the guaranteed field contract is a latent bug that would surface when switching between providers or running mixed-provider pipelines.

**Evidence:**
```python
# OpenRouter - raw usage (may be {})
output[f"{spec.output_prefix}_usage"] = usage

# Azure - normalized with defaults
output[f"{spec.output_prefix}_usage"] = (
    response.usage if response.usage
    else {"prompt_tokens": 0, "completion_tokens": 0}
)
```

### [828] Truncation check divergence from Azure

**What:** The truncation check at line 828 uses `completion_tokens >= effective_max_tokens` without the `completion_tokens > 0` guard that Azure has at line 470. While this cannot produce false positives in the current code (because `effective_max_tokens` is always > 0 when not None, and `completion_tokens` defaults to 0), it represents an unexplained divergence from the reference implementation.

**Why it matters:** If OpenRouter ever returns `completion_tokens: 0` in usage data (e.g., for a zero-length response that still triggers the structured output parser), the behavior would differ between providers. The Azure guard is defensive-in-depth against this edge case.

**Evidence:**
```python
# OpenRouter - no > 0 guard
if effective_max_tokens is not None and completion_tokens >= effective_max_tokens:

# Azure - has > 0 guard
if effective_max_tokens is not None and completion_tokens > 0 and completion_tokens >= effective_max_tokens:
```

## Observations

### [1002] Unsafe `token_id` extraction pattern

**What:** Line 1002 uses `ctx.token.token_id if ctx.token else "unknown"`. The Azure variant (line 649) uses `ctx.token.token_id if ctx.token is not None else "unknown"`, which is the more explicit None check. While functionally equivalent (token would never be falsy-but-not-None), the `is not None` form is the project's standard pattern.

### [689-929] `_process_single_query` does not receive `token_id`

**What:** The OpenRouter multi-query's `_process_single_query` method signature lacks a `token_id` parameter, unlike Azure's version (line 353 has `token_id: str`). This means individual query tracing cannot correlate to the token. The `token_id` is only used in `_process_row` (line 1002) for the aggregate Langfuse trace, but individual error traces (`_record_langfuse_trace_for_error`) -- which are dead code anyway -- would need it.

### [57-193] Configuration class duplication

**What:** `OpenRouterMultiQueryConfig` reimplements `build_json_schema()`, `build_response_format()`, `parse_output_mapping()`, and `expand_queries()` -- all of which are identical to `MultiQueryConfig` except for the missing `validate_no_output_key_collisions` and missing `max_tokens` in `expand_queries`. These could share a mixin or common base.

### [638-687] `_validate_field_type` duplication

**What:** The `_validate_field_type` method is identical between OpenRouter and Azure multi-query variants (both implement the same bool-check, int/float whole-number check, enum validation). This should be a shared utility, likely on `OutputFieldConfig` itself or in a shared validation module.

### [1094-1100] Result merge uses dict.update() which silently overwrites

**What:** When merging individual query results into the output row, `output.update(result.row)` is used. If any query's output fields accidentally overlap with input fields or another query's fields, the later value silently wins. Combined with the missing collision validation, this is a recipe for data corruption.

### [274-364] Constructor is 90 lines long

**What:** The `__init__` method spans lines 274-364, performing config parsing, schema construction, pool setup, client initialization, and tracing setup. This is a maintainability concern but not a bug.

## Verdict

**Status:** NEEDS_REFACTOR
**Recommended action:**
1. **Immediate (Critical):** Fix the `None` content crash at line 846 by adding a null check before `.strip()`. Fix `expand_queries()` to pass `criterion.max_tokens`. Add the `validate_no_output_key_collisions` validator.
2. **Near-term (Warnings):** Wire up `_record_langfuse_trace_for_error` to actual error paths. Switch to `validate_json_object_response()` shared utility. Add telemetry emission on Langfuse failures. Normalize usage metadata to match Azure's default structure. Consider making network/server errors retryable to match the single-query variant's behavior.
3. **Deferred (Observations):** Extract shared validation logic (`_validate_field_type`), configuration methods (`build_json_schema`, etc.), and consider a multi-query config base class to prevent future divergence.
**Confidence:** HIGH -- All critical findings are confirmed by direct line-by-line comparison with the working Azure equivalent, supported by reading the contracts, shared utilities, and data flow. The `None` content crash is provable from the OpenRouter API specification.
