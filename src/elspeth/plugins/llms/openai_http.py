"""Generic OpenAI-compatible HTTP client implementing the LLM protocol."""

from __future__ import annotations

import os
from typing import Any, Dict

import requests

from elspeth.core.interfaces import LLMClientProtocol


class HttpOpenAIClient(LLMClientProtocol):
    """Minimal client for standard /v1/chat/completions endpoints."""

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str | None = None,
        api_key_env: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        if not api_key and api_key_env:
            api_key = os.getenv(api_key_env)
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            f"{self.api_base}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        return {
            "content": content,
            "raw": data,
            "metadata": metadata or {},
        }


__all__ = ["HttpOpenAIClient"]
