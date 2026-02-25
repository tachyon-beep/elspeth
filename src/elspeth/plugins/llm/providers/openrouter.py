# src/elspeth/plugins/llm/providers/openrouter.py
"""OpenRouter LLM provider.

Handles raw HTTP transport with full Tier 3 boundary validation:
- JSON parsing with NaN/Infinity rejection
- Content extraction from choices[0].message.content
- Null content → ContentPolicyError
- Non-finite usage values → LLMClientError
- HTTP status code → typed exception mapping

Client caching is per-state_id with a threading lock. Uses AuditedHTTPClient
for audit recording and telemetry.
"""

from __future__ import annotations

import json
import math
from threading import Lock
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.clients.http import AuditedHTTPClient
from elspeth.plugins.clients.llm import (
    ContentPolicyError,
    ContextLengthError,
    LLMClientError,
    NetworkError,
    RateLimitError,
    ServerError,
)
from elspeth.plugins.llm.provider import LLMQueryResult, parse_finish_reason
from elspeth.plugins.llm.validation import reject_nonfinite_constant

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder
    from elspeth.plugins.clients.base import TelemetryEmitCallback

logger = structlog.get_logger(__name__)


class OpenRouterLLMProvider:
    """OpenRouter provider — raw HTTP with Tier 3 validation.

    Responsibilities:
    1. Create/cache AuditedHTTPClient per state_id (thread-safe)
    2. Make HTTP POST to /chat/completions
    3. Parse JSON response with NaN rejection
    4. Validate content, usage, finish_reason at Tier 3 boundary
    5. Map HTTP errors to typed exceptions
    6. Let validated data flow as LLMQueryResult

    Does NOT own:
    - Audit recording (AuditedHTTPClient does this)
    - Telemetry emission (AuditedHTTPClient does this)
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 60.0,
        recorder: LandscapeRecorder,
        run_id: str,
        telemetry_emit: TelemetryEmitCallback,
        limiter: Any = None,
    ) -> None:
        # Pre-build auth headers — avoids storing the raw API key as a named attribute
        self._request_headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/elspeth-rapid",
        }
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._recorder = recorder
        self._run_id = run_id
        self._telemetry_emit = telemetry_emit
        self._limiter = limiter

        # Client cache
        self._http_clients: dict[str, AuditedHTTPClient] = {}
        self._http_clients_lock = Lock()

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
        """Execute LLM query via OpenRouter HTTP API.

        Full Tier 3 validation pipeline:
        1. HTTP POST with error classification
        2. JSON parse with NaN rejection
        3. Content extraction and null check
        4. Usage validation (non-finite rejection)
        5. Finish reason normalization

        Raises:
            RateLimitError: HTTP 429 (retryable)
            ServerError: HTTP 5xx (retryable)
            NetworkError: Connection/timeout failures (retryable)
            ContentPolicyError: Null content from provider (not retryable)
            LLMClientError: Other failures (not retryable)
        """
        snapshot_state_id = state_id

        try:
            http_client = self._get_http_client(snapshot_state_id, token_id=token_id)

            # Build request body
            request_body: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                request_body["max_tokens"] = max_tokens

            # HTTP call — raise_for_status for error classification
            try:
                response = http_client.post(
                    "/chat/completions",
                    json=request_body,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code == 429:
                    raise RateLimitError(f"Rate limited: {e}") from e
                elif status_code >= 500:
                    raise ServerError(f"Server error ({status_code}): {e}") from e
                else:
                    # Check response body for context length indicators before
                    # falling through to generic LLMClientError. Matches the same
                    # patterns used by AuditedLLMClient._classify_llm_error().
                    error_body = e.response.text.lower()
                    if any(
                        p in error_body
                        for p in (
                            "context_length_exceeded",
                            "context length",
                            "maximum context",
                        )
                    ):
                        raise ContextLengthError(
                            f"Context length exceeded: {e.response.text[:200]}",
                        ) from e
                    raise LLMClientError(
                        f"HTTP {status_code}: {e}",
                        retryable=False,
                    ) from e
            except httpx.RequestError as e:
                raise NetworkError(f"Network error: {e}") from e

            # Parse JSON — reject NaN/Infinity at Tier 3 boundary
            try:
                data = json.loads(response.content, parse_constant=reject_nonfinite_constant)
            except (ValueError, TypeError) as e:
                raise LLMClientError(
                    f"Response is not valid JSON: {e}",
                    retryable=False,
                ) from e

            # Extract content from choices
            choices = data.get("choices") if isinstance(data, dict) else None
            if not choices:
                raise LLMClientError(
                    f"Empty or missing choices in response: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}",
                    retryable=False,
                )

            try:
                content = choices[0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                raise LLMClientError(
                    f"Malformed response structure: {type(e).__name__}: {e}",
                    retryable=False,
                ) from e

            # Null content = content filtered by provider
            if content is None:
                raise ContentPolicyError("LLM returned null content (likely content-filtered by provider)")

            # Non-string content
            if not isinstance(content, str):
                raise LLMClientError(
                    f"Expected string content, got {type(content).__name__}",
                    retryable=False,
                )

            # Validate usage (non-finite rejection)
            raw_usage = data.get("usage") or {}
            if isinstance(raw_usage, dict):
                for usage_key, usage_val in raw_usage.items():
                    if isinstance(usage_val, float) and not math.isfinite(usage_val):
                        raise LLMClientError(
                            f"Non-finite value in usage.{usage_key}: {usage_val}",
                            retryable=False,
                        )
            usage = TokenUsage.from_dict(raw_usage)

            # Extract finish reason
            raw_finish_reason = choices[0].get("finish_reason") if isinstance(choices[0], dict) else None
            finish_reason = parse_finish_reason(str(raw_finish_reason)) if raw_finish_reason is not None else None

            # Extract model (provider may return different model than requested)
            response_model = data.get("model", model) if isinstance(data, dict) else model

            return LLMQueryResult(
                content=content,
                usage=usage,
                model=response_model,
                finish_reason=finish_reason,
            )
        finally:
            # Clean up cached client for this state_id
            with self._http_clients_lock:
                client = self._http_clients.pop(snapshot_state_id, None)
            if client is not None:
                client.close()

    def _get_http_client(self, state_id: str, *, token_id: str | None = None) -> AuditedHTTPClient:
        """Get or create AuditedHTTPClient for a state_id (thread-safe)."""
        with self._http_clients_lock:
            if state_id not in self._http_clients:
                self._http_clients[state_id] = AuditedHTTPClient(
                    recorder=self._recorder,
                    state_id=state_id,
                    run_id=self._run_id,
                    telemetry_emit=self._telemetry_emit,
                    timeout=self._timeout,
                    base_url=self._base_url,
                    headers=self._request_headers,
                    limiter=self._limiter,
                    token_id=token_id,
                )
            return self._http_clients[state_id]

    def close(self) -> None:
        """Release all cached clients."""
        with self._http_clients_lock:
            for client in self._http_clients.values():
                client.close()
            self._http_clients.clear()
