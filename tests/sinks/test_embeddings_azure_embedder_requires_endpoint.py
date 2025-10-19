from __future__ import annotations

import types
from pathlib import Path

import pytest

from elspeth.plugins.nodes.sinks.embeddings_store import EmbeddingsStoreSink, UpsertResponse, VectorRecord, VectorStoreClient


class _StubProvider(VectorStoreClient):
    def upsert_many(self, namespace: str, records):  # pragma: no cover - not exercised here
        return UpsertResponse(count=0, took=0.0, namespace=namespace)


def test_embeddings_azure_openai_embedder_requires_endpoint(tmp_path: Path):
    with pytest.raises(Exception):
        EmbeddingsStoreSink(
            provider="pgvector",
            dsn="postgresql://example",
            provider_factory=lambda name, opts: _StubProvider(),
            # Missing endpoint should raise when vector is absent and embedder is needed
            embed_model={"provider": "azure_openai", "deployment": "dep"},
        ).write({"results": [{"row": {"APPID": "1"}, "response": {"content": "text"}}]}, metadata={})

