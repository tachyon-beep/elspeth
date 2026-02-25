# src/elspeth/plugins/llm/provider.py
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
        if not self.model or not self.model.strip():
            raise ValueError("LLMQueryResult.model must be non-empty")


@runtime_checkable
class LLMProvider(Protocol):
    """What LLMTransform needs from a provider. Narrow interface.

    Providers raise typed exceptions from elspeth.plugins.clients.llm:
    - RateLimitError: 429 / rate limit (retryable)
    - NetworkError: connection failures (retryable)
    - ServerError: 5xx errors (retryable)
    - ContentPolicyError: content filtering (not retryable)
    - ContextLengthError: context too long (not retryable)
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
