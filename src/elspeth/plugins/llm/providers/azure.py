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
from typing import TYPE_CHECKING, Any

import structlog

from elspeth.plugins.clients.llm import AuditedLLMClient
from elspeth.plugins.llm.provider import LLMQueryResult, parse_finish_reason

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder
    from elspeth.plugins.clients.base import TelemetryEmitCallback

logger = structlog.get_logger(__name__)


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

        # Client caches
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
    ) -> LLMQueryResult:
        """Execute LLM query via Azure OpenAI SDK.

        Args:
            messages: Chat messages (system + user)
            model: Model/deployment name
            temperature: Sampling temperature
            max_tokens: Max response tokens (None = provider default)
            state_id: Snapshot of state_id for client caching
            token_id: Token identity for audit correlation

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
            )

            # Extract finish_reason from raw_response (SDK-validated API response — Tier 2)
            finish_reason = None
            if response.raw_response is not None:
                choices = response.raw_response.get("choices", [])
                if choices:
                    raw_fr = choices[0].get("finish_reason")
                    if raw_fr is not None:
                        finish_reason = parse_finish_reason(str(raw_fr))

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
