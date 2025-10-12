from __future__ import annotations

from dataclasses import dataclass

import pytest

from elspeth.core.plugins import PluginContext, apply_plugin_context
from elspeth.core.validation import ConfigurationError
from elspeth.plugins.outputs.embeddings_store import EmbeddingsStoreSink, UpsertResponse, VectorRecord, VectorStoreClient
from elspeth.retrieval.embedding import Embedder


class StubVectorStore(VectorStoreClient):
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[VectorRecord]]] = []

    def upsert_many(self, namespace: str, records):
        items = list(records)
        self.calls.append((namespace, items))
        return UpsertResponse(count=len(items), took=0.01, namespace=namespace)


class StubEmbedder(Embedder):
    def embed(self, text: str):
        return [0.42, 0.17, 0.91]


def _attach_context(sink: EmbeddingsStoreSink) -> None:
    suite_ctx = PluginContext(plugin_name="suite", plugin_kind="suite", security_level="official")
    experiment_ctx = suite_ctx.derive(plugin_name="experiment", plugin_kind="experiment")
    sink_ctx = experiment_ctx.derive(plugin_name="embeddings_store", plugin_kind="sink")
    apply_plugin_context(sink, sink_ctx)


def test_embeddings_sink_upserts_records_using_stub_provider():
    provider = StubVectorStore()
    sink = EmbeddingsStoreSink(
        provider="pgvector",
        dsn="postgresql://example",
        provider_factory=lambda name, _: provider,
        embed_model={"provider": "stub"},
        embedder_factory=lambda config: StubEmbedder(),
    )
    _attach_context(sink)

    results = {
        "results": [
            {
                "row": {"APPID": "A-1"},
                "response": {
                    "content": "Example answer",
                },
                "metrics": {"extra": "value"},
            }
        ]
    }
    metadata = {"security_level": "official", "retry_summary": {"total": 1}}

    sink.write(results, metadata=metadata)
    artifacts = sink.collect_artifacts()

    assert provider.calls, "expected upsert to occur"
    namespace, records = provider.calls[0]
    assert namespace == "suite.experiment.official"
    assert records[0].document_id == "A-1"
    assert records[0].vector == [0.42, 0.17, 0.91]
    assert records[0].metadata["metadata.retry_summary"] == {"total": 1}
    assert artifacts["embeddings_manifest"].metadata["count"] == 1


def test_embeddings_sink_errors_when_embeddings_missing_without_model():
    provider = StubVectorStore()
    sink = EmbeddingsStoreSink(
        provider="pgvector",
        dsn="postgresql://example",
        provider_factory=lambda name, _: provider,
    )
    _attach_context(sink)

    with pytest.raises(ConfigurationError):
        sink.write({"results": [{"row": {"APPID": "missing"}}]}, metadata={"security_level": "official"})
    assert not provider.calls
    assert sink.collect_artifacts() == {}
