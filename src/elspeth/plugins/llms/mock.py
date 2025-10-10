"""Mock LLM client for local testing and sample suites."""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from elspeth.core.interfaces import LLMClientProtocol


class MockLLMClient(LLMClientProtocol):
    def __init__(self, *, seed: int | None = None):
        self.seed = seed or 0

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
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

    def _derive_score(self, system_prompt: str, user_prompt: str, metadata: Dict[str, Any]) -> float:
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
