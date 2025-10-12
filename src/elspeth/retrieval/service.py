"""High-level retrieval service using vector stores and embedders."""

from __future__ import annotations

from typing import Iterable, Mapping

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
    provider = str(config.get("provider") or "").lower()
    provider_options = dict(config.get("provider_options") or {})

    embed_cfg = config.get("embed_model")
    if not isinstance(embed_cfg, Mapping):
        raise TypeError("embed_model configuration is required for retrieval service")

    embedder = _create_embedder(embed_cfg)
    client = create_query_client(provider, provider_options)
    return RetrievalService(client=client, embedder=embedder)


def _create_embedder(config: Mapping[str, object]) -> Embedder:
    provider = str(config.get("provider") or "").lower()
    if provider == "openai":
        return OpenAIEmbedder(model=str(config.get("model") or "text-embedding-3-large"), api_key=config.get("api_key"))
    if provider == "azure_openai":
        return AzureOpenAIEmbedder(
            endpoint=config.get("endpoint"),
            deployment=str(config.get("deployment") or ""),
            api_key=config.get("api_key"),
            api_version=config.get("api_version"),
        )
    raise ValueError(f"Unsupported embed_model provider '{provider}'")
