"""Static LLM client returning deterministic responses for testing."""

from __future__ import annotations

from typing import Any, Mapping

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.protocols import LLMClientProtocol
from elspeth.core.base.types import SecurityLevel


class StaticLLMClient(BasePlugin, LLMClientProtocol):
    """Return predefined content and metrics for every request.

    Security policy: Test-only transform operates at UNOFFICIAL level (ADR-002-B).

    Args:
        content: Static response content to return for all requests (REQUIRED).
        score: Optional score metric to include in response.
        metrics: Optional additional metrics to include in response.
    """

    def __init__(
        self,
        *,
        content: str,  # Required - no default allowed
        score: float | None = None,
        metrics: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize static LLM client with hard-coded security policy.

        ADR-002-B: Security policy is immutable. Static LLMs operate at UNOFFICIAL level
        and can be trusted to downgrade (test-only transform).
        """
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # ADR-002-B: Immutable policy
            allow_downgrade=True,  # ADR-002-B: Immutable policy
        )
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
