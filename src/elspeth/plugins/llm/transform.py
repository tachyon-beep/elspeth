# src/elspeth/plugins/llm/transform.py
"""Unified LLM transform with strategy pattern (Task 9 of T10).

LLMTransform dispatches to SingleQueryStrategy or MultiQueryStrategy
based on whether queries are configured. Provider dispatch (Azure,
OpenRouter) is handled via _PROVIDERS registry.

Architecture:
    LLMTransform (BatchTransformMixin)
        ├── SingleQueryStrategy — direct template render, raw content output
        └── MultiQueryStrategy — mapped context, JSON parsing, field extraction

    Provider instantiation is deferred to on_start() when recorder/telemetry
    become available. __init__ stores provider_cls + config for later use.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast

import structlog

from elspeth.contracts import Determinism, TransformErrorReason, TransformResult, propagate_contract
from elspeth.contracts.contexts import LifecycleContext, TransformContext
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.batching import BatchTransformMixin, OutputPort
from elspeth.plugins.clients.llm import ContextLengthError, LLMClientError
from elspeth.plugins.llm import (
    _build_augmented_output_schema,
    get_llm_audit_fields,
    get_llm_guaranteed_fields,
    populate_llm_metadata_fields,
)
from elspeth.plugins.llm.base import LLMConfig
from elspeth.plugins.llm.langfuse import LangfuseTracer, create_langfuse_tracer
from elspeth.plugins.llm.multi_query import QuerySpec, ResponseFormat, resolve_queries
from elspeth.plugins.llm.provider import FinishReason, LLMProvider
from elspeth.plugins.llm.providers.azure import AzureLLMProvider, AzureOpenAIConfig
from elspeth.plugins.llm.providers.openrouter import OpenRouterConfig, OpenRouterLLMProvider
from elspeth.plugins.llm.templates import PromptTemplate, TemplateError
from elspeth.plugins.llm.tracing import parse_tracing_config
from elspeth.plugins.llm.validation import reject_nonfinite_constant, strip_markdown_fences
from elspeth.plugins.schema_factory import create_schema_from_config

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Provider registry — single source of truth for both config parsing and
# provider instantiation. Eliminates the sync failure mode of two dispatch tables.
# ---------------------------------------------------------------------------

# NOTE: type[LLMProvider] won't work for concrete classes implementing a Protocol.
# The concrete classes are structurally compatible — mypy verifies this.
_PROVIDERS: dict[str, tuple[type[LLMConfig], Any]] = {
    "azure": (AzureOpenAIConfig, AzureLLMProvider),
    "openrouter": (OpenRouterConfig, OpenRouterLLMProvider),
}


# ---------------------------------------------------------------------------
# Strategy protocol and implementations
# ---------------------------------------------------------------------------


class QueryStrategy(Protocol):
    """What LLMTransform._process_row delegates to."""

    def execute(
        self,
        row: PipelineRow,
        ctx: TransformContext,
        *,
        provider: LLMProvider,
        tracer: LangfuseTracer,
    ) -> TransformResult: ...


@dataclass(frozen=True, slots=True)
class SingleQueryStrategy:
    """Direct template render → LLM call → raw content output."""

    template: PromptTemplate
    system_prompt: str | None
    system_prompt_source: str | None
    model: str
    temperature: float
    max_tokens: int | None
    response_field: str

    def execute(
        self,
        row: PipelineRow,
        ctx: TransformContext,
        *,
        provider: LLMProvider,
        tracer: LangfuseTracer,
    ) -> TransformResult:
        """Execute single LLM query and build output row."""
        state_id = ctx.state_id
        if state_id is None:
            raise RuntimeError("LLMTransform requires state_id")
        if ctx.token is None:
            raise RuntimeError("LLMTransform requires ctx.token")
        token_id = ctx.token.token_id

        # 1. Render template (THEIR DATA — wrap)
        try:
            rendered = self.template.render_with_metadata(row, contract=row.contract)
        except TemplateError as e:
            error_reason: TransformErrorReason = {
                "reason": "template_rendering_failed",
                "error": str(e),
                "template_hash": self.template.template_hash,
            }
            if self.template.template_source:
                error_reason["template_file_path"] = self.template.template_source
            return TransformResult.error(error_reason)

        # 2. Build messages
        messages: list[dict[str, str]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": rendered.prompt})

        # 3. Call provider (EXTERNAL — errors classified by provider)
        start_time = time.monotonic()
        try:
            result = provider.execute_query(
                messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                state_id=state_id,
                token_id=token_id,
            )
        except ContextLengthError as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            tracer.record_error(
                token_id=token_id,
                query_name="single",
                prompt=rendered.prompt,
                error_message=str(e),
                model=self.model,
                latency_ms=latency_ms,
            )
            return TransformResult.error(
                {"reason": "context_length_exceeded", "error": str(e)},
                retryable=False,
            )
        except LLMClientError as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            tracer.record_error(
                token_id=token_id,
                query_name="single",
                prompt=rendered.prompt,
                error_message=str(e),
                model=self.model,
                latency_ms=latency_ms,
            )
            if e.retryable:
                raise
            return TransformResult.error(
                {"reason": "llm_call_failed", "error": str(e)},
                retryable=False,
            )

        latency_ms = (time.monotonic() - start_time) * 1000

        # 4. Check truncation (finish_reason=LENGTH)
        if result.finish_reason == FinishReason.LENGTH:
            tracer.record_error(
                token_id=token_id,
                query_name="single",
                prompt=rendered.prompt,
                error_message="Response truncated (finish_reason=length)",
                model=self.model,
                latency_ms=latency_ms,
            )
            return TransformResult.error(
                {
                    "reason": "response_truncated",
                    "finish_reason": "length",
                    "content_length": len(result.content),
                },
                retryable=False,
            )

        # 5. Strip markdown fences
        content = strip_markdown_fences(result.content)

        # Record success in tracer
        tracer.record_success(
            token_id=token_id,
            query_name="single",
            prompt=rendered.prompt,
            response_content=content,
            model=self.model,
            usage=result.usage,
            latency_ms=latency_ms,
        )

        # 6. Build output row
        output = row.to_dict()
        output[self.response_field] = content
        populate_llm_metadata_fields(
            output,
            self.response_field,
            usage=result.usage,
            model=result.model,
            template_hash=rendered.template_hash,
            variables_hash=rendered.variables_hash,
            template_source=rendered.template_source,
            lookup_hash=rendered.lookup_hash,
            lookup_source=rendered.lookup_source,
            system_prompt_source=self.system_prompt_source,
        )

        # 7. Propagate contract
        output_contract = propagate_contract(
            input_contract=row.contract,
            output_row=output,
            transform_adds_fields=True,
        )

        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={"action": "enriched", "fields_added": [self.response_field]},
        )


@dataclass(frozen=True, slots=True)
class MultiQueryStrategy:
    """Execute multiple queries per row with atomic failure semantics."""

    query_specs: list[QuerySpec]
    template: PromptTemplate
    system_prompt: str | None
    system_prompt_source: str | None
    model: str
    temperature: float
    max_tokens: int | None
    response_field: str

    def execute(
        self,
        row: PipelineRow,
        ctx: TransformContext,
        *,
        provider: LLMProvider,
        tracer: LangfuseTracer,
    ) -> TransformResult:
        """Execute all queries, returning atomic success or failure."""
        state_id = ctx.state_id
        if state_id is None:
            raise RuntimeError("LLMTransform requires state_id")
        if ctx.token is None:
            raise RuntimeError("LLMTransform requires ctx.token")
        token_id = ctx.token.token_id

        # Collect results across all queries — atomic: all succeed or all fail
        accumulated_outputs: dict[str, Any] = {}

        for query_idx, spec in enumerate(self.query_specs):
            # Build template context from named input_fields
            try:
                template_ctx = spec.build_template_context(row)
            except KeyError as e:
                return TransformResult.error(
                    {
                        "reason": "template_context_failed",
                        "query_name": spec.name,
                        "query_index": query_idx,
                        "error": str(e),
                    },
                    retryable=False,
                )

            # Use per-query template if provided, else config-level template
            query_template = self.template
            if spec.template is not None:
                query_template = PromptTemplate(spec.template)

            # Render template
            try:
                rendered = query_template.render_with_metadata(
                    template_ctx,
                    contract=row.contract,
                )
            except TemplateError as e:
                return TransformResult.error(
                    {
                        "reason": "template_rendering_failed",
                        "query_name": spec.name,
                        "query_index": query_idx,
                        "error": str(e),
                        "template_hash": query_template.template_hash,
                        "discarded_successful_queries": query_idx,
                    },
                    retryable=False,
                )

            # Build messages
            messages: list[dict[str, str]] = []
            if self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})
            messages.append({"role": "user", "content": rendered.prompt})

            # Execute query
            query_max_tokens = spec.max_tokens or self.max_tokens

            # Build response_format for structured output requests
            response_format: dict[str, Any] | None = None
            if spec.output_fields:
                if spec.response_format == ResponseFormat.STRUCTURED:
                    # Build JSON Schema from output field definitions
                    properties = {f.suffix: f.to_json_schema() for f in spec.output_fields}
                    response_format = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": f"{spec.name}_output",
                            "schema": {
                                "type": "object",
                                "properties": properties,
                                "required": list(properties),
                            },
                        },
                    }
                else:
                    # STANDARD mode — model outputs JSON but no schema enforcement
                    response_format = {"type": "json_object"}

            start_time = time.monotonic()
            try:
                result = provider.execute_query(
                    messages,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=query_max_tokens,
                    state_id=state_id,
                    token_id=token_id,
                    response_format=response_format,
                )
            except ContextLengthError as e:
                latency_ms = (time.monotonic() - start_time) * 1000
                tracer.record_error(
                    token_id=token_id,
                    query_name=spec.name,
                    prompt=rendered.prompt,
                    error_message=str(e),
                    model=self.model,
                    latency_ms=latency_ms,
                )
                return TransformResult.error(
                    {
                        "reason": "context_length_exceeded",
                        "failed_query_name": spec.name,
                        "failed_query_index": query_idx,
                        "error": str(e),
                        "discarded_successful_queries": query_idx,
                    },
                    retryable=False,
                )
            except LLMClientError as e:
                latency_ms = (time.monotonic() - start_time) * 1000
                tracer.record_error(
                    token_id=token_id,
                    query_name=spec.name,
                    prompt=rendered.prompt,
                    error_message=str(e),
                    model=self.model,
                    latency_ms=latency_ms,
                )
                if e.retryable:
                    raise
                # Non-retryable: discard ALL accumulated results (atomic failure)
                return TransformResult.error(
                    {
                        "reason": "multi_query_failed",
                        "failed_query_name": spec.name,
                        "failed_query_index": query_idx,
                        "error": str(e),
                        "discarded_successful_queries": query_idx,
                    },
                    retryable=False,
                )

            latency_ms = (time.monotonic() - start_time) * 1000

            # Check truncation
            if result.finish_reason == FinishReason.LENGTH:
                tracer.record_error(
                    token_id=token_id,
                    query_name=spec.name,
                    prompt=rendered.prompt,
                    error_message="Response truncated (finish_reason=length)",
                    model=self.model,
                    latency_ms=latency_ms,
                )
                return TransformResult.error(
                    {
                        "reason": "response_truncated",
                        "query_name": spec.name,
                        "query_index": query_idx,
                        "finish_reason": "length",
                        "discarded_successful_queries": query_idx,
                    },
                    retryable=False,
                )

            # Strip fences and store content
            content = strip_markdown_fences(result.content)

            tracer.record_success(
                token_id=token_id,
                query_name=spec.name,
                prompt=rendered.prompt,
                response_content=content,
                model=self.model,
                usage=result.usage,
                latency_ms=latency_ms,
            )

            # JSON parsing + field extraction when output_fields configured
            if spec.output_fields:
                # LLM response content is Tier 3 — parse and validate immediately
                try:
                    parsed = json.loads(content, parse_constant=reject_nonfinite_constant)
                except (json.JSONDecodeError, ValueError) as e:
                    return TransformResult.error(
                        {
                            "reason": "json_parse_failed",
                            "query_name": spec.name,
                            "query_index": query_idx,
                            "error": str(e),
                            "raw_response_preview": content[:500],
                            "discarded_successful_queries": query_idx,
                        },
                        retryable=False,
                    )
                if not isinstance(parsed, dict):
                    return TransformResult.error(
                        {
                            "reason": "invalid_json_type",
                            "query_name": spec.name,
                            "query_index": query_idx,
                            "expected": "object",
                            "actual": type(parsed).__name__,
                            "discarded_successful_queries": query_idx,
                        },
                        retryable=False,
                    )
                # Extract typed fields into prefixed output columns
                for field in spec.output_fields:
                    field_key = f"{spec.name}_{field.suffix}"
                    accumulated_outputs[field_key] = parsed.get(field.suffix)
                # Also store raw content for audit traceability
                accumulated_outputs[f"{spec.name}_{self.response_field}"] = content
            else:
                # Unstructured: store raw content only
                accumulated_outputs[f"{spec.name}_{self.response_field}"] = content

            populate_llm_metadata_fields(
                accumulated_outputs,
                f"{spec.name}_{self.response_field}",
                usage=result.usage,
                model=result.model,
                template_hash=rendered.template_hash,
                variables_hash=rendered.variables_hash,
                template_source=rendered.template_source,
                lookup_hash=rendered.lookup_hash,
                lookup_source=rendered.lookup_source,
                system_prompt_source=self.system_prompt_source,
            )

        # All queries succeeded — build output row
        output = {**row.to_dict(), **accumulated_outputs}

        # Multi-query adds dynamic fields — propagate contract from input
        output_contract = propagate_contract(
            input_contract=row.contract,
            output_row=output,
            transform_adds_fields=True,
        )

        return TransformResult.success(
            PipelineRow(output, output_contract),
            success_reason={
                "action": "multi_query_enriched",
                "queries_completed": len(self.query_specs),
            },
        )


# ---------------------------------------------------------------------------
# LLMTransform — the unified plugin class
# ---------------------------------------------------------------------------


class LLMTransform(BaseTransform, BatchTransformMixin):
    """Unified LLM transform with provider dispatch and strategy selection.

    Registered as plugin name="llm". Uses BatchTransformMixin for concurrent
    row processing with FIFO output ordering and backpressure.

    Provider dispatch:
        "azure"      → AzureOpenAIConfig + AzureLLMProvider
        "openrouter" → OpenRouterConfig  + OpenRouterLLMProvider

    Strategy selection:
        queries is not None → MultiQueryStrategy
        queries is None     → SingleQueryStrategy
    """

    name = "llm"
    determinism: Determinism = Determinism.NON_DETERMINISTIC

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)

        # Provider dispatch from single registry.
        # .get() is appropriate here: config is user YAML (Tier 3 boundary), and
        # defaulting to "" produces a clear ValueError listing valid providers,
        # which is more helpful than a raw KeyError on missing 'provider' key.
        provider_name = config.get("provider", "")
        if provider_name not in _PROVIDERS:
            raise ValueError(f"Unknown LLM provider '{provider_name}'. Valid providers: {sorted(_PROVIDERS)}")
        config_cls, _ = _PROVIDERS[provider_name]

        # Parse config with provider-specific model.
        # config_cls is AzureOpenAIConfig or OpenRouterConfig at runtime;
        # from_dict() returns Self on the subclass, but mypy sees type[LLMConfig].
        self._config = cast(
            "AzureOpenAIConfig | OpenRouterConfig",
            config_cls.from_dict(config),
        )

        # Store common LLM settings.
        # AzureOpenAIConfig._set_model_from_deployment ensures model is populated;
        # OpenRouterConfig requires model. So self._config.model is always non-empty.
        self._model = self._config.model
        self._template = PromptTemplate(
            self._config.template,
            template_source=self._config.template_source,
            lookup_data=self._config.lookup,
            lookup_source=self._config.lookup_source,
        )
        self._system_prompt = self._config.system_prompt
        self._system_prompt_source = self._config.system_prompt_source
        self._temperature = self._config.temperature
        self._max_tokens = self._config.max_tokens
        self._response_field = self._config.response_field
        self._max_capacity_retry_seconds = self._config.max_capacity_retry_seconds

        # Schema
        schema_config = self._config.schema_config
        self.input_schema = create_schema_from_config(
            schema_config,
            f"{self.name}Schema",
            allow_coercion=False,
        )
        self.output_schema = _build_augmented_output_schema(
            base_schema_config=schema_config,
            response_field=self._config.response_field,
            schema_name=f"{self.name}OutputSchema",
        )

        # Build output schema config with field categorization
        guaranteed = get_llm_guaranteed_fields(self._response_field)
        audit = get_llm_audit_fields(self._response_field)
        base_guaranteed = schema_config.guaranteed_fields or ()
        base_audit = schema_config.audit_fields or ()
        self._output_schema_config = SchemaConfig(
            mode=schema_config.mode,
            fields=schema_config.fields,
            guaranteed_fields=tuple(set(base_guaranteed) | set(guaranteed)),
            audit_fields=tuple(set(base_audit) | set(audit)),
            required_fields=schema_config.required_fields,
        )

        # Tracer — factory returns frozen ActiveLangfuseTracer or NoOpLangfuseTracer.
        # tracing lives on provider-specific configs (AzureOpenAIConfig, OpenRouterConfig),
        # both of which define tracing: dict[str, Any] | None.
        tracing_config = parse_tracing_config(self._config.tracing) if self._config.tracing else None
        self._tracer = create_langfuse_tracer(
            transform_name=self.name,
            tracing_config=tracing_config,
        )

        # Strategy dispatch: queries is not None → multi-query
        if self._config.queries is not None:
            query_specs = resolve_queries(self._config.queries)
            self._strategy: SingleQueryStrategy | MultiQueryStrategy = MultiQueryStrategy(
                query_specs=query_specs,
                template=self._template,
                system_prompt=self._system_prompt,
                system_prompt_source=self._system_prompt_source,
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                response_field=self._response_field,
            )

            # Multi-query emits prefixed fields — declare them for collision detection
            prefixed_fields: set[str] = set()
            for spec in query_specs:
                prefix = f"{spec.name}_{self._response_field}"
                prefixed_fields.add(prefix)
                prefixed_fields.update(get_llm_guaranteed_fields(prefix))
                prefixed_fields.update(get_llm_audit_fields(prefix))
                if spec.output_fields:
                    for field in spec.output_fields:
                        prefixed_fields.add(f"{spec.name}_{field.suffix}")
            self.declared_output_fields = frozenset(prefixed_fields)
        else:
            self._strategy = SingleQueryStrategy(
                template=self._template,
                system_prompt=self._system_prompt,
                system_prompt_source=self._system_prompt_source,
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                response_field=self._response_field,
            )

            # Single-query emits unprefixed fields
            self.declared_output_fields = frozenset(
                [
                    *get_llm_guaranteed_fields(self._config.response_field),
                    *get_llm_audit_fields(self._config.response_field),
                ]
            )

        # Provider instance — deferred to on_start() when recorder/telemetry available
        self._provider: LLMProvider | None = None

        # Recorder, telemetry, rate limit (set in on_start)
        self._recorder: LandscapeRecorder | None = None
        self._run_id: str = ""
        self._telemetry_emit: Callable[[Any], None] = lambda event: None
        self._limiter: Any = None

        # Batch processing state
        self._batch_initialized = False

    def connect_output(self, output: OutputPort, max_pending: int = 30) -> None:
        """Connect output port and initialize batch processing."""
        if self._batch_initialized:
            raise RuntimeError("connect_output() already called")

        self.init_batch_processing(
            max_pending=max_pending,
            output=output,
            name=self.name,
            max_workers=max_pending,
            batch_wait_timeout=float(self._max_capacity_retry_seconds),
        )
        self._batch_initialized = True

    def on_start(self, ctx: LifecycleContext) -> None:
        """Capture recorder/telemetry and create provider instance."""
        super().on_start(ctx)
        self._recorder = ctx.landscape
        self._run_id = ctx.run_id
        self._telemetry_emit = ctx.telemetry_emit
        limiter_name = "azure_openai" if isinstance(self._config, AzureOpenAIConfig) else "openrouter"
        self._limiter = ctx.rate_limit_registry.get_limiter(limiter_name) if ctx.rate_limit_registry is not None else None

        # Create provider now that recorder/telemetry are available
        self._provider = self._create_provider()

    def _create_provider(self) -> LLMProvider:
        """Instantiate the provider with all required dependencies.

        Uses isinstance narrowing on self._config to safely access
        provider-specific attributes (endpoint, deployment_name, base_url, etc.).
        """
        if self._recorder is None:
            raise RuntimeError("_recorder not initialized — _create_provider called before on_start()")

        if isinstance(self._config, AzureOpenAIConfig):
            return AzureLLMProvider(
                endpoint=self._config.endpoint,
                api_key=self._config.api_key,
                api_version=self._config.api_version,
                deployment_name=self._config.deployment_name,
                recorder=self._recorder,
                run_id=self._run_id,
                telemetry_emit=self._telemetry_emit,
                limiter=self._limiter,
            )
        elif isinstance(self._config, OpenRouterConfig):
            return OpenRouterLLMProvider(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
                timeout_seconds=self._config.timeout_seconds,
                recorder=self._recorder,
                run_id=self._run_id,
                telemetry_emit=self._telemetry_emit,
                limiter=self._limiter,
            )
        else:
            raise RuntimeError(f"Unknown config type: {type(self._config).__name__}")

    def accept(self, row: PipelineRow, ctx: TransformContext) -> None:
        """Accept a row for processing (pipeline entry point)."""
        if not self._batch_initialized:
            raise RuntimeError("connect_output() must be called before accept()")
        self.accept_row(row, ctx, self._process_row)

    def process(self, row: PipelineRow, ctx: TransformContext) -> TransformResult:
        """Not supported — use accept() for row-level pipelining."""
        raise NotImplementedError(
            f"{self.__class__.__name__} uses row-level pipelining. Use accept() instead of process(). See class docstring for usage."
        )

    def _process_row(self, row: PipelineRow, ctx: TransformContext) -> TransformResult:
        """Process a single row via the selected strategy.

        Called by worker threads from BatchTransformMixin. Delegates to
        SingleQueryStrategy or MultiQueryStrategy.
        """
        if self._provider is None:
            raise RuntimeError("Provider not initialized — _process_row called before on_start()")

        return self._strategy.execute(
            row,
            ctx,
            provider=self._provider,
            tracer=self._tracer,
        )

    def close(self) -> None:
        """Release resources."""
        self._tracer.flush()

        if self._batch_initialized:
            self.shutdown_batch_processing()

        if self._provider is not None:
            self._provider.close()
            self._provider = None

        self._recorder = None
