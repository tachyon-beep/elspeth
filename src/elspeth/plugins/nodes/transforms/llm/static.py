"""Static LLM client returning deterministic responses for testing."""

from __future__ import annotations

from typing import Any, Mapping

from elspeth.core.protocols import LLMClientProtocol


class StaticLLMClient(LLMClientProtocol):
    """Return predefined content and metrics for every request."""

    def __init__(
        self,
        *,
        content: str = "STATIC RESPONSE",
        score: float | None = 0.5,
        metrics: Mapping[str, Any] | None = None,
    ) -> None:
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
