from __future__ import annotations

import os
from pathlib import Path

import pytest

from elspeth.core.base.plugin_context import PluginContext, apply_plugin_context
from elspeth.plugins.nodes.sinks.embeddings_store import Embedder, EmbeddingsStoreSink
from elspeth.retrieval.providers import PgVectorQueryClient
from elspeth.retrieval.service import RetrievalService


class StubEmbedder(Embedder):
    def __init__(self, vector):
        self._vector = list(vector)

    def embed(self, text: str):
        return list(self._vector)


def _attach_sink_context(sink: EmbeddingsStoreSink, *, security_level: str = "official") -> None:
    suite_ctx = PluginContext(plugin_name="suite", plugin_kind="suite", security_level=security_level)
    experiment_ctx = suite_ctx.derive(plugin_name="experiment", plugin_kind="experiment")
    sink_ctx = experiment_ctx.derive(plugin_name="embeddings_store", plugin_kind="sink")
    apply_plugin_context(sink, sink_ctx)


@pytest.mark.integration
def test_embeddings_pgvector_round_trip(tmp_path: Path) -> None:
    dsn = os.getenv("ELSPETH_PG_VECTOR_DSN")
    if not dsn:
        pytest.skip("Set ELSPETH_PG_VECTOR_DSN to run pgvector integration test")

    try:
        import psycopg  # type: ignore
    except ModuleNotFoundError:  # pragma: no cover - environment dependent
        pytest.skip("psycopg package required for pgvector integration test")

    conn = psycopg.connect(dsn, autocommit=True)
    namespace = "suite.experiment.official"
    vector_dimension = 1536
    embedding_vector = [round(((index % 5) + 1) * 0.1, 1) for index in range(vector_dimension)]
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS elspeth_rag (
                    namespace TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    embedding VECTOR(1536),
                    contents TEXT,
                    metadata JSONB,
                    security_level TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (namespace, document_id)
                )
                """
            )

        sink = EmbeddingsStoreSink(
            provider="pgvector",
            dsn=dsn,
        )
        _attach_sink_context(sink)

        results = {
            "results": [
                {
                    "row": {"APPID": "record-1"},
                    "response": {
                        "content": "Context payload",
                        "metrics": {"embedding": embedding_vector},
                    },
                }
            ]
        }
        sink.write(results, metadata={"security_level": "OFFICIAL", "determinism_level": "guaranteed"})

        service = RetrievalService(
            client=PgVectorQueryClient(dsn=dsn, table="elspeth_rag"),
            embedder=StubEmbedder(embedding_vector),
        )

        hits = list(service.retrieve(namespace, "ignored", top_k=1, min_score=0.0))

        assert len(hits) == 1
        assert hits[0].document_id == "record-1"

    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM elspeth_rag WHERE namespace = %s", (namespace,))
        conn.close()
