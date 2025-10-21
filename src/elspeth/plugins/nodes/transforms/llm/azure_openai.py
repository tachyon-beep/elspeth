"""Azure OpenAI client wrapper implementing the LLM protocol."""

from __future__ import annotations

import os
from typing import Any

from elspeth.core.base.protocols import LLMClientProtocol


class AzureOpenAIClient(LLMClientProtocol):
    def __init__(
        self,
        *,
        deployment: str | None = None,
        config: dict[str, Any],
        client: Any | None = None,
    ):
        self.config = config
        self.temperature = config.get("temperature")
        self.max_tokens = config.get("max_tokens")
        # Bounded request timeouts for operational resilience
        try:
            self.request_timeout = float(config.get("timeout", 30.0))
        except Exception:
            self.request_timeout = 30.0
        self.deployment = self._resolve_deployment(deployment)
        self._client = client or self._create_client()

    def _create_client(self) -> Any:
        api_key = self._resolve_required("api_key")
        api_version = self._resolve_required("api_version")
        azure_endpoint = self._resolve_required("azure_endpoint")

        try:
            from openai import AzureOpenAI
        except ImportError as exc:  # pragma: no cover - dependency ensured in runtime
            raise RuntimeError("openai package is required for AzureOpenAIClient") from exc

        return AzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=azure_endpoint,
        )

    def _resolve_deployment(self, deployment: str | None) -> str:
        if deployment:
            return deployment
        if self.config.get("deployment"):
            # Dict[str, Any] indexing returns Any, but runtime check ensures it's str
            return self.config["deployment"]  # type: ignore[no-any-return]
        env_key = self.config.get("deployment_env")
        if env_key:
            value = os.getenv(env_key)
            if value:
                return value
        value = os.getenv("ELSPETH_AZURE_OPENAI_DEPLOYMENT")
        if value:
            return value
        raise ValueError(
            "AzureOpenAIClient missing deployment configuration; "
            "set 'deployment' in config, or set environment variable "
            f"'{self.config.get('deployment_env', 'ELSPETH_AZURE_OPENAI_DEPLOYMENT')}'"
        )

    def _resolve_required(self, key: str) -> str:
        value = self._resolve_optional(key)
        if not value:
            raise ValueError(f"AzureOpenAIClient missing required config value '{key}'")
        return value

    def _resolve_optional(self, key: str) -> str | None:
        if key in self.config and self.config[key]:
            # Dict[str, Any] indexing returns Any, but runtime check ensures it's str
            return self.config[key]  # type: ignore[no-any-return]
        env_key = self.config.get(f"{key}_env")
        if env_key:
            return os.getenv(env_key)
        return None

    @property
    def client(self) -> Any:
        return self._client

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        kwargs: dict[str, Any] = {"model": self.deployment, "messages": messages}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens

        # Apply request timeout; openai SDK accepts per-request timeout
        response = self.client.chat.completions.create(timeout=self.request_timeout, **kwargs)
        content = None
        try:
            content = response.choices[0].message.content
        except Exception:  # pragma: no cover - defensive fallback
            content = None

        return {
            "content": content,
            "raw": response,
            "metadata": metadata or {},
        }
