# T10: LLM Plugin Consolidation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Collapse 6 LLM transform classes (~4,950 lines) into a unified LLMTransform with LLMProvider protocol, eliminating ~3,300 lines of duplication.

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

**Note on tracing method variations (from reality check):**
- `openrouter_multi_query.py`: has `_setup_langfuse_tracing` but NOT `_record_langfuse_trace`/`_record_langfuse_trace_for_error` — uses different tracing pattern
- `azure_multi_query.py`: has all three record methods but NOT `_flush_tracing` (inherited from `BaseMultiQueryTransform`)
- `azure_batch.py`: has `_record_langfuse_batch_job` (different from `_record_langfuse_trace`)
- Task 3 wiring must account for these per-file variations

**Step 1: Write failing tests for LangfuseTracer**

Test file: `tests/unit/plugins/llm/test_langfuse_tracer.py`

Tests to write:
- `test_create_with_langfuse_config_returns_active_tracer` — mock Langfuse import, verify ActiveLangfuseTracer returned
- `test_create_with_non_langfuse_config_returns_noop` — pass AzureAITracingConfig, verify NoOpLangfuseTracer
- `test_create_with_none_config_returns_noop` — pass None, verify NoOpLangfuseTracer
- `test_create_langfuse_not_installed_logs_warning_returns_noop` — simulate ImportError, verify warning logged, returns NoOpLangfuseTracer
- `test_record_success_creates_span_and_generation` — mock client, verify nested context managers called with correct metadata
- `test_record_success_with_usage_updates_generation` — verify usage_details populated when usage.is_known
- `test_record_success_without_usage_skips_usage_details` — verify no usage_details when usage is None
- `test_record_error_sets_error_level` — verify level="ERROR" and status_message set
- `test_noop_tracer_record_success_is_silent` — verify NoOpLangfuseTracer.record_success does nothing
- `test_noop_tracer_record_error_is_silent` — verify NoOpLangfuseTracer.record_error does nothing
- `test_record_exception_logs_warning` — mock client that raises, verify structlog warning emitted (No Silent Failures — tracing failures go to structlog, not telemetry stream)
- `test_flush_calls_client_flush` — verify flush() delegated to client
- `test_flush_failure_logs_warning` — verify flush exception logged at warning level
- `test_flush_when_noop_is_silent`
- `test_noop_tracer_matches_protocol_signature` — verify NoOpLangfuseTracer has explicit parameter signatures (not *args/**kwargs), enabling mypy drift detection

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

Uses factory pattern to avoid mutable two-phase initialization. The factory
returns either an ActiveLangfuseTracer or NoOpLangfuseTracer — both frozen,
both satisfying the LangfuseTracer protocol.

Follows No Silent Failures: tracing failures are logged at warning level via
structlog. Tracing failures do NOT go to the ELSPETH telemetry stream because
TelemetryEmitCallback expects ExternalCallCompleted dataclass instances, and
tracing failures are a different event class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.llm.tracing import LangfuseTracingConfig, TracingConfig

if TYPE_CHECKING:
    from langfuse import Langfuse  # type: ignore[import-not-found,import-untyped]

logger = structlog.get_logger(__name__)


class LangfuseTracer(Protocol):
    """What the transform needs from tracing. Narrow interface."""

    def record_success(
        self,
        token_id: str,
        query_name: str,
        prompt: str,
        response_content: str,
        model: str,
        usage: TokenUsage | None = None,
        latency_ms: float | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None: ...

    def record_error(
        self,
        token_id: str,
        query_name: str,
        prompt: str,
        error_message: str,
        model: str,
        latency_ms: float | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None: ...

    def flush(self) -> None: ...


@dataclass(frozen=True, slots=True)
class NoOpLangfuseTracer:
    """No-op tracer for when Langfuse is not configured.

    Matches LangfuseTracer Protocol signatures exactly — enables mypy to
    catch signature drift between Protocol and implementations.
    """

    def record_success(
        self,
        token_id: str,
        query_name: str,
        prompt: str,
        response_content: str,
        model: str,
        usage: TokenUsage | None = None,
        latency_ms: float | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        pass

    def record_error(
        self,
        token_id: str,
        query_name: str,
        prompt: str,
        error_message: str,
        model: str,
        latency_ms: float | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        pass

    def flush(self) -> None:
        pass


@dataclass(frozen=True, slots=True)
class ActiveLangfuseTracer:
    """Fully-initialized Langfuse tracer. Immutable after construction."""

    transform_name: str
    client: Any  # Langfuse instance — typed as Any since it's an optional import

    def record_success(
        self,
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
        try:
            metadata = {"token_id": token_id, "plugin": self.transform_name, "query": query_name}
            if extra_metadata:
                metadata.update(extra_metadata)

            with (
                self.client.start_as_current_observation(
                    as_type="span",
                    name=f"elspeth.{self.transform_name}",
                    metadata=metadata,
                ),
                self.client.start_as_current_observation(
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
            _handle_trace_failure("langfuse_trace_failed", self.transform_name, e)

    def record_error(
        self,
        token_id: str,
        query_name: str,
        prompt: str,
        error_message: str,
        model: str,
        latency_ms: float | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record failed LLM call as Langfuse span + generation with ERROR level."""
        try:
            metadata = {"token_id": token_id, "plugin": self.transform_name, "query": query_name}
            if extra_metadata:
                metadata.update(extra_metadata)

            with (
                self.client.start_as_current_observation(
                    as_type="span",
                    name=f"elspeth.{self.transform_name}",
                    metadata=metadata,
                ),
                self.client.start_as_current_observation(
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
            _handle_trace_failure("langfuse_error_trace_failed", self.transform_name, e)

    def flush(self) -> None:
        """Flush pending tracing data."""
        try:
            self.client.flush()
        except Exception as e:
            _handle_trace_failure("langfuse_flush_failed", self.transform_name, e)


def _handle_trace_failure(
    event_name: str, transform_name: str, error: Exception,
) -> None:
    """Handle trace recording failure — No Silent Failures via structlog.

    Tracing failures go to structlog only, not the ELSPETH telemetry stream.
    TelemetryEmitCallback expects ExternalCallCompleted (from plugins/clients/base.py),
    which does not match tracing failure events.
    """
    logger.warning(
        "langfuse_trace_failed",
        event=event_name,
        plugin=transform_name,
        error=str(error),
        error_type=type(error).__name__,
    )


def create_langfuse_tracer(
    transform_name: str,
    tracing_config: TracingConfig | None,
) -> LangfuseTracer:
    """Factory: returns ActiveLangfuseTracer or NoOpLangfuseTracer.

    Fully constructs the tracer — no deferred setup() needed. The transform
    holds the returned object from __init__ through the entire lifecycle.
    """
    if tracing_config is None:
        return NoOpLangfuseTracer()
    if not isinstance(tracing_config, LangfuseTracingConfig):
        return NoOpLangfuseTracer()

    try:
        from langfuse import Langfuse  # type: ignore[import-not-found,import-untyped]

        client = Langfuse(
            public_key=tracing_config.public_key,
            secret_key=tracing_config.secret_key,
            host=tracing_config.host,
            tracing_enabled=tracing_config.tracing_enabled,
        )
        logger.info(
            "Langfuse tracing initialized (v3)",
            provider="langfuse",
            host=tracing_config.host,
            tracing_enabled=tracing_config.tracing_enabled,
        )
        return ActiveLangfuseTracer(transform_name=transform_name, client=client)
    except ImportError:
        logger.warning(
            "Langfuse tracing requested but package not installed",
            provider="langfuse",
            hint="Install with: uv pip install elspeth[tracing-langfuse]",
        )
        return NoOpLangfuseTracer()
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
- Test: `tests/unit/plugins/llm/test_validation.py` (create new — this file does not exist yet)

Four duplicated patterns to extract:
1. Template rendering error handling (4 instances across azure.py:434, openrouter.py:512, azure_multi_query.py:207, openrouter_multi_query.py:218)
2. Truncation detection (2 instances: azure_multi_query.py:284, openrouter_multi_query.py:346)
3. Markdown fence stripping (2 instances: azure_multi_query.py:330, openrouter_multi_query.py:367)
4. ~~OpenRouter HTTP response parsing~~ **Deferred to Phase B (Task 7).** The `parse_llm_json_response()` helper (~60 lines: NaN-safe JSON parse via `_reject_nonfinite_constant`, `choices[0]["message"]["content"]` extraction, null content check, usage normalization) is only needed by `OpenRouterLLMProvider`. Extracting it in Phase A would create an untested helper with no caller — implement it alongside the provider in Task 7 instead.

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
- `test_check_truncation_finish_reason_enum_length_returns_error` — verify FinishReason.LENGTH works (StrEnum == str)
- `test_check_truncation_token_heuristic_returns_error`
- `test_check_truncation_no_finish_reason_no_tokens_returns_none`
- `test_check_truncation_includes_preview_when_content_provided`
- `test_check_truncation_max_tokens_zero_returns_none` — verify max_tokens=0 does NOT spuriously trigger
- `test_strip_markdown_fences_removes_triple_backtick`
- `test_strip_markdown_fences_removes_language_tag`
- `test_strip_markdown_fences_noop_when_no_fences`
- `test_strip_markdown_fences_trailing_whitespace_after_closing_fence` — verify "```json\n{}\n``` " (trailing space) handled
- `test_strip_markdown_fences_no_closing_fence` — verify content after opening fence is still returned
- `test_strip_markdown_fences_no_newline_after_opening` — verify ` ```json ` with no body returns as-is
- ~~`test_parse_llm_json_response_*`~~ — **Deferred to Phase B Task 7** (see item 4 above)

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_validation.py -v -k "render_template or check_truncation or strip_markdown"`
Expected: FAIL — functions do not exist

**Step 3: Implement shared functions**

Add to `src/elspeth/plugins/llm/validation.py`:

```python
from typing import Any

from elspeth.contracts.token_usage import TokenUsage
from elspeth.contracts.errors import TransformErrorReason  # Use existing TypedDict — do NOT redefine
from elspeth.plugins.llm.templates import PromptTemplate, RenderedPrompt, TemplateError


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
    finish_reason: str | None,  # Accepts FinishReason (StrEnum) or raw str — StrEnum == str
    completion_tokens: int | None,
    prompt_tokens: int | None,
    max_tokens: int | None,
    query_name: str | None = None,
    content_preview: str | None = None,
) -> TransformErrorReason | None:
    """Check for response truncation. Returns error dict or None.

    Uses finish_reason as authoritative signal, falls back to token heuristic.
    Accepts both FinishReason enum and raw str (StrEnum comparison works with ==).
    Consolidates truncation detection from azure_multi_query.py and
    openrouter_multi_query.py.
    """
    is_truncated: bool
    if finish_reason is not None:
        is_truncated = finish_reason == "length"
    else:
        # Token heuristic fallback — guard against max_tokens=0 spurious trigger
        is_truncated = (
            max_tokens is not None
            and max_tokens > 0
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

    Consolidates identical logic from azure_multi_query.py and
    openrouter_multi_query.py.
    """
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    first_newline = stripped.find("\n")
    if first_newline != -1:
        stripped = stripped[first_newline + 1:]
    # Handle trailing whitespace before closing fence (e.g. "``` \n")
    if stripped.rstrip().endswith("```"):
        stripped = stripped.rstrip()
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

1. Add `from elspeth.plugins.llm.langfuse import create_langfuse_tracer`
2. In `__init__` or `on_start()`, replace `self._setup_langfuse_tracing()` with:
   ```python
   self._tracer = create_langfuse_tracer(
       transform_name=self.name,
       tracing_config=self._tracing_config,
       trace_logger=self._logger,
   )
   ```
3. Replace `_record_langfuse_trace()` calls with `self._tracer.record_success(...)`
4. Replace `_record_langfuse_trace_for_error()` calls with `self._tracer.record_error(...)`
5. Replace `_flush_tracing()` with `self._tracer.flush()`
6. Delete the 3-4 private methods that are now replaced

**Per-file variations to handle:**
- **azure.py, openrouter.py**: Standard pattern — `_setup_langfuse_tracing` + `_record_langfuse_trace` + `_record_langfuse_trace_for_error` + `_flush_tracing`. Straightforward replacement.
- **azure_multi_query.py**: Has all three record methods but NOT `_flush_tracing` (inherited from `BaseMultiQueryTransform`). Wire `_flush_tracing` through the inherited `on_complete`.
- **openrouter_multi_query.py**: Has `_setup_langfuse_tracing` but NOT `_record_langfuse_trace`/`_record_langfuse_trace_for_error` — uses a different tracing pattern. **WARNING: This alignment is a behavior change**, not just an extraction. Add a targeted tracing test (`test_openrouter_multi_query_tracing_after_alignment`) that verifies the aligned `record_success`/`record_error` calls produce correct Langfuse observations before committing Phase A.
- **azure_batch.py**: Has `_record_langfuse_batch_job` (different from `_record_langfuse_trace`). Leave batch-specific recording in place; only replace `_setup_langfuse_tracing` and `_flush_tracing`.
- **openrouter_batch.py**: Same batch consideration as azure_batch.py.

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
- `test_llm_query_result_fields` — verify content, usage, model, finish_reason fields (NO raw_response — providers own audit recording)
- `test_llm_query_result_post_init_rejects_empty_content` — verify `__post_init__` raises ValueError on `content=""`
- `test_llm_query_result_post_init_rejects_whitespace_content` — verify `__post_init__` raises ValueError on `content="   "` (whitespace-only is functionally empty)
- `test_llm_query_result_post_init_rejects_empty_model` — verify `__post_init__` raises ValueError on `model=""`
- `test_llm_query_result_post_init_rejects_whitespace_model` — verify `__post_init__` raises ValueError on `model="   "` (whitespace-only, same pattern as content validation)
- `test_finish_reason_enum_values` — verify stop, length, content_filter, tool_calls
- `test_finish_reason_from_string` — verify FinishReason("stop") works
- `test_parse_finish_reason_unknown_logs_warning` — verify unknown values like "end_turn" log a warning and return None (not silently dropped)
- `test_parse_finish_reason_empty_string_logs_warning` — verify `parse_finish_reason("")` logs warning and returns None (empty string is not a valid FinishReason)
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
6. Finish reason normalization (provider-specific → FinishReason enum)

The transform above the provider never sees raw SDK/HTTP responses.
raw_response is NOT on LLMQueryResult — providers record audit data
via their Audited*Client (D2 from architecture remediation).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

import structlog

from elspeth.contracts.token_usage import TokenUsage

logger = structlog.get_logger(__name__)


class FinishReason(StrEnum):
    """Validated finish reasons from LLM providers."""
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    TOOL_CALLS = "tool_calls"


def parse_finish_reason(raw: str | None) -> FinishReason | None:
    """Parse raw finish_reason string into validated enum.

    Unknown values log a warning and return None. This is intentional —
    providers have provider-specific finish reasons (e.g. Anthropic's
    "end_turn", "max_tokens") that we don't want to crash on, but we
    DO want visibility when new values appear.

    Providers should normalize their known finish reasons BEFORE calling
    this function (e.g. Anthropic "end_turn" → "stop").
    """
    if raw is None:
        return None
    try:
        return FinishReason(raw)
    except ValueError:
        logger.warning(
            "Unknown LLM finish_reason — not acting on it",
            finish_reason=raw,
            known_values=[e.value for e in FinishReason],
        )
        return None


@dataclass(frozen=True, slots=True)
class LLMQueryResult:
    """Normalized, validated result from any LLM provider.

    All Tier 3 validation has already happened inside the provider.
    Content is guaranteed non-null, non-empty, non-whitespace-only string.
    Usage is normalized via TokenUsage.known/unknown.

    NOTE: raw_response is NOT included here. Providers own audit recording
    via their Audited*Client (chat_completion/post methods record internally
    via their Landscape recorder) — the raw SDK/HTTP response stays within
    the provider boundary (D2 principle).
    """
    content: str
    usage: TokenUsage
    model: str
    finish_reason: FinishReason | None = None

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("LLMQueryResult.content must be non-empty (whitespace-only rejected)")
        if not self.model:
            raise ValueError("LLMQueryResult.model must be non-empty")


@runtime_checkable
class LLMProvider(Protocol):
    """What LLMTransform needs from a provider. Narrow interface.

    Providers raise typed exceptions from elspeth.plugins.clients.llm:
    - RateLimitError: 429 / rate limit (retryable)
    - NetworkError: connection failures (retryable)
    - ServerError: 5xx errors (retryable)
    - ContentPolicyError: content filtering (not retryable)
    - LLMClientError: other failures (not retryable)

    Note: LLMClientError (exception in plugins/clients/llm.py) is NOT the
    same as LLMCallError (frozen dataclass in contracts/call_data.py for
    audit recording). Providers RAISE LLMClientError; they RECORD LLMCallError.
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
- Client caching is per-state_id with threading.Lock (matches azure.py:446-470). **Note:** `azure_multi_query.py` uses a two-lock pattern (raw SDK client + audited wrapper). Determine at implementation time whether the unified provider needs one or two levels of caching.
- **CRITICAL: `state_id` snapshot bug.** `azure.py:453` correctly snapshots `state_id` before the try block because `ctx.state_id` is mutable during retries. `openrouter.py:693` uses `ctx.state_id` directly in the finally block (buggy). The unified provider MUST use the Azure pattern: `snapshot_state_id = state_id` at method entry, use `snapshot_state_id` in all subsequent code including error/finally paths.
- Error classification already happens inside AuditedLLMClient (llm.py:322-390)
- The provider re-raises the same typed exceptions (RateLimitError, ContentPolicyError, etc.)
- Azure AI tracing auto-instrumentation is set up in `on_start()`, NOT in provider `__init__`. The provider creates transport; tracing config belongs to the transform lifecycle.
- **Finish reason normalization happens here** at the Tier 3 boundary: Azure returns standard OpenAI finish_reason values ("stop", "length", "content_filter"), so `parse_finish_reason()` should handle them directly. If Azure introduces new values, they'll be logged and returned as None.
- raw_response stays within the provider — it is recorded internally by `AuditedLLMClient.chat_completion()` via its Landscape recorder, NOT passed into LLMQueryResult

**Tests:**
- `test_execute_query_returns_llm_query_result` — mock AuditedLLMClient, verify correct mapping, verify NO raw_response field
- `test_execute_query_maps_finish_reason` — verify FinishReason enum conversion
- `test_execute_query_unknown_finish_reason_returns_none` — verify provider-specific value (e.g. "end_turn") yields `finish_reason=None` on result
- `test_execute_query_propagates_rate_limit_error` — verify RateLimitError passes through
- `test_execute_query_propagates_content_policy_error`
- `test_execute_query_timeout` — verify httpx.TimeoutException → NetworkError mapping
- `test_client_cached_per_state_id` — verify same state_id returns same client
- `test_concurrent_client_creation_same_state_id` — 50 threads racing to create a client for the same state_id, verify exactly one client instance created (mirrors existing `TestAzureClientThreadSafety` pattern)
- `test_state_id_snapshot_used_not_mutable_ref` — mutate `state_id` parameter after `execute_query()` begins, verify the provider uses the original snapshot value in audit recording and client cache (prevents the openrouter.py bug where `ctx.state_id` was read in `finally` block)
- `test_close_clears_clients`
- `test_azure_ai_tracing_setup_in_on_start` — verify _configure_azure_monitor called in lifecycle, not provider init

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
- JSON parsing with `reject_nonfinite_constant` from validation.py
- Content extraction: `data["choices"][0]["message"]["content"]` with validation wrapping
- Null content check → ContentPolicyError
- Non-finite usage validation
- HTTP status code → typed exception mapping (429→RateLimitError, 5xx→ServerError, non-429 4xx→LLMClientError)
- Uses AuditedHTTPClient for audit recording
- **Finish reason normalization:** OpenRouter passes through the upstream provider's finish_reason. Some models return non-standard values. The provider calls `parse_finish_reason()` which logs unknown values and returns None.
- raw_response stays within the provider — it is recorded internally by `AuditedHTTPClient.post()` via its Landscape recorder, NOT passed into LLMQueryResult

**Tests (use ChaosLLM fixtures from conftest):**
- `test_execute_query_parses_json_response` — mock HTTP, verify LLMQueryResult fields, verify NO raw_response
- `test_execute_query_rejects_nan_in_response` — verify NaN/Infinity rejected
- `test_execute_query_rejects_null_content` — verify ContentPolicyError raised
- `test_execute_query_rejects_non_string_content` — verify LLMClientError raised (NOT LLMCallError — that's a dataclass for audit)
- `test_execute_query_validates_usage_non_finite` — verify non-finite usage values rejected
- `test_execute_query_unknown_finish_reason` — verify provider-specific value yields `finish_reason=None` and logs warning
- `test_execute_query_429_raises_rate_limit_error` — mock 429 response
- `test_execute_query_500_raises_server_error` — mock 5xx response
- `test_execute_query_network_error_raises_network_error` — mock connection failure
- `test_execute_query_timeout_raises_network_error` — mock httpx.TimeoutException
- `test_execute_query_4xx_raises_llm_client_error` — mock non-429 4xx (uses LLMClientError, not LLMCallError)
- `test_client_cached_per_state_id`
- `test_concurrent_client_creation_same_state_id` — 50 threads racing to create a client for the same state_id, verify exactly one client instance created
- `test_state_id_snapshot_used_not_mutable_ref` — mutate `state_id` parameter after `execute_query()` begins, verify the provider uses the original snapshot value in audit recording and client cache (prevents the openrouter.py bug where `ctx.state_id` was read in `finally` block)
- `test_execute_query_empty_choices_raises` — mock HTTP response with `choices=[]` (empty list), verify LLMClientError raised (distinct from null content)
- `test_close_clears_clients`

**Note:** Task 6 and Task 7 test fixtures should use explicit `model="gpt-4o"` in provider config dicts rather than relying on `LLMConfig.model` being required, since Task 8 changes `model` to optional. This prevents test breakage when Task 8 runs.

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
    provider: Literal["azure", "openrouter"] = Field(..., description="LLM provider")
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

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("QuerySpec.name must be non-empty")
        if not self.input_fields:
            raise ValueError("QuerySpec.input_fields must be non-empty")
```

Remove: `CaseStudyConfig`, `CriterionConfig`, `MultiQueryConfigMixin`, `MultiQueryConfig`, `validate_multi_query_key_collisions`

Add: `QuerySpecBody` (Pydantic model for dict-keyed config parsing), `resolve_queries()` function (normalizes list|dict to list[QuerySpec])

**`resolve_queries()` validation requirements:**
1. Raise `ValueError` if `queries` list is empty (no-op transforms are bugs)
2. Detect output field key collisions across queries (e.g. two queries both producing `score` field)
3. Warn on reserved output suffixes (`_error`, `_metadata`, `_raw`) that conflict with ELSPETH internals
4. Return `list[QuerySpec]` — single query returns a 1-element list (MultiQueryStrategy still applies if `queries` was explicitly configured)
5. Scan template strings for old positional pattern `{{ input_\d+ }}` and raise `ValueError` with migration-specific message: "Template uses positional variables ({{ input_1 }}). Migrate to named variables matching input_fields keys."

**Schema change note for `model` field:**
The `model` field on `LLMConfig` changes from `model: str` (required) to `model: str | None = None` (optional). This is because Azure uses `deployment_name` instead. Provider-specific config classes (`AzureOpenAIConfig`, `OpenRouterConfig`) enforce their own requirements:
- `AzureOpenAIConfig`: `deployment_name: str` (required), `model: None` (defaults, ignored)
- `OpenRouterConfig`: `model: str` (required — validates non-None in its own validator)

Test fixtures for multi-query tests need updating for this schema change.

**`template` field stays required on `LLMConfig`.**
Multi-query transforms use a single shared template rendered with different context per query (via `QuerySpec.build_template_context()`). The `QuerySpec.template` field is for per-query template overrides only — the shared `LLMConfig.template` remains the base. Both single-query and multi-query modes require a template.

**`tracing` field placement:**
The `tracing: dict[str, Any] | None` field currently lives on both `AzureOpenAIConfig` and `OpenRouterConfig` independently (duplicated). It stays on provider-specific configs — NOT moved to `LLMConfig` base — because Azure supports both `azure_ai` and `langfuse` tracing while OpenRouter only supports `langfuse` (azure_ai auto-instruments the OpenAI SDK which OpenRouter doesn't use). Provider-specific validation can enforce this constraint.

Provider-specific config:
```python
class AzureOpenAIConfig(LLMConfig):
    deployment_name: str
    endpoint: str
    api_key: str
    api_version: str = "2024-10-21"
    tracing: dict[str, Any] | None = None  # azure_ai or langfuse

class OpenRouterConfig(LLMConfig):
    api_key: str
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 60.0
    tracing: dict[str, Any] | None = None  # langfuse only (azure_ai not supported)
```

These can live in the provider files or a shared `configs.py` — decide during implementation based on import dependencies.

**Batch config impact:** `OpenRouterBatchConfig` (in `openrouter_batch.py`) inherits from `LLMConfig` and requires `model` to be non-None. Since batch files are NOT part of this consolidation, Task 8 must add an explicit `model: str` field override on `OpenRouterBatchConfig` to preserve its existing validation. Add test: `test_openrouter_batch_config_rejects_none_model`.

**Tests:**
- Existing config validation tests need migration
- `test_query_spec_post_init_rejects_empty_name` — verify ValueError on `name=""`
- `test_query_spec_post_init_rejects_empty_input_fields` — verify ValueError on `input_fields={}`
- `test_resolve_queries_empty_list_raises` — verify ValueError("no queries configured")
- `test_resolve_queries_empty_dict_raises` — verify ValueError("no queries configured") when `queries={}` (empty dict normalizes to empty list)
- `test_resolve_queries_key_collision_raises` — two queries producing same output field
- `test_resolve_queries_reserved_suffix_warns` — query producing `_error` suffix logs warning
- `test_resolve_queries_dict_to_list` — verify dict-keyed config normalizes to list[QuerySpec]
- `test_resolve_queries_single_query_returns_one_element_list`
- `test_azure_config_requires_deployment_name` — verify AzureOpenAIConfig validation
- `test_openrouter_config_requires_model` — verify OpenRouterConfig validates non-None model
- `test_base_llm_config_model_optional` — verify `model: str | None = None` on base LLMConfig
- `test_openrouter_batch_config_rejects_none_model` — verify `OpenRouterBatchConfig(model=None, ...)` raises ValidationError
- `test_resolve_queries_rejects_positional_template_variables` — template with `{{ input_1 }}` raises ValueError with migration guidance message

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

`LLMTransform` extends `BatchTransformMixin` (D8). All existing LLM transforms
use `accept()`/`connect_output()`/`flush_batch_processing()`, NOT `process()`.
Strategies are called from `_process_row()`, preserving concurrent row
processing with FIFO output ordering and backpressure.

`LLMTransform.__init__` dispatches provider:
```python
# NOTE: type[LLMProvider] won't work for concrete classes implementing a Protocol.
# Use Callable[..., LLMProvider] or just omit the type annotation and let mypy
# infer from usage. The concrete classes are structurally compatible.
_PROVIDERS: dict[str, tuple[type[LLMConfig], Any]] = {
    "azure": (AzureOpenAIConfig, AzureLLMProvider),
    "openrouter": (OpenRouterConfig, OpenRouterLLMProvider),
}

class LLMTransform(BaseTransform, BatchTransformMixin):
    name = "llm"
    determinism = Determinism.NON_DETERMINISTIC

    def __init__(self, config: dict[str, Any]) -> None:
        provider_name = config["provider"]
        if provider_name not in _PROVIDERS:
            raise ValueError(
                f"Unknown LLM provider '{provider_name}'. "
                f"Valid providers: {sorted(_PROVIDERS)}"
            )
        config_cls, provider_cls = _PROVIDERS[provider_name]
        # Parse config with provider-specific model
        self._config = config_cls.from_dict(config)
        self._provider = provider_cls(self._config, ...)
        # Factory returns frozen ActiveLangfuseTracer or NoOpLangfuseTracer
        # tracing lives on provider-specific configs (AzureOpenAIConfig, OpenRouterConfig),
        # both of which define tracing: dict[str, Any] | None. Since config_cls is always
        # one of those two, self._config.tracing is always present. No defensive getattr.
        tracing_config = parse_tracing_config(self._config.tracing) if self._config.tracing else None
        self._tracer = create_langfuse_tracer(
            transform_name=self.name,
            tracing_config=tracing_config,
        )
        self._query_specs = resolve_queries(self._config)
        self._strategy = (
            MultiQueryStrategy(...) if self._config.queries is not None
            else SingleQueryStrategy(...)
        )
```

Strategy selection: if `queries` is explicitly provided (even with one entry), use MultiQueryStrategy. Otherwise SingleQueryStrategy. This preserves explicit intent. Uses `is not None` (not truthiness) per project convention.

**Single provider registry:** Both `_get_transform_config_model()` and `__init__()` read from `_PROVIDERS`, eliminating the sync failure mode of two independent dispatch tables.

**Note on `PluginContext.llm_client`:** After T10, providers own their own client lifecycle (D2). `LLMTransform._process_row()` MUST NOT read `ctx.llm_client`. The executor may still set it (it doesn't know the transform's internals), but it is unused. A test (`test_llm_transform_does_not_use_ctx_llm_client`) verifies this with a sentinel. Removing `ctx.llm_client` from the executor path is deferred to T17.

**Tests (using ChaosLLM fixtures):**
- Single-query tests: verify LLMTransform(provider="azure") with no queries works as single-query
- Multi-query tests: verify LLMTransform(provider="openrouter", queries=...) uses multi-query strategy
- `test_strategy_type_is_multi_query_when_queries_provided` — assert `isinstance(transform._strategy, MultiQueryStrategy)` to catch strategy dispatch bugs
- `test_strategy_type_is_single_query_when_no_queries` — assert `isinstance(transform._strategy, SingleQueryStrategy)`
- Provider dispatch: verify "azure" creates AzureLLMProvider, "openrouter" creates OpenRouterLLMProvider
- Unknown provider: verify helpful error message listing valid providers
- Error handling: verify all exception types map to correct TransformResult (RateLimitError→retryable, NetworkError→retryable, ServerError→retryable, ContentPolicyError→not retryable, ContextLengthError→not retryable, LLMClientError→not retryable)
- `test_error_classification_context_length_error` — verify ContextLengthError maps to non-retryable TransformResult with reason "context_length_exceeded" (5th exception type from `plugins/clients/llm.py`, currently missing from the plan)
- Contract propagation: verify single-query uses propagate_contract, multi-query builds OBSERVED
- Truncation: verify truncated responses (finish_reason=LENGTH) return error
- Fence stripping: verify markdown fences stripped in STANDARD mode
- `test_tracer_is_noop_when_no_tracing_config` — verify NoOpLangfuseTracer used
- `test_tracer_is_active_when_langfuse_configured` — verify ActiveLangfuseTracer used
- `test_multi_query_partial_failure_discards_successful_results` — mock 4 queries where query 3 raises LLMClientError, verify TransformResult is error and output row has NO fields from successful queries (audit integrity)
    The error reason dict MUST include: (a) which query failed (name + index), (b) the failure detail, and (c) how many queries succeeded but were discarded. This enables operators to distinguish "1 of 10 failed" from "9 of 10 failed" in quarantine investigation.
- `test_llm_transform_does_not_use_ctx_llm_client` — set ctx.llm_client to sentinel that raises on access, verify transform processes row successfully via provider's own client
- `test_llm_transform_uses_process_row_not_process` — verify LLMTransform extends BatchTransformMixin and _process_row is the entry point (D8)

**Config test file:** New config tests from Task 8 (QuerySpec validation, resolve_queries, provider configs) should live in `tests/unit/plugins/llm/test_llm_config.py`.

**Step N: Commit**

```
feat(llm): unified LLMTransform with SingleQuery/MultiQuery strategies
```

---

### Task 10: Update plugin registration and validation

**Files:**
- Modify: `src/elspeth/plugins/validation.py` — update `_get_transform_config_model()` for "llm" plugin
- Modify: `src/elspeth/plugins/discovery.py` — verify llm/ directory still scanned correctly
- Test: `tests/unit/plugins/llm/test_plugin_registration.py` (create new or extend existing discovery tests)

**Tests:**
- `test_llm_plugin_dispatches_to_azure_config` — verify `_get_transform_config_model("llm", {"provider": "azure"})` returns `AzureOpenAIConfig`
- `test_llm_plugin_dispatches_to_openrouter_config` — verify `_get_transform_config_model("llm", {"provider": "openrouter"})` returns `OpenRouterConfig`
- `test_llm_plugin_missing_provider_falls_back_to_base` — verify missing `provider` key returns `LLMConfig` (Pydantic catches the Literal validation)
- `test_old_plugin_names_raise_helpful_error` — verify `azure_llm`, `openrouter_llm` etc. raise ValueError with migration guidance

**Key changes in validation.py:**

Replace the 4 deleted plugin entries:
```python
# BEFORE (lines 262-282):
elif transform_type == "azure_llm": ...
elif transform_type == "azure_multi_query_llm": ...
elif transform_type == "openrouter_llm": ...
elif transform_type == "openrouter_multi_query_llm": ...

# AFTER — uses shared _PROVIDERS registry from transform.py:
elif transform_type == "llm":
    from elspeth.plugins.llm.transform import _PROVIDERS

    # Read provider field to select correct config class
    provider = config.get("provider") if isinstance(config, dict) else None
    if provider in _PROVIDERS:
        config_cls, _ = _PROVIDERS[provider]
        return config_cls
    elif provider is not None:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            f"Valid providers: {sorted(_PROVIDERS)}"
        )
    else:
        # provider missing entirely — let Pydantic catch it with Literal validation
        from elspeth.plugins.llm.base import LLMConfig
        return LLMConfig
```

**Why provider-dispatch matters:** Without this, `_get_transform_config_model()` returns the base `LLMConfig` which lacks provider-specific required fields (`deployment_name`, `endpoint`). Pydantic validation would pass with missing fields, and the error would surface later at instantiation with a confusing traceback.

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

**Unit tests (`tests/unit/plugins/llm/`):**

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

**Contract tests (`tests/unit/contracts/`):**

| Test File | Current Import | New Import | Migration Type |
|-----------|---------------|-----------|----------------|
| transform_contracts/test_azure_multi_query_contract.py | AzureMultiQueryLLMTransform | LLMTransform(provider="azure", queries=...) | Instantiation + config |
| test_telemetry_contracts.py | Multiple transforms | LLMTransform | Instantiation change |

**Property tests (`tests/property/plugins/llm/`):**

| Test File | Migration Type |
|-----------|----------------|
| test_multi_query_properties.py | Update to domain-agnostic QuerySpec (case_studies/criteria → queries) |
| Any hypothesis tests referencing old class names | Update strategies to use LLMTransform |

**Integration tests (`tests/integration/plugins/llm/`):**

| Test File | Migration Type |
|-----------|----------------|
| `tests/unit/telemetry/test_plugin_wiring.py` | Verify "llm" plugin wires correctly (NOTE: actual location is `tests/unit/telemetry/`, not `tests/integration/plugins/llm/`) |
| test_llm_integration.py (if exists) | Update instantiation |
| `tests/integration/plugins/llm/test_multi_query.py` | Update instantiation to LLMTransform(provider=..., queries=...) |
| `tests/integration/plugins/llm/test_contract_validation.py` | Verify — may reference old class names |

**Performance tests:**

| Test File | Migration Type |
|-----------|----------------|
| test_llm_retry.py (stress) | via stress conftest factory update |

**Other:**

| Test File | Migration Type |
|-----------|----------------|
| test_assert_to_raise.py | AzureOpenAIConfig import path change (from providers/azure.py, not llm/base.py) |
| `tests/unit/plugins/test_assert_to_raise.py` | Rewrite — imports `AzureLLMTransform` and tests `_get_llm_client()` which no longer exists; needs full test rewrite |

**NOTE:** Before implementation, verify these paths actually exist. During the review, 3 paths were flagged as potentially wrong:
- `test_azure_multi_query_contract.py` — verify exact location (could be `tests/unit/plugins/llm/` or `tests/unit/contracts/`)
- `test_telemetry_contracts.py` — verify exact location
- `test_plugin_wiring.py` — verify exact location (could be `tests/integration/` or `tests/unit/`)

Run `find tests/ -name "*llm*" -o -name "*multi_query*" -o -name "*plugin_wiring*" | sort` to build the definitive list at implementation time.

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

**Rollback criterion:** If any batch fails to pass `pytest tests/unit/plugins/llm/ tests/integration/plugins/llm/ -x`, revert that batch's changes before proceeding to the next batch. Old class names still exist (Task 12 deletes them), so reverting test changes to a batch restores a passing state.

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

**Template variable migration:**
Single-query templates use Jinja2 variables that reference row fields directly (e.g., `{{ text }}`, `{{ customer_id }}`). These DO NOT change — single-query templates are unaffected.

Multi-query templates need migration from positional `{{ input_1 }}` to named variables matching the `input_fields` mapping:

```yaml
# BEFORE (multi-query with case_studies)
transforms:
  - plugin: azure_multi_query_llm
    options:
      case_studies:
        - name: cs1
          input_fields: [text, category]
      criteria:
        - name: quality
          description: "Rate the quality"
      template: "Evaluate {{ input_1 }} in category {{ input_2 }}"

# AFTER (multi-query with queries dict)
transforms:
  - plugin: llm
    options:
      provider: azure
      deployment_name: gpt-4
      endpoint: ${AZURE_OPENAI_ENDPOINT}
      api_key: ${AZURE_OPENAI_KEY}
      queries:
        cs1_quality:
          input_fields:
            text_content: text      # template var: row field
            category_name: category
          response_format: standard
          output_fields:
            - suffix: score
              type: integer
          template: "Evaluate {{ text_content }} in category {{ category_name }}"
```

Note how `{{ input_1 }}` → `{{ text_content }}` and `{{ input_2 }}` → `{{ category_name }}` — the template variables now match the keys in `input_fields`, making templates self-documenting.

**Template variable safety:** Verify that `PromptTemplate` uses Jinja2's `StrictUndefined` policy so that un-migrated templates referencing `{{ input_1 }}` raise `TemplateError` rather than silently rendering as empty string. Add a test: `test_template_with_undeclared_variable_raises_error`.

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

**Documentation files to update (8 files, 33 references):**
- `docs/guides/tier2-tracing.md` — 17 refs (provider comparison table needs full rewrite)
- `docs/runbooks/configure-keyvault-secrets.md` — 3 refs
- `docs/guides/user-manual.md` — 3 refs
- `docs/guides/troubleshooting.md` — 2 refs
- `docs/reference/environment-variables.md` — 4 refs
- `docs/reference/configuration.md` — 4 refs
- `ARCHITECTURE.md` — component name references
- Example `README.md` files in examples directories

**After updating examples and docs, delete old files:**
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
refactor(llm): delete 5 old transform files, update 16 example YAMLs + 8 doc files

Removes azure.py, openrouter.py, base_multi_query.py, azure_multi_query.py,
openrouter_multi_query.py. All functionality is now in transform.py with
providers/azure.py and providers/openrouter.py.

Net: ~4,200 lines deleted, ~900 created. ~3,300 line reduction.
```

---

## Verification Checklist

After all tasks complete:

- [ ] `.venv/bin/python -m pytest tests/ -x -q` — all tests pass
- [ ] `.venv/bin/python -m mypy src/` — no new errors
- [ ] `.venv/bin/python -m ruff check src/` — clean
- [ ] `.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model` — pass
- [ ] `.venv/bin/python -m scripts.check_contracts` — pass
- [ ] `rg "azure_llm\|openrouter_llm\|azure_multi_query_llm\|openrouter_multi_query_llm" src/ examples/ docs/` — only batch refs or helpful error strings
- [ ] No `from elspeth.plugins.llm.azure import` in src/ (except batch files)
- [ ] No `from elspeth.plugins.llm.openrouter import` in src/ (except batch files)
- [ ] LLM test count >= 520 (original 392 + ~128 new tests from Tasks 1, 2, 5, 6, 7, 8, 9)
- [ ] All 16 example YAMLs use `plugin: llm` with `provider:` field
- [ ] No `raw_response` on LLMQueryResult anywhere in src/ or tests/
- [ ] No `LLMCallError` used as a raiseable exception (only `LLMClientError` from `plugins/clients/llm`)
- [ ] No local `TransformErrorReason` redefinitions (only imported from `contracts.errors`)
- [ ] `parse_finish_reason()` logs unknown values (verify with test)
- [ ] `create_langfuse_tracer()` factory used everywhere (no manual `LangfuseTracer(...)` construction)
- [ ] QuerySpec `__post_init__` validation covers empty name and empty input_fields
- [ ] `resolve_queries()` rejects empty list, empty dict, and detects key collisions
- [ ] `LLMTransform` extends `BatchTransformMixin` — strategies called from `_process_row()`, not `process()`
- [ ] `LLMTransform._process_row()` does NOT read `ctx.llm_client` (sentinel test passes)
- [ ] `NoOpLangfuseTracer` has explicit parameter signatures matching Protocol (no `*args/**kwargs`)
- [ ] No `telemetry_emit` parameter on `LangfuseTracer` methods (tracing failures go to structlog only)
- [ ] `LLMQueryResult.__post_init__` rejects whitespace-only content (`"   "`)
- [ ] `provider` field on `LLMConfig` uses `Literal["azure", "openrouter"]`, not `str`
- [ ] `_PROVIDERS` registry is single dict used by both `_get_transform_config_model()` and `__init__()`
- [ ] `state_id` is snapshot before try block in providers (Azure pattern, not OpenRouter buggy pattern)
- [ ] `PromptTemplate` uses `StrictUndefined` — un-migrated `{{ input_1 }}` raises `TemplateError`
- [ ] All 8 doc files updated (33 old plugin name references removed)
- [ ] `MultiQueryStrategy` traces per-query only (D9) — no row-level aggregate traces
- [ ] `test_multi_query_partial_failure_discards_successful_results` passes
- [ ] `test_openrouter_multi_query_tracing_after_alignment` passes (Phase A behavior change verified)
- [ ] `ContextLengthError` maps to non-retryable `TransformResult` with reason "context_length_exceeded"
- [ ] `LLMTransform.close()` calls `self._provider.close()` and `self._tracer.flush()` (provider lifecycle)
- [ ] `src/elspeth/plugins/llm/providers/__init__.py` exists (package is properly registered)
- [ ] `.venv/bin/python scripts/cicd/enforce_tier_model.py check` passes after Task 9 (not just after Task 12)
- [ ] `rg "_langfuse_client|isinstance.*ActiveLangfuseTracer" src/` returns no matches after Task 12 (bridge code fully removed)
- [ ] `rg "AzureLLMTransform|OpenRouterLLMTransform|AzureMultiQueryLLMTransform|OpenRouterMultiQueryLLMTransform" tests/` returns only helpful-error test strings after Task 11
- [ ] `resolve_queries()` rejects templates with positional `{{ input_\d+ }}` variables (migration safety)
- [ ] Concurrent client creation test passes for both providers (race condition on first-access)
- [ ] `state_id` snapshot test passes for both providers (not mutable ref)
