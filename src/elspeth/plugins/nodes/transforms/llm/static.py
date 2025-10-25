"""Static LLM client returning deterministic responses for testing."""

from __future__ import annotations

from typing import Any, Mapping

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.protocols import LLMClientProtocol
from elspeth.core.base.types import SecurityLevel


class StaticLLMClient(BasePlugin, LLMClientProtocol):
    """Return predefined content and metrics for every request.

    Args:
        security_level: Security clearance for this LLM adapter (MANDATORY per ADR-004).
        allow_downgrade: Whether adapter can operate at lower pipeline levels (MANDATORY per ADR-005).
        content: Static response content to return for all requests (REQUIRED).
        score: Optional score metric to include in response.
        metrics: Optional additional metrics to include in response.
    """

    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        allow_downgrade: bool,
        content: str,  # Required - no default allowed
        score: float | None = None,
        metrics: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(security_level=security_level, allow_downgrade=allow_downgrade)
        self.content = content
        self.score = score
        self.extra_metrics = dict(metrics or {})

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metrics = dict(self.extra_metrics)
        if self.score is not None:
            metrics.setdefault("score", float(self.score))
        return {
            "content": self.content,
            "metrics": metrics,
            "raw": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "metadata": metadata or {},
            },
        }


__all__ = ["StaticLLMClient"]
