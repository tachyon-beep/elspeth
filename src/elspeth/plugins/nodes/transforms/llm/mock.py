"""Mock LLM client for local testing and sample suites."""

from __future__ import annotations

import hashlib
from typing import Any

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.protocols import LLMClientProtocol
from elspeth.core.base.types import SecurityLevel


class MockLLMClient(BasePlugin, LLMClientProtocol):
    """Deterministic mock client for tests and offline runs.

    Security policy: Test-only transform operates at UNOFFICIAL level (ADR-002-B).

    Args:
        seed: Optional seed for deterministic response generation (default: 0).
    """

    def __init__(
        self,
        *,
        seed: int | None = None
    ):
        """Initialize mock LLM client with hard-coded security policy.

        ADR-002-B: Security policy is immutable. Mock LLMs operate at UNOFFICIAL level
        and can be trusted to downgrade (test-only transform).
        """
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # ADR-002-B: Immutable policy
            allow_downgrade=True,  # ADR-002-B: Immutable policy
        )
        self.seed = seed or 0

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = metadata or {}
        score = self._derive_score(system_prompt, user_prompt, context)
        return {
            "content": f"[mock] score={score:.2f}\n{user_prompt}",
            "metrics": {
                "score": score,
                "comment": "Mock response generated for demonstration",  # optional helper
            },
            "raw": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "metadata": context,
            },
        }

    def _derive_score(self, system_prompt: str, user_prompt: str, metadata: dict[str, Any]) -> float:
        hasher = hashlib.sha256()
        hasher.update(system_prompt.encode("utf-8"))
        hasher.update(user_prompt.encode("utf-8"))
        if metadata:
            hasher.update(str(sorted(metadata.items())).encode("utf-8"))
        hasher.update(str(self.seed).encode("utf-8"))
        digest = hasher.digest()
        raw = digest[0]
        return 0.4 + (raw / 255.0) * 0.5


__all__ = ["MockLLMClient"]
