"""Embedding providers used for retrieval services."""

from __future__ import annotations

import os
from typing import Sequence

from elspeth.core.validation import ConfigurationError


class Embedder:
    """Base embedding provider."""

    def embed(self, text: str) -> Sequence[float]:  # pragma: no cover - interface
        raise NotImplementedError


class OpenAIEmbedder(Embedder):
    """OpenAI embedding provider."""

    def __init__(self, *, model: str, api_key: str | None = None):
        try:
            from openai import OpenAI  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("openai package is required for OpenAI embeddings") from exc

        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ConfigurationError("OpenAI embeddings require an API key via 'api_key' or OPENAI_API_KEY")
        self._client = OpenAI(api_key=key)
        self._model = model

    def embed(self, text: str) -> Sequence[float]:
        response = self._client.embeddings.create(model=self._model, input=text)
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
    ) -> None:
        try:
            from openai import AzureOpenAI  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("openai package >=1.0 with Azure support is required for Azure embeddings") from exc

        endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        if not endpoint:
            raise ConfigurationError("Azure OpenAI embeddings require 'endpoint' or AZURE_OPENAI_ENDPOINT")

        key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        if not key:
            raise ConfigurationError("Azure OpenAI embeddings require 'api_key' or AZURE_OPENAI_API_KEY")

        version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-13")

        self._client = AzureOpenAI(
            api_key=key,
            azure_endpoint=endpoint,
            api_version=version,
        )
        self._deployment = deployment

    def embed(self, text: str) -> Sequence[float]:
        response = self._client.embeddings.create(model=self._deployment, input=text)
        return list(response.data[0].embedding)
