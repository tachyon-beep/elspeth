# T10: LLM Plugin Consolidation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Collapse 6 LLM transform classes into a unified LLMTransform with LLMProvider protocol, eliminating ~2,700 lines of duplication.

**Architecture:** Strategy pattern — LLMProvider protocol handles transport (Azure SDK vs OpenRouter HTTP), two processing strategies (SingleQuery/MultiQuery) handle row logic, shared LangfuseTracer handles tracing. Domain-specific terminology replaced with generic QuerySpec.

**Tech Stack:** Python 3.12+, Pydantic v2, pluggy, httpx, openai SDK, structlog, pytest

**Design doc:** `docs/plans/2026-02-25-llm-plugin-consolidation.md`

---

## Phase A: Extract Shared Infrastructure

Phase A extracts duplicated code into shared modules without changing any transform's behavior. Each task is independently committable.

---

### Task 1: Extract LangfuseTracer to langfuse.py

**Files:**
- Create: `src/elspeth/plugins/llm/langfuse.py`
- Test: `tests/unit/plugins/llm/test_langfuse_tracer.py`

The Langfuse tracing code is duplicated across all 6 LLM transform files (~600 lines total). The variations are:
- `_setup_langfuse_tracing()`: identical logic, varies only in whether tracing_config is a parameter or self._tracing_config
- `_record_langfuse_trace()`: identical body, varies in metadata keys (deployment vs model vs query) and whether ctx/telemetry_emit is passed
- `_record_langfuse_trace_for_error()`: identical body, same metadata variation
- `_flush_tracing()`: byte-for-byte identical across all files

**Step 1: Write failing tests for LangfuseTracer**

Test file: `tests/unit/plugins/llm/test_langfuse_tracer.py`

Tests to write:
- `test_init_with_langfuse_config_creates_client` — mock Langfuse import, verify client created with correct keys
- `test_init_with_non_langfuse_config_does_nothing` — pass AzureAITracingConfig, verify no client
- `test_init_langfuse_not_installed_logs_warning` — simulate ImportError, verify warning logged
- `test_record_success_creates_span_and_generation` — mock client, verify nested context managers called with correct metadata
- `test_record_success_with_usage_updates_generation` — verify usage_details populated when usage.is_known
- `test_record_success_without_usage_skips_usage_details` — verify no usage_details when usage is None
- `test_record_error_sets_error_level` — verify level="ERROR" and status_message set
- `test_record_when_inactive_is_noop` — verify no calls when tracing_active is False
- `test_record_exception_emits_telemetry` — mock client that raises, verify telemetry_emit called (No Silent Failures)
- `test_flush_calls_client_flush` — verify flush() delegated to client
- `test_flush_when_no_client_is_noop`

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_langfuse_tracer.py -v`
Expected: FAIL — module does not exist

**Step 3: Implement LangfuseTracer**

Create `src/elspeth/plugins/llm/langfuse.py`:

```python
"""Langfuse tracing utilities for LLM transforms.

Extracts the Langfuse v3 span/generation recording pattern that was duplicated
across all 6 LLM transform files. Uses the OpenTelemetry-based context manager
API (start_as_current_observation).

Follows No Silent Failures: any tracing emission point emits telemetry on failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.llm.tracing import LangfuseTracingConfig, TracingConfig

if TYPE_CHECKING:
    pass  # Langfuse is optional dependency


TelemetryEmitCallback = Callable[[dict[str, Any]], None]


@dataclass
class LangfuseTracer:
    """Manages Langfuse v3 span recording for LLM queries.

    Consolidates the 3 duplicated methods (_setup, _record_success, _record_error)
    that appeared across all 6 LLM transform files.

    Usage:
        tracer = LangfuseTracer(transform_name="llm")
        tracer.setup(tracing_config, logger)
        tracer.record_success(telemetry_emit, token_id, "query_name", prompt, result)
        tracer.record_error(telemetry_emit, token_id, "query_name", prompt, error_msg)
        tracer.flush()
    """

    transform_name: str
    _client: Any = field(default=None, init=False, repr=False)
    _active: bool = field(default=False, init=False)

    def setup(self, tracing_config: TracingConfig | None, logger: Any) -> None:
        """Initialize Langfuse client from config. Noop if not LangfuseTracingConfig."""
        if tracing_config is None:
            return
        if not isinstance(tracing_config, LangfuseTracingConfig):
            return

        try:
            from langfuse import Langfuse  # type: ignore[import-not-found,import-untyped]

            self._client = Langfuse(
                public_key=tracing_config.public_key,
                secret_key=tracing_config.secret_key,
                host=tracing_config.host,
                tracing_enabled=tracing_config.tracing_enabled,
            )
            self._active = True
            logger.info(
                "Langfuse tracing initialized (v3)",
                provider="langfuse",
                host=tracing_config.host,
                tracing_enabled=tracing_config.tracing_enabled,
            )
        except ImportError:
            logger.warning(
                "Langfuse tracing requested but package not installed",
                provider="langfuse",
                hint="Install with: uv pip install elspeth[tracing-langfuse]",
            )

    @property
    def is_active(self) -> bool:
        return self._active and self._client is not None

    def record_success(
        self,
        telemetry_emit: TelemetryEmitCallback | None,
        token_id: str,
        query_name: str,
        prompt: str,
        response_content: str,
        model: str,
        usage: TokenUsage | None = None,
        latency_ms: float | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record successful LLM call as Langfuse span + generation."""
        if not self.is_active:
            return

        try:
            metadata = {"token_id": token_id, "plugin": self.transform_name, "query": query_name}
            if extra_metadata:
                metadata.update(extra_metadata)

            with (
                self._client.start_as_current_observation(
                    as_type="span",
                    name=f"elspeth.{self.transform_name}",
                    metadata=metadata,
                ),
                self._client.start_as_current_observation(
                    as_type="generation",
                    name="llm_call",
                    model=model,
                    input=[{"role": "user", "content": prompt}],
                ) as generation,
            ):
                update_kwargs: dict[str, Any] = {"output": response_content}

                if usage is not None and usage.is_known:
                    update_kwargs["usage_details"] = {
                        "input": usage.prompt_tokens,
                        "output": usage.completion_tokens,
                    }

                if latency_ms is not None:
                    update_kwargs["metadata"] = {"latency_ms": latency_ms}

                generation.update(**update_kwargs)
        except Exception as e:
            self._handle_trace_failure("langfuse_trace_failed", e, telemetry_emit)

    def record_error(
        self,
        telemetry_emit: TelemetryEmitCallback | None,
        token_id: str,
        query_name: str,
        prompt: str,
        error_message: str,
        model: str,
        latency_ms: float | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record failed LLM call as Langfuse span + generation with ERROR level."""
        if not self.is_active:
            return

        try:
            metadata = {"token_id": token_id, "plugin": self.transform_name, "query": query_name}
            if extra_metadata:
                metadata.update(extra_metadata)

            with (
                self._client.start_as_current_observation(
                    as_type="span",
                    name=f"elspeth.{self.transform_name}",
                    metadata=metadata,
                ),
                self._client.start_as_current_observation(
                    as_type="generation",
                    name="llm_call",
                    model=model,
                    input=[{"role": "user", "content": prompt}],
                ) as generation,
            ):
                update_kwargs: dict[str, Any] = {
                    "level": "ERROR",
                    "status_message": error_message,
                }

                if latency_ms is not None:
                    update_kwargs["metadata"] = {"latency_ms": latency_ms}

                generation.update(**update_kwargs)
        except Exception as e:
            self._handle_trace_failure("langfuse_error_trace_failed", e, telemetry_emit)

    def flush(self) -> None:
        """Flush pending tracing data."""
        if self._client is None:
            return
        try:
            self._client.flush()
        except Exception as e:
            import structlog
            logger = structlog.get_logger(__name__)
            logger.warning("Failed to flush Langfuse tracing", error=str(e))

    def _handle_trace_failure(
        self, event_name: str, error: Exception, telemetry_emit: TelemetryEmitCallback | None
    ) -> None:
        """Handle trace recording failure — No Silent Failures."""
        if telemetry_emit is not None:
            telemetry_emit({"event": event_name, "plugin": self.transform_name, "error": str(error)})
        import structlog
        logger = structlog.get_logger(__name__)
        logger.warning(f"Failed to record Langfuse trace: {event_name}", error=str(error))
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_langfuse_tracer.py -v`
Expected: All PASS

**Step 5: Commit**

```
feat(llm): extract LangfuseTracer — consolidate 6 duplicated tracing implementations
```

---

### Task 2: Extract shared validation helpers to validation.py

**Files:**
- Modify: `src/elspeth/plugins/llm/validation.py` (add functions)
- Test: `tests/unit/plugins/llm/test_validation.py` (extend existing)

Three duplicated patterns to extract:
1. Template rendering error handling (4 instances across azure.py:434, openrouter.py:512, azure_multi_query.py:207, openrouter_multi_query.py:218)
2. Truncation detection (2 instances: azure_multi_query.py:284, openrouter_multi_query.py:346)
3. Markdown fence stripping (2 instances: azure_multi_query.py:330, openrouter_multi_query.py:367)

**Step 1: Write failing tests**

Test file: `tests/unit/plugins/llm/test_validation.py` (extend existing)

Tests to write:
- `test_render_template_safe_success` — returns rendered result
- `test_render_template_safe_template_error_returns_error_reason` — returns TransformErrorReason dict
- `test_render_template_safe_includes_template_hash`
- `test_render_template_safe_includes_template_source_when_present`
- `test_render_template_safe_includes_query_name_when_provided`
- `test_check_truncation_finish_reason_length_returns_error`
- `test_check_truncation_finish_reason_stop_returns_none`
- `test_check_truncation_token_heuristic_returns_error`
- `test_check_truncation_no_finish_reason_no_tokens_returns_none`
- `test_check_truncation_includes_preview_when_content_provided`
- `test_strip_markdown_fences_removes_triple_backtick`
- `test_strip_markdown_fences_removes_language_tag`
- `test_strip_markdown_fences_noop_when_no_fences`
- `test_strip_markdown_fences_noop_in_structured_mode`

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_validation.py -v -k "render_template or check_truncation or strip_markdown"`
Expected: FAIL — functions do not exist

**Step 3: Implement shared functions**

Add to `src/elspeth/plugins/llm/validation.py`:

```python
from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.llm.templates import PromptTemplate, RenderedPrompt, TemplateError

# Type alias for structured error reasons
TransformErrorReason = dict[str, Any]


def render_template_safe(
    template: PromptTemplate,
    row_or_context: Any,
    *,
    contract: Any | None = None,
    query_name: str | None = None,
) -> RenderedPrompt | TransformErrorReason:
    """Render a template, returning structured error on failure.

    Consolidates the try/except TemplateError pattern from 4 LLM transforms.
    """
    try:
        return template.render_with_metadata(row_or_context, contract=contract)
    except TemplateError as e:
        error: TransformErrorReason = {
            "reason": "template_rendering_failed",
            "error": str(e),
            "template_hash": template.template_hash,
        }
        if template.template_source:
            error["template_file_path"] = template.template_source
        if query_name is not None:
            error["query"] = query_name
        return error


def check_truncation(
    *,
    finish_reason: str | None,
    completion_tokens: int | None,
    prompt_tokens: int | None,
    max_tokens: int | None,
    query_name: str | None = None,
    content_preview: str | None = None,
) -> TransformErrorReason | None:
    """Check for response truncation. Returns error dict or None.

    Uses finish_reason as authoritative signal, falls back to token heuristic.
    Consolidates truncation detection from azure_multi_query.py:284 and
    openrouter_multi_query.py:346.
    """
    is_truncated: bool
    if finish_reason is not None:
        is_truncated = finish_reason == "length"
    else:
        is_truncated = (
            max_tokens is not None
            and completion_tokens is not None
            and completion_tokens > 0
            and completion_tokens >= max_tokens
        )

    if not is_truncated:
        return None

    error: TransformErrorReason = {
        "reason": "response_truncated",
        "error": (
            f"LLM response was truncated at {completion_tokens} tokens "
            f"(max_tokens={max_tokens}). Increase max_tokens or shorten your prompt."
        ),
        "max_tokens": max_tokens,
        "completion_tokens": completion_tokens,
        "prompt_tokens": prompt_tokens,
        "finish_reason": finish_reason,
    }
    if query_name is not None:
        error["query"] = query_name
    if content_preview:
        error["raw_response_preview"] = content_preview[:500]
    return error


def strip_markdown_fences(content: str) -> str:
    """Strip markdown code block fences from LLM response content.

    LLMs sometimes wrap JSON responses in ```json ... ``` blocks even in
    JSON mode. This strips them so JSON parsing succeeds.

    Consolidates identical logic from azure_multi_query.py:330 and
    openrouter_multi_query.py:367.
    """
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    first_newline = stripped.find("\n")
    if first_newline != -1:
        stripped = stripped[first_newline + 1:]
    if stripped.endswith("```"):
        stripped = stripped[:-3].strip()
    return stripped
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_validation.py -v`
Expected: All PASS

**Step 5: Commit**

```
feat(llm): extract shared validation helpers — template errors, truncation, fence stripping
```

---

### Task 3: Wire existing transforms to use extracted utilities

**Files:**
- Modify: `src/elspeth/plugins/llm/azure.py` — replace inline tracing with LangfuseTracer
- Modify: `src/elspeth/plugins/llm/openrouter.py` — replace inline tracing with LangfuseTracer
- Modify: `src/elspeth/plugins/llm/azure_multi_query.py` — replace tracing + validation
- Modify: `src/elspeth/plugins/llm/openrouter_multi_query.py` — replace tracing + validation
- Modify: `src/elspeth/plugins/llm/azure_batch.py` — replace _setup_langfuse_tracing and _flush_tracing
- Modify: `src/elspeth/plugins/llm/openrouter_batch.py` — replace tracing

This is a mechanical refactor. For each file:

1. Add `from elspeth.plugins.llm.langfuse import LangfuseTracer`
2. Add `self._langfuse_tracer = LangfuseTracer(transform_name=self.name)` in `__init__`
3. Replace `_setup_langfuse_tracing()` calls with `self._langfuse_tracer.setup(tracing_config, logger)`
4. Replace `_record_langfuse_trace()` calls with `self._langfuse_tracer.record_success(...)`
5. Replace `_record_langfuse_trace_for_error()` calls with `self._langfuse_tracer.record_error(...)`
6. Replace `_flush_tracing()` with `self._langfuse_tracer.flush()`
7. Delete the 3-4 private methods that are now replaced

For azure_multi_query.py and openrouter_multi_query.py additionally:
1. Add `from elspeth.plugins.llm.validation import check_truncation, strip_markdown_fences`
2. Replace inline truncation detection with `check_truncation(...)` call
3. Replace inline fence stripping with `strip_markdown_fences(content)`

For azure.py, openrouter.py, azure_multi_query.py, openrouter_multi_query.py:
1. Template error handling is NOT wired yet (it returns different shapes for single vs multi-query, leave for Phase B)

**Testing:** Run full LLM test suite after each file is updated:

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/ -v --tb=short`
Expected: All existing tests pass (behavior unchanged)

Also run tracing-specific tests:
Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_azure_tracing.py tests/unit/plugins/llm/test_openrouter_tracing.py tests/unit/plugins/llm/test_tracing_integration.py -v`

**Step N: Commit (after all 6 files are updated)**

```
refactor(llm): wire all 6 transforms to use LangfuseTracer and shared validation

Replaces ~600 lines of duplicated Langfuse tracing with LangfuseTracer calls.
Replaces duplicated truncation detection and fence stripping with shared helpers.
No behavioral changes — all existing tests pass.
```

---

### Task 4: Verify Phase A and run full suite

**Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x --tb=short -q`
Expected: All 8,037+ tests pass

**Step 2: Run mypy**

Run: `.venv/bin/python -m mypy src/`
Expected: No new errors

**Step 3: Run ruff**

Run: `.venv/bin/python -m ruff check src/`
Expected: Clean

**Step 4: Run tier model enforcement**

Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: Pass

**Step 5: Run config contracts**

Run: `.venv/bin/python -m scripts.check_contracts`
Expected: Pass

**Step 6: Commit if not already committed, then tag**

Phase A is complete. All shared infrastructure is extracted and wired. Existing transforms work identically.

---

## Phase B: Provider Protocol + Unified Transform

Phase B introduces the new architecture. This is the structural change — files are created, old files are deleted, tests are migrated.

---

### Task 5: Create provider.py — LLMProvider protocol and DTOs

**Files:**
- Create: `src/elspeth/plugins/llm/provider.py`
- Test: `tests/unit/plugins/llm/test_provider_protocol.py`

**Step 1: Write failing tests**

Tests:
- `test_llm_query_result_is_frozen` — verify frozen dataclass
- `test_llm_query_result_fields` — verify all fields present with correct types
- `test_finish_reason_enum_values` — verify stop, length, content_filter, tool_calls
- `test_finish_reason_from_string` — verify FinishReason("stop") works
- `test_llm_provider_protocol_is_runtime_checkable` — verify isinstance works
- `test_mock_provider_satisfies_protocol` — create mock implementing protocol, verify isinstance

**Step 2: Implement provider.py**

```python
"""LLM provider protocol and response DTOs.

The LLMProvider protocol defines the narrow interface between LLMTransform
(shared logic) and provider-specific transport (Azure SDK, OpenRouter HTTP).

Providers are responsible for:
1. Client lifecycle (creation, caching per state_id, cleanup)
2. LLM API calls (transport-specific)
3. Tier 3 boundary validation (response parsing, NaN rejection)
4. Error classification (raising typed exceptions)
5. Audit trail recording (via their Audited*Client)

The transform above the provider never sees raw SDK/HTTP responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from elspeth.contracts.token_usage import TokenUsage


class FinishReason(StrEnum):
    """Validated finish reasons from LLM providers."""
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    TOOL_CALLS = "tool_calls"


def parse_finish_reason(raw: str | None) -> FinishReason | None:
    """Parse raw finish_reason string into validated enum.

    Unknown values return None (provider-specific reasons we don't handle).
    """
    if raw is None:
        return None
    try:
        return FinishReason(raw)
    except ValueError:
        return None  # Unknown finish reason — don't crash, just don't act on it


@dataclass(frozen=True, slots=True)
class LLMQueryResult:
    """Normalized, validated result from any LLM provider.

    All Tier 3 validation has already happened inside the provider.
    Content is guaranteed non-null, non-empty string.
    Usage is normalized via TokenUsage.known/unknown.
    """
    content: str
    usage: TokenUsage
    model: str
    raw_response: dict[str, Any]  # For audit recording — stays within provider boundary
    finish_reason: FinishReason | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """What LLMTransform needs from a provider. Narrow interface.

    Providers raise typed exceptions from elspeth.plugins.clients.errors:
    - RateLimitError: 429 / rate limit (retryable)
    - NetworkError: connection failures (retryable)
    - ServerError: 5xx errors (retryable)
    - ContentPolicyError: content filtering (not retryable)
    - LLMCallError: other failures (not retryable)
    """

    def execute_query(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int | None,
        state_id: str,
        token_id: str,
    ) -> LLMQueryResult: ...

    def close(self) -> None: ...
```

**Step 3: Run tests, verify pass**

**Step 4: Commit**

```
feat(llm): add LLMProvider protocol and LLMQueryResult DTO
```

---

### Task 6: Create providers/azure.py

**Files:**
- Create: `src/elspeth/plugins/llm/providers/__init__.py`
- Create: `src/elspeth/plugins/llm/providers/azure.py`
- Test: `tests/unit/plugins/llm/test_provider_azure.py`

The Azure provider is thin — it wraps the existing `AuditedLLMClient` (in `plugins/clients/llm.py`) and normalizes its `LLMResponse` to `LLMQueryResult`.

**Key implementation details:**
- Client caching is per-state_id with threading.Lock (matches azure.py:446-470)
- Error classification already happens inside AuditedLLMClient (llm.py:322-390)
- The provider re-raises the same typed exceptions (RateLimitError, ContentPolicyError, etc.)
- Azure AI tracing auto-instrumentation is set up in __init__ if tracing_config.provider == "azure_ai"

**Tests:**
- `test_execute_query_returns_llm_query_result` — mock AuditedLLMClient, verify correct mapping
- `test_execute_query_maps_finish_reason` — verify FinishReason enum conversion
- `test_execute_query_propagates_rate_limit_error` — verify RateLimitError passes through
- `test_execute_query_propagates_content_policy_error`
- `test_client_cached_per_state_id` — verify same state_id returns same client
- `test_close_clears_clients`
- `test_azure_ai_tracing_setup_in_init` — verify _configure_azure_monitor called

**Step N: Commit**

```
feat(llm): add AzureLLMProvider — thin wrapper over AuditedLLMClient
```

---

### Task 7: Create providers/openrouter.py

**Files:**
- Create: `src/elspeth/plugins/llm/providers/openrouter.py`
- Test: `tests/unit/plugins/llm/test_provider_openrouter.py`

The OpenRouter provider is thicker — it does raw HTTP and all Tier 3 validation. Extracts the response parsing logic from openrouter.py:552-651.

**Key implementation details:**
- Client caching per-state_id with threading.Lock (matches openrouter.py pattern)
- JSON parsing with `_reject_nonfinite_constant` from validation.py
- Content extraction: `data["choices"][0]["message"]["content"]` with validation wrapping
- Null content check → ContentPolicyError
- Non-finite usage validation
- HTTP status code → typed exception mapping (429→RateLimitError, 5xx→ServerError)
- Uses AuditedHTTPClient for audit recording

**Tests (use ChaosLLM fixtures from conftest):**
- `test_execute_query_parses_json_response` — mock HTTP, verify LLMQueryResult fields
- `test_execute_query_rejects_nan_in_response` — verify NaN/Infinity rejected
- `test_execute_query_rejects_null_content` — verify ContentPolicyError raised
- `test_execute_query_rejects_non_string_content` — verify LLMCallError
- `test_execute_query_validates_usage_non_finite` — verify non-finite usage values rejected
- `test_execute_query_429_raises_rate_limit_error` — mock 429 response
- `test_execute_query_500_raises_server_error` — mock 5xx response
- `test_execute_query_network_error_raises_network_error` — mock connection failure
- `test_execute_query_4xx_raises_llm_call_error` — mock non-429 4xx
- `test_client_cached_per_state_id`
- `test_close_clears_clients`

**Step N: Commit**

```
feat(llm): add OpenRouterLLMProvider — HTTP transport with Tier 3 validation
```

---

### Task 8: Refactor config models

**Files:**
- Modify: `src/elspeth/plugins/llm/base.py` — keep LLMConfig, add multi-query fields
- Modify: `src/elspeth/plugins/llm/multi_query.py` — rewrite QuerySpec domain-agnostic, remove CaseStudyConfig/CriterionConfig/MultiQueryConfigMixin/MultiQueryConfig
- Create config classes for Azure and OpenRouter in their provider files (or a new `configs.py`)
- Test: extend existing config tests

**Key changes:**

`base.py` — LLMConfig gets the `provider` field and optional multi-query fields:
```python
class LLMConfig(TransformDataConfig):
    provider: str = Field(..., description="LLM provider (azure, openrouter)")
    model: str | None = Field(None, description="Model identifier")
    # ... existing fields ...
    queries: list[QuerySpec] | dict[str, QuerySpecBody] | None = Field(None, description="Multi-query specs")
```

`multi_query.py` — Rewrite `QuerySpec` to be domain-agnostic:
```python
@dataclass(frozen=True, slots=True)
class QuerySpec:
    """One query to execute against an LLM for a given row."""
    name: str
    input_fields: dict[str, str]  # {template_var: row_field}
    response_format: ResponseFormat = ResponseFormat.STANDARD
    output_fields: list[OutputFieldConfig] | None = None
    template: str | None = None
    max_tokens: int | None = None
```

Remove: `CaseStudyConfig`, `CriterionConfig`, `MultiQueryConfigMixin`, `MultiQueryConfig`, `validate_multi_query_key_collisions`

Add: `QuerySpecBody` (Pydantic model for dict-keyed config parsing), `resolve_queries()` function (normalizes list|dict to list[QuerySpec])

Provider-specific config:
```python
class AzureOpenAIConfig(LLMConfig):
    deployment_name: str
    endpoint: str
    api_key: str
    api_version: str = "2024-10-21"

class OpenRouterConfig(LLMConfig):
    api_key: str
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 60.0
```

These can live in the provider files or a shared `configs.py` — decide during implementation based on import dependencies.

**Tests:**
- Existing config validation tests need migration
- New tests for QuerySpec (domain-agnostic), resolve_queries(), dict-keyed parsing
- Test `model: str | None = None` (not empty string)

**Step N: Commit**

```
refactor(llm): flatten config hierarchy — remove MultiQueryConfigMixin, domain-agnostic QuerySpec
```

---

### Task 9: Create transform.py — LLMTransform with two strategies

**Files:**
- Create: `src/elspeth/plugins/llm/transform.py`
- Test: `tests/unit/plugins/llm/test_transform.py`

This is the core of Phase B. The unified transform with:
- `LLMTransform` — the plugin class, registered as `name = "llm"`
- `SingleQueryStrategy` — direct template render, raw content output
- `MultiQueryStrategy` — mapped context, JSON parsing, field extraction

**Key implementation details:**

`LLMTransform.__init__` dispatches provider:
```python
_PROVIDERS = {
    "azure": AzureLLMProvider,
    "openrouter": OpenRouterLLMProvider,
}

class LLMTransform(BaseTransform, BatchTransformMixin):
    name = "llm"
    determinism = Determinism.NON_DETERMINISTIC

    def __init__(self, config: dict[str, Any]) -> None:
        provider_name = config["provider"]
        provider_cls = _PROVIDERS[provider_name]
        # Parse config with provider-specific model
        self._config = _parse_config(provider_name, config)
        self._provider = provider_cls(self._config, ...)
        self._tracer = LangfuseTracer(transform_name=self.name)
        self._query_specs = resolve_queries(self._config)
        self._strategy = (
            MultiQueryStrategy(...) if len(self._query_specs) > 1 or self._config.queries
            else SingleQueryStrategy(...)
        )
```

Strategy selection: if `queries` is explicitly provided (even with one entry), use MultiQueryStrategy. Otherwise SingleQueryStrategy. This preserves explicit intent.

**Tests (using ChaosLLM fixtures):**
- Single-query tests: verify LLMTransform(provider="azure") with no queries works as single-query
- Multi-query tests: verify LLMTransform(provider="openrouter", queries=...) uses multi-query strategy
- Provider dispatch: verify "azure" creates AzureLLMProvider, "openrouter" creates OpenRouterLLMProvider
- Unknown provider: verify helpful error message
- Error handling: verify all exception types map to correct TransformResult
- Contract propagation: verify single-query uses propagate_contract, multi-query builds OBSERVED
- Truncation: verify truncated responses return error
- Fence stripping: verify markdown fences stripped in STANDARD mode

**Step N: Commit**

```
feat(llm): unified LLMTransform with SingleQuery/MultiQuery strategies
```

---

### Task 10: Update plugin registration and validation

**Files:**
- Modify: `src/elspeth/plugins/validation.py` — update `_get_transform_config_model()` for "llm" plugin
- Modify: `src/elspeth/plugins/discovery.py` — verify llm/ directory still scanned correctly
- Test: update plugin discovery tests

**Key changes in validation.py:**

Replace the 4 deleted plugin entries:
```python
# BEFORE (lines 262-282):
elif transform_type == "azure_llm": ...
elif transform_type == "azure_multi_query_llm": ...
elif transform_type == "openrouter_llm": ...
elif transform_type == "openrouter_multi_query_llm": ...

# AFTER:
elif transform_type == "llm":
    from elspeth.plugins.llm.transform import LLMTransform
    # Config validation is provider-dependent — resolved at instantiation
    from elspeth.plugins.llm.base import LLMConfig
    return LLMConfig
```

Batch entries stay unchanged:
```python
elif transform_type == "azure_batch_llm": ...
elif transform_type == "openrouter_batch_llm": ...
```

Add helpful error for old plugin names:
```python
elif transform_type in {"azure_llm", "openrouter_llm", "azure_multi_query_llm", "openrouter_multi_query_llm"}:
    raise ValueError(
        f"Plugin '{transform_type}' has been replaced by 'llm' with a 'provider' field. "
        f"Example: plugin: llm, provider: {'azure' if 'azure' in transform_type else 'openrouter'}"
    )
```

**Step N: Commit**

```
refactor(llm): update plugin registration — 5 names → 1 unified 'llm' plugin
```

---

### Task 11: Migrate tests

**Files:**
- Modify: 17+ test files (see inventory below)
- Modify: `tests/unit/plugins/llm/conftest.py`
- Modify: `tests/performance/stress/conftest.py`

**Test migration inventory:**

| Test File | Current Import | New Import | Migration Type |
|-----------|---------------|-----------|----------------|
| test_azure.py | AzureLLMTransform | LLMTransform(provider="azure") | Instantiation change |
| test_openrouter.py | OpenRouterLLMTransform | LLMTransform(provider="openrouter") | Instantiation change |
| test_azure_multi_query.py | AzureMultiQueryLLMTransform | LLMTransform(provider="azure", queries=...) | Instantiation + config |
| test_openrouter_multi_query.py | OpenRouterMultiQueryLLMTransform | LLMTransform(provider="openrouter", queries=...) | Instantiation + config |
| test_multi_query.py | AzureMultiQueryLLMTransform | LLMTransform(provider="azure", queries=...) | Instantiation + config |
| test_azure_multi_query_retry.py | AzureMultiQueryLLMTransform | LLMTransform(provider="azure", queries=...) | Instantiation + config |
| test_azure_multi_query_profiling.py | AzureMultiQueryLLMTransform | LLMTransform(provider="azure", queries=...) | Instantiation + config |
| test_azure_tracing.py | AzureLLMTransform | LLMTransform(provider="azure") | Instantiation change |
| test_openrouter_tracing.py | OpenRouterLLMTransform, OpenRouterMultiQueryLLMTransform | LLMTransform(provider="openrouter") | Instantiation change |
| test_tracing_integration.py | AzureLLMTransform, OpenRouterLLMTransform | LLMTransform | Instantiation change |
| test_p1_bug_fixes.py | via conftest factories | Update factories | Factory update |
| test_azure_multi_query_contract.py | AzureMultiQueryLLMTransform | LLMTransform(provider="azure", queries=...) | Instantiation + config |
| test_telemetry_contracts.py | Multiple transforms | LLMTransform | Instantiation change |
| test_plugin_wiring.py | Multiple transforms | LLMTransform | Check wiring |
| test_llm_retry.py (stress) | via stress conftest | Update stress factories | Factory update |
| test_assert_to_raise.py | AzureOpenAIConfig | AzureOpenAIConfig (new location) | Import path change |

**Multi-query config migration:**
Old config uses `case_studies` + `criteria`. New config uses `queries` dict.
Test fixtures need conversion:
```python
# BEFORE
config = {
    "case_studies": [{"name": "cs1", "input_fields": ["text"]}],
    "criteria": [{"name": "diag", "description": "..."}],
    "output_mapping": {"score": {"suffix": "score", "type": "integer"}},
}

# AFTER
config = {
    "queries": {
        "cs1_diag": {
            "input_fields": {"text": "text"},
            "response_format": "standard",
            "output_fields": [{"suffix": "score", "type": "integer"}],
        }
    },
}
```

**Strategy:** Migrate test files in batches:
1. First: update conftest.py factories (all tests use them)
2. Then: single-query tests (azure, openrouter, tracing)
3. Then: multi-query tests (multi_query, retry, profiling, contract)
4. Then: integration, performance, plugin wiring
5. Run full suite after each batch

**Step N: Commit (may be multiple commits)**

```
test(llm): migrate LLM test suite to unified LLMTransform — 17 files, 392 tests
```

---

### Task 12: Update examples and delete old files

**Files:**
- Modify: 16 example YAML files (see inventory)
- Delete: `src/elspeth/plugins/llm/azure.py`
- Delete: `src/elspeth/plugins/llm/openrouter.py`
- Delete: `src/elspeth/plugins/llm/base_multi_query.py`
- Delete: `src/elspeth/plugins/llm/azure_multi_query.py`
- Delete: `src/elspeth/plugins/llm/openrouter_multi_query.py`

**Example YAML migration pattern:**
```yaml
# BEFORE
transforms:
  - plugin: azure_llm
    options:
      deployment_name: gpt-4
      endpoint: ${AZURE_OPENAI_ENDPOINT}
      api_key: ${AZURE_OPENAI_KEY}
      template: "Classify: {{ text }}"

# AFTER
transforms:
  - plugin: llm
    options:
      provider: azure
      deployment_name: gpt-4
      endpoint: ${AZURE_OPENAI_ENDPOINT}
      api_key: ${AZURE_OPENAI_KEY}
      template: "Classify: {{ text }}"
```

For multi-query examples, the config structure changes more significantly (case_studies/criteria → queries dict).

**Example files to update (16 total):**
- `examples/azure_openai_sentiment/settings.yaml` — azure_llm → llm+azure
- `examples/azure_openai_sentiment/settings_pooled.yaml`
- `examples/azure_blob_sentiment/settings.yaml`
- `examples/azure_blob_sentiment/settings_pooled.yaml`
- `examples/openrouter_sentiment/settings.yaml` — openrouter_llm → llm+openrouter
- `examples/openrouter_sentiment/settings_pooled.yaml`
- `examples/multi_query_assessment/settings.yaml` — azure_multi_query_llm → llm+azure+queries
- `examples/openrouter_multi_query_assessment/settings.yaml` — openrouter_multi_query_llm → llm+openrouter+queries
- `examples/openrouter_multi_query_assessment/settings_overflow.yaml`
- `examples/openrouter_multi_query_assessment/settings_stress.yaml`
- `examples/openrouter_multi_query_assessment/settings_journal.yaml`
- `examples/chaosllm_sentiment/settings.yaml`
- `examples/chaosllm_endurance/settings.yaml`
- `examples/rate_limited_llm/settings.yaml`
- `examples/schema_contracts_llm_assessment/settings.yaml`
- `examples/template_lookups/settings.yaml`

**After updating examples, delete old files:**
1. Delete the 5 old transform files
2. Verify no imports remain: `rg "from elspeth.plugins.llm.azure import" src/` (should only find batch)
3. Verify no imports remain: `rg "from elspeth.plugins.llm.openrouter import" src/` (should only find batch)
4. Verify no imports remain: `rg "from elspeth.plugins.llm.base_multi_query import" src/`

**Step N: Run full suite one final time**

Run: `.venv/bin/python -m pytest tests/ -x --tb=short -q`
Run: `.venv/bin/python -m mypy src/`
Run: `.venv/bin/python -m ruff check src/`
Run: `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`

**Step N+1: Commit**

```
refactor(llm): delete 5 old transform files, update 16 example YAMLs

Removes azure.py, openrouter.py, base_multi_query.py, azure_multi_query.py,
openrouter_multi_query.py. All functionality is now in transform.py with
providers/azure.py and providers/openrouter.py.

Net: ~3,400 lines deleted, ~720 created. ~2,700 line reduction.
```

---

## Verification Checklist

After all tasks complete:

- [ ] `.venv/bin/python -m pytest tests/ -x -q` — all tests pass
- [ ] `.venv/bin/python -m mypy src/` — no new errors
- [ ] `.venv/bin/python -m ruff check src/` — clean
- [ ] `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model` — pass
- [ ] `.venv/bin/python -m scripts.check_contracts` — pass
- [ ] `rg "azure_llm\|openrouter_llm\|azure_multi_query_llm\|openrouter_multi_query_llm" src/ examples/` — only batch refs or helpful error strings
- [ ] No `from elspeth.plugins.llm.azure import` in src/ (except batch files)
- [ ] No `from elspeth.plugins.llm.openrouter import` in src/ (except batch files)
- [ ] LLM test count >= 392 (no tests dropped)
- [ ] All 16 example YAMLs use `plugin: llm` with `provider:` field
