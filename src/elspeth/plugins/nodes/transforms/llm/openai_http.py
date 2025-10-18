"""Generic OpenAI-compatible HTTP client implementing the LLM protocol."""

from __future__ import annotations

import os
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from elspeth.core.base.protocols import LLMClientProtocol


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
        retry_total: int = 3,
        backoff_factor: float = 0.5,
        status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
        security_level: str | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        # Defense-in-depth: validate endpoint even when instantiated directly
        try:
            from elspeth.core.security import validate_http_api_endpoint

            validate_http_api_endpoint(endpoint=self.api_base, security_level=security_level)
        except Exception as exc:  # pragma: no cover - validation path exercised via registry tests
            # Raise a clear error for misconfiguration/bypasses
            raise ValueError(f"HTTP API endpoint validation failed: {exc}") from exc
        if not api_key and api_key_env:
            api_key = os.getenv(api_key_env)
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        # Configure a session with bounded retries for transient errors
        self.session = requests.Session()
        try:  # pragma: no cover - adapter internals vary by env
            retry = Retry(
                total=retry_total,
                backoff_factor=backoff_factor,
                status_forcelist=list(status_forcelist),
                allowed_methods=["GET", "POST"],
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)
        except Exception:
            # If retry adapter isn't available, proceed without retries
            pass

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
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

        response = self.session.post(
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
