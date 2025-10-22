"""High-level retrieval service using vector stores and embedders."""

from __future__ import annotations

from typing import Iterable, Mapping

from elspeth.core.security import validate_azure_openai_endpoint
from elspeth.retrieval.embedding import AzureOpenAIEmbedder, Embedder, OpenAIEmbedder
from elspeth.retrieval.providers import QueryResult, VectorQueryClient, create_query_client


class RetrievalService:
    """Compose an embedder with a vector query client."""

    def __init__(self, *, client: VectorQueryClient, embedder: Embedder) -> None:
        self._client = client
        self._embedder = embedder

    def retrieve(
        self,
        namespace: str,
        query_text: str,
        *,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> Iterable[QueryResult]:
        vector = self._embedder.embed(query_text)
        return self._client.query(namespace, vector, top_k=top_k, min_score=min_score)


def create_retrieval_service(config: Mapping[str, object]) -> RetrievalService:
    """Construct a RetrievalService from a config mapping.

    Expects keys:
    - "provider": retrieval provider name (e.g., "pgvector", "azure_search")
    - "provider_options": provider-specific options mapping
    - "embed_model": embedding provider configuration mapping

    Returns:
        RetrievalService: composed of a vector query client and an embedder.
    """
    provider = str(config.get("provider") or "").lower()
    provider_options_raw = config.get("provider_options") or {}
    if not isinstance(provider_options_raw, Mapping):
        raise TypeError("provider_options must be a mapping")
    provider_options = dict(provider_options_raw)

    embed_cfg = config.get("embed_model")
    if not isinstance(embed_cfg, Mapping):
        raise TypeError("embed_model configuration is required for retrieval service")

    embedder = _create_embedder(embed_cfg)
    client = create_query_client(provider, provider_options)
    return RetrievalService(client=client, embedder=embedder)


def _create_embedder(config: Mapping[str, object]) -> Embedder:
    provider = str(config.get("provider") or "").lower()
    if provider == "openai":
        model = str(config.get("model") or "text-embedding-3-large")
        api_key_raw = config.get("api_key")
        api_key = str(api_key_raw) if api_key_raw is not None else None
        timeout_raw = config.get("timeout")
        timeout: float | int | None
        if isinstance(timeout_raw, (int, float, str)):
            try:
                timeout = float(timeout_raw)
            except (ValueError, TypeError):
                timeout = None
        else:
            timeout = None
        # Pass only non-None arguments to satisfy type checker without breaking tests
        if timeout is not None:
            return OpenAIEmbedder(model=model, api_key=api_key, timeout=timeout)
        return OpenAIEmbedder(model=model, api_key=api_key)
    if provider == "azure_openai":
        endpoint_raw = config.get("endpoint")
        endpoint = str(endpoint_raw) if endpoint_raw is not None else None
        deployment = str(config.get("deployment") or "")
        api_key_raw = config.get("api_key")
        api_key = str(api_key_raw) if api_key_raw is not None else None
        api_version_raw = config.get("api_version")
        api_version = str(api_version_raw) if api_version_raw is not None else None
        timeout_raw = config.get("timeout")
        if isinstance(timeout_raw, (int, float, str)):
            try:
                timeout_val = float(timeout_raw)
            except (ValueError, TypeError):
                timeout_val = None
        else:
            timeout_val = None
        if endpoint:
            validate_azure_openai_endpoint(endpoint)
        # Pass only non-None arguments to satisfy type checker without breaking tests
        if timeout_val is not None:
            return AzureOpenAIEmbedder(
                endpoint=endpoint,
                deployment=deployment,
                api_key=api_key,
                api_version=api_version,
                timeout=timeout_val,
            )
        return AzureOpenAIEmbedder(
            endpoint=endpoint,
            deployment=deployment,
            api_key=api_key,
            api_version=api_version,
        )
    raise ValueError(f"Unsupported embed_model provider '{provider}'")
