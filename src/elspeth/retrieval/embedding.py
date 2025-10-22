"""Embedding providers used for retrieval services."""

from __future__ import annotations

import os
from typing import Sequence

from openai import AzureOpenAI, OpenAI

from elspeth.core.security import (
    get_secure_mode,
    validate_azure_openai_endpoint,
    validate_http_api_endpoint,
)
from elspeth.core.validation.base import ConfigurationError


class Embedder:
    """Base embedding provider."""

    def embed(self, text: str) -> Sequence[float]:  # pragma: no cover - interface
        """Generate embedding vector for the given text.

        Args:
            text: Input text to embed

        Returns:
            Embedding vector as a sequence of floats
        """
        raise NotImplementedError


class OpenAIEmbedder(Embedder):
    """OpenAI embedding provider."""

    def __init__(self, *, model: str, api_key: str | None = None, timeout: float | int | None = None):
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ConfigurationError("OpenAI embeddings require an API key via 'api_key' or OPENAI_API_KEY")
        # Enforce endpoint allowlist for OpenAI public API (defense-in-depth).
        # The OpenAI public endpoint is always allowed regardless of security level;
        # pass security_level=None explicitly to make this intention clear.
        validate_http_api_endpoint("https://api.openai.com", security_level=None)
        self._client = OpenAI(api_key=key)
        self._model = model
        # Resolve timeout from argument or environment
        resolved_timeout = timeout
        if resolved_timeout is None:
            t_env = os.getenv("ELSPETH_EMBEDDING_TIMEOUT")
            if t_env:
                try:
                    resolved_timeout = float(t_env)
                except (ValueError, TypeError):
                    resolved_timeout = None
        try:
            self._timeout = float(resolved_timeout) if resolved_timeout is not None else 30.0
        except (ValueError, TypeError):
            self._timeout = 30.0

    def embed(self, text: str) -> Sequence[float]:
        response = self._client.embeddings.create(model=self._model, input=text, timeout=self._timeout)
        return list(response.data[0].embedding)


class AzureOpenAIEmbedder(Embedder):
    """Azure OpenAI embedding provider."""

    def __init__(
        self,
        *,
        endpoint: str | None,
        deployment: str,
        api_key: str | None = None,
        api_version: str | None = None,
        timeout: float | int | None = None,
    ) -> None:
        endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        if not endpoint:
            raise ConfigurationError("Azure OpenAI embeddings require 'endpoint' or AZURE_OPENAI_ENDPOINT")

        key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        if not key:
            raise ConfigurationError("Azure OpenAI embeddings require 'api_key' or AZURE_OPENAI_API_KEY")

        version = api_version or os.getenv("AZURE_OPENAI_API_VERSION")
        if not version:
            raise ConfigurationError(
                "Azure OpenAI embeddings require explicit 'api_version' configuration or AZURE_OPENAI_API_VERSION. "
                "Provide explicit version (e.g., '2024-05-13') for security/audit purposes."
            )

        # Enforce endpoint allowlist for Azure OpenAI (defense-in-depth)
        # according to current secure mode
        validate_azure_openai_endpoint(endpoint, mode=get_secure_mode())

        self._client = AzureOpenAI(
            api_key=key,
            azure_endpoint=endpoint,
            api_version=version,
        )
        self._deployment = deployment
        resolved_timeout = timeout
        if resolved_timeout is None:
            t_env = os.getenv("ELSPETH_EMBEDDING_TIMEOUT")
            if t_env:
                try:
                    resolved_timeout = float(t_env)
                except (ValueError, TypeError):
                    resolved_timeout = None
        try:
            self._timeout = float(resolved_timeout) if resolved_timeout is not None else 30.0
        except (ValueError, TypeError):
            self._timeout = 30.0

    def embed(self, text: str) -> Sequence[float]:
        response = self._client.embeddings.create(model=self._deployment, input=text, timeout=self._timeout)
        return list(response.data[0].embedding)
