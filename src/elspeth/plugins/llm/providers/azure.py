# src/elspeth/plugins/llm/providers/azure.py
"""Azure OpenAI LLM provider.

Thin wrapper over AuditedLLMClient that normalizes LLMResponse into
LLMQueryResult. All audit recording, telemetry, and error classification
happen inside AuditedLLMClient — this provider just manages client lifecycle
and response normalization.

Client caching is per-state_id with a threading lock. The state_id is
snapshot at method entry (not read from a mutable context) to prevent
evicting the wrong cache entry during retry races.
"""

from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING, Any, Literal, Self

import structlog
from pydantic import Field, model_validator

from elspeth.plugins.clients.llm import AuditedLLMClient, ContentPolicyError, LLMClientError
from elspeth.plugins.llm.base import LLMConfig
from elspeth.plugins.llm.provider import FinishReason, LLMQueryResult, parse_finish_reason
from elspeth.plugins.llm.tracing import AzureAITracingConfig, TracingConfig

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder
    from elspeth.plugins.clients.base import TelemetryEmitCallback

logger = structlog.get_logger(__name__)


class AzureOpenAIConfig(LLMConfig):
    """Azure OpenAI-specific configuration.

    Extends LLMConfig with Azure-specific settings:
    - deployment_name: Azure deployment name (required) - used as model identifier
    - endpoint: Azure OpenAI endpoint URL (required)
    - api_key: Azure OpenAI API key (required)
    - api_version: Azure API version (default: 2024-10-21)

    Pooling options (inherited from LLMConfig):
    - pool_size: Number of concurrent workers (1=sequential, >1=pooled)
    - max_dispatch_delay_ms: Maximum AIMD backoff delay
    - max_capacity_retry_seconds: Timeout for capacity error retries

    Note: The 'model' field from LLMConfig is automatically set to
    deployment_name if not explicitly provided.
    """

    # Azure configs always have provider="azure" — narrowed Literal prevents misconfiguration
    provider: Literal["azure"] = Field(default="azure", description="LLM provider")

    # Override model to make it optional - will default to deployment_name
    model: str = Field(default="", description="Model identifier (defaults to deployment_name)")

    deployment_name: str = Field(..., description="Azure deployment name")
    endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    api_key: str = Field(..., description="Azure OpenAI API key")
    api_version: str = Field(default="2024-10-21", description="Azure API version")

    # Tier 2: Plugin-internal tracing (optional)
    # Use environment variables for secrets: ${APPLICATIONINSIGHTS_CONNECTION_STRING}
    tracing: dict[str, Any] | None = Field(
        default=None,
        description="Tier 2 tracing configuration (azure_ai, langfuse, or none)",
    )

    @model_validator(mode="after")
    def _set_model_from_deployment(self) -> Self:
        """Set model to deployment_name if not explicitly provided."""
        if not self.model:
            self.model = self.deployment_name
        return self


class AzureLLMProvider:
    """Azure OpenAI provider — wraps AuditedLLMClient.

    Responsibilities:
    1. Create/cache AuditedLLMClient per state_id (thread-safe)
    2. Create/cache underlying AzureOpenAI SDK client (thread-safe)
    3. Map LLMResponse → LLMQueryResult (content, usage, model, finish_reason)
    4. Let LLMClientError subclasses propagate unchanged

    Does NOT own:
    - Audit recording (AuditedLLMClient does this)
    - Error classification (AuditedLLMClient does this)
    - Tracing setup (transform lifecycle manages azure_ai tracing)
    """

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        api_version: str,
        deployment_name: str,
        recorder: LandscapeRecorder,
        run_id: str,
        telemetry_emit: TelemetryEmitCallback,
        limiter: Any = None,
    ) -> None:
        self._endpoint = endpoint
        self._api_key: str | None = api_key
        self._api_version = api_version
        self._deployment_name = deployment_name
        self._recorder = recorder
        self._run_id = run_id
        self._telemetry_emit = telemetry_emit
        self._limiter = limiter

        # Client caches — lock ordering: _llm_clients_lock → _underlying_client_lock
        # (always acquire _llm_clients_lock first to prevent deadlock)
        self._llm_clients: dict[str, AuditedLLMClient] = {}
        self._llm_clients_lock = Lock()
        self._underlying_client: Any = None  # AzureOpenAI | None
        self._underlying_client_lock = Lock()

    def execute_query(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float,
        max_tokens: int | None,
        state_id: str,
        token_id: str,
        response_format: dict[str, Any] | None = None,
    ) -> LLMQueryResult:
        """Execute LLM query via Azure OpenAI SDK.

        Args:
            messages: Chat messages (system + user)
            model: Model/deployment name
            temperature: Sampling temperature
            max_tokens: Max response tokens (None = provider default)
            state_id: Snapshot of state_id for client caching
            token_id: Token identity for audit correlation
            response_format: OpenAI response_format dict (e.g., {"type": "json_object"})

        Returns:
            Normalized LLMQueryResult

        Raises:
            RateLimitError, NetworkError, ServerError: Retryable
            ContentPolicyError, ContextLengthError, LLMClientError: Not retryable
        """
        # Snapshot state_id — do not read from mutable ctx later.
        # This prevents the openrouter.py bug where ctx.state_id was read
        # in the finally block, evicting the wrong cache entry during retries.
        snapshot_state_id = state_id

        try:
            client = self._get_llm_client(snapshot_state_id, token_id=token_id)

            response = client.chat_completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )

            # Extract finish_reason from raw_response.
            # raw_response is the Azure SDK's deserialized API response (Tier 3
            # external boundary — SDK structure may change between versions).
            finish_reason = None
            if response.raw_response is not None:
                choices = response.raw_response.get("choices", [])
                if choices:
                    raw_fr = choices[0].get("finish_reason")
                    if raw_fr is not None:
                        finish_reason = parse_finish_reason(str(raw_fr))
                else:
                    logger.warning(
                        "Azure SDK response missing choices — finish_reason unavailable",
                        raw_response_keys=list(response.raw_response.keys()),
                    )

            # Empty/whitespace content — AuditedLLMClient converts None→""
            # (known fabrication). Detect here and raise typed errors so the
            # transform's except LLMClientError handler catches them.
            if not response.content or not response.content.strip():
                if finish_reason == FinishReason.TOOL_CALLS:
                    raise LLMClientError(
                        "Azure returned tool_calls response (not supported by ELSPETH)",
                        retryable=False,
                    )
                raise ContentPolicyError(
                    f"LLM returned empty content (finish_reason={finish_reason})",
                )

            return LLMQueryResult(
                content=response.content,
                usage=response.usage,
                model=response.model,
                finish_reason=finish_reason,
            )
        finally:
            # Clean up cached client for this state_id to prevent unbounded growth.
            # Uses snapshot (not state_id parameter) to avoid evicting wrong entry.
            with self._llm_clients_lock:
                self._llm_clients.pop(snapshot_state_id, None)

    def _get_underlying_client(self) -> Any:
        """Get or create the underlying AzureOpenAI SDK client (thread-safe)."""
        with self._underlying_client_lock:
            if self._underlying_client is None:
                from openai import AzureOpenAI

                self._underlying_client = AzureOpenAI(
                    azure_endpoint=self._endpoint,
                    api_key=self._api_key,
                    api_version=self._api_version,
                )
                # Clear plaintext key — SDK client holds its own copy
                self._api_key = None
            return self._underlying_client

    def _get_llm_client(self, state_id: str, *, token_id: str | None = None) -> AuditedLLMClient:
        """Get or create AuditedLLMClient for a state_id (thread-safe)."""
        with self._llm_clients_lock:
            if state_id not in self._llm_clients:
                self._llm_clients[state_id] = AuditedLLMClient(
                    recorder=self._recorder,
                    state_id=state_id,
                    run_id=self._run_id,
                    telemetry_emit=self._telemetry_emit,
                    underlying_client=self._get_underlying_client(),
                    provider="azure",
                    limiter=self._limiter,
                    token_id=token_id,
                )
            return self._llm_clients[state_id]

    def close(self) -> None:
        """Release all cached clients."""
        with self._llm_clients_lock:
            self._llm_clients.clear()
        with self._underlying_client_lock:
            self._underlying_client = None


# Optional SDK import — module-level so tests can mock it.
try:
    from azure.monitor.opentelemetry import (
        configure_azure_monitor,
    )
except ImportError:
    configure_azure_monitor = None  # type: ignore[assignment]

# Module-level idempotency guard — Azure Monitor is process-global.
_azure_monitor_configured: bool = False


def _reset_azure_monitor_state() -> None:
    """Reset module state for testing only."""
    global _azure_monitor_configured
    _azure_monitor_configured = False


def _configure_azure_monitor(config: TracingConfig) -> bool:
    """Configure Azure Monitor (module-level to allow mocking).

    Returns True on success, False on failure.
    Idempotent: second call logs a warning and returns True.
    """
    global _azure_monitor_configured

    if not isinstance(config, AzureAITracingConfig):
        return False

    if _azure_monitor_configured:
        logger.warning(
            "Azure Monitor already configured — skipping duplicate initialization",
        )
        return True

    if configure_azure_monitor is None:
        logger.warning(  # type: ignore[unreachable]  # runtime fallback when SDK not installed (see line 239)
            "azure-monitor-opentelemetry is not installed — Azure AI tracing inactive",
            hint="Install with: uv pip install 'elspeth[azure]'",
        )
        return False

    configure_azure_monitor(
        connection_string=config.connection_string,
        enable_live_metrics=config.enable_live_metrics,
    )

    # Wire enable_content_recording to the Azure AI Inference tracing SDK.
    # Without this, the config field is accepted and logged but never applied,
    # leaving operators with a false sense of their content recording policy.
    try:
        from azure.ai.inference.tracing import AIInferenceInstrumentor

        AIInferenceInstrumentor().instrument(enable_content_recording=config.enable_content_recording)
    except ImportError:
        # azure-ai-inference not installed — fall back to environment variable
        # which the OpenAI SDK instrumentor reads at trace emission time.
        import os

        logger.warning(
            "azure-ai-inference not installed — falling back to environment variable for content recording",
            hint="Install azure-ai-inference for full tracing support",
            fallback_env_var="AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED",
        )
        os.environ["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = str(config.enable_content_recording).lower()

    _azure_monitor_configured = True
    return True
