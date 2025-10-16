from __future__ import annotations

import sys
import types

import pytest

from elspeth.core.plugin_context import PluginContext, apply_plugin_context
from elspeth.core.validation import ConfigurationError
from elspeth.plugins.nodes.sinks.embeddings_store import EmbeddingsStoreSink, UpsertResponse, VectorRecord, VectorStoreClient
from elspeth.retrieval.embedding import Embedder


class StubVectorStore(VectorStoreClient):
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[VectorRecord]]] = []

    def upsert_many(self, namespace: str, records):
        items = list(records)
        self.calls.append((namespace, items))
        return UpsertResponse(count=len(items), took=0.01, namespace=namespace)


class RecordingEmbedder(Embedder):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed(self, text: str):
        self.calls.append(text)
        return [0.9, 0.1]


class StubEmbedder(Embedder):
    def embed(self, text: str):
        return [0.42, 0.17, 0.91]


def _attach_context(sink: EmbeddingsStoreSink) -> None:
    suite_ctx = PluginContext(plugin_name="suite", plugin_kind="suite", security_level="official", determinism_level="none")
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
    metadata = {"security_level": "OFFICIAL", "determinism_level": "guaranteed", "retry_summary": {"total": 1}}

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
        sink.write({"results": [{"row": {"APPID": "missing"}}]}, metadata={"security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    assert not provider.calls
    assert sink.collect_artifacts() == {}


def test_embeddings_sink_embeds_text_when_vector_missing():
    provider = StubVectorStore()
    embedder = RecordingEmbedder()
    sink = EmbeddingsStoreSink(
        provider="pgvector",
        dsn="postgresql://example",
        provider_factory=lambda name, _: provider,
        embed_model={"provider": "openai", "model": "irrelevant"},
        embedder_factory=lambda config: embedder,
    )
    _attach_context(sink)

    sink.write(
        {
            "results": [
                {
                    "row": {"APPID": "auto"},
                    "response": {"content": "raw text"},
                }
            ]
        },
        metadata={"security_level": "OFFICIAL", "determinism_level": "guaranteed", "run_id": "run-1"},
    )

    _, records = provider.calls[0]
    assert records[0].vector == [0.9, 0.1]
    assert embedder.calls == ["raw text"]


def test_embeddings_sink_metadata_falls_back_to_run_metadata():
    provider = StubVectorStore()
    sink = EmbeddingsStoreSink(
        provider="pgvector",
        dsn="postgresql://example",
        provider_factory=lambda name, _: provider,
        embed_model={"provider": "openai", "model": "irrelevant"},
        embedder_factory=lambda config: RecordingEmbedder(),
        metadata_fields=["row.record_id", "metadata.ticket"],
    )
    _attach_context(sink)

    sink.write(
        {
            "results": [
                {
                    "row": {"APPID": "A-1"},
                    "response": {"content": "text"},
                }
            ]
        },
        metadata={"security_level": "OFFICIAL", "determinism_level": "guaranteed", "ticket": "INC-123"},
    )

    _, records = provider.calls[0]
    assert records[0].metadata["metadata.ticket"] == "INC-123"


def test_embeddings_sink_azure_provider_requires_api_key_env(monkeypatch):
    """Test that azure_search provider requires explicit api_key_env configuration."""
    monkeypatch.delenv("AZURE_SEARCH_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="api_key_env"):
        EmbeddingsStoreSink(
            provider="azure_search",
            namespace="suite.ns",
            provider_options={
                "endpoint": "https://example",
                "index": "idx",
                "vector_field": "embedding",
                "id_field": "document_id",
                "namespace_field": "namespace",
            },
            embed_model={"provider": "openai", "model": "irrelevant"},
            embedder_factory=lambda config: RecordingEmbedder(),
        )


def test_embeddings_sink_azure_provider_uses_env_key(monkeypatch):
    created = {}

    class StubAzureClient:
        def __init__(self, **kwargs):
            created.update(kwargs)

        def upsert_many(self, namespace: str, records):  # pragma: no cover - sink finalization
            return UpsertResponse(count=0, took=0.0, namespace=namespace)

        def close(self):  # pragma: no cover - no-op
            return None

    monkeypatch.setenv("AZURE_SEARCH_KEY", "token")
    monkeypatch.setattr(
        "elspeth.plugins.nodes.sinks.embeddings_store.AzureSearchVectorClient",
        StubAzureClient,
    )

    sink = EmbeddingsStoreSink(
        provider="azure_search",
        namespace="suite.ns",
        provider_options={
            "endpoint": "https://example",
            "index": "idx",
            "api_key_env": "AZURE_SEARCH_KEY",
            "vector_field": "embedding",
            "id_field": "document_id",
            "namespace_field": "namespace",
        },
        embed_model={"provider": "openai", "model": "irrelevant"},
        embedder_factory=lambda config: RecordingEmbedder(),
    )

    assert created["endpoint"] == "https://example"
    assert created["index"] == "idx"
    assert sink.provider_name == "azure_search"


def test_embeddings_sink_collect_artifacts_resets_manifest():
    provider = StubVectorStore()
    sink = EmbeddingsStoreSink(
        provider="pgvector",
        dsn="postgresql://example",
        provider_factory=lambda name, _: provider,
        embed_model={"provider": "openai", "model": "irrelevant"},
        embedder_factory=lambda config: RecordingEmbedder(),
    )
    _attach_context(sink)

    sink.write(
        {
            "results": [
                {
                    "row": {"APPID": "A-1"},
                    "response": {"content": "text", "metrics": {"embedding": [0.1, 0.2]}},
                }
            ]
        },
        metadata={"security_level": "OFFICIAL", "determinism_level": "guaranteed"},
    )

    manifest = sink.collect_artifacts()
    assert manifest["embeddings_manifest"].metadata["count"] == 1
    assert sink.collect_artifacts() == {}


def test_embeddings_sink_batches_results():
    provider = StubVectorStore()
    sink = EmbeddingsStoreSink(
        provider="pgvector",
        dsn="postgresql://example",
        provider_factory=lambda name, _: provider,
        embed_model={"provider": "openai", "model": "irrelevant"},
        embedder_factory=lambda config: RecordingEmbedder(),
        batch_size=1,
    )
    _attach_context(sink)

    sink.write(
        {
            "results": [
                {"row": {"APPID": "A-1"}, "response": {"content": "one", "metrics": {"embedding": [0.1, 0.2]}}},
                {"row": {"APPID": "A-2"}, "response": {"content": "two", "metrics": {"embedding": [0.3, 0.4]}}},
            ]
        },
        metadata={"security_level": "OFFICIAL", "determinism_level": "guaranteed"},
    )

    assert len(provider.calls) == 2
    manifest = sink.collect_artifacts()
    assert manifest["embeddings_manifest"].metadata["batch_count"] == 2


def test_embeddings_sink_finalize_closes_client():
    class ClosingProvider(StubVectorStore):
        def __init__(self):
            super().__init__()
            self.closed = False

        def close(self):
            self.closed = True

    provider = ClosingProvider()
    sink = EmbeddingsStoreSink(
        provider="pgvector",
        dsn="postgresql://example",
        provider_factory=lambda name, _: provider,
        embed_model={"provider": "openai", "model": "irrelevant"},
        embedder_factory=lambda config: RecordingEmbedder(),
    )
    _attach_context(sink)

    sink.finalize({}, metadata={})
    assert provider.closed is True


def test_pgvector_conflict_clause_skip(monkeypatch):
    stub = types.ModuleType("psycopg")

    # Mock psycopg.sql module for SQL injection protection
    class MockSQL:
        def __init__(self, text):
            self.text = text

        def format(self, *args):
            # Replace {} placeholders with arguments in order
            result = self.text
            for arg in args:
                if isinstance(arg, MockIdentifier):
                    result = result.replace("{}", arg.name, 1)
                elif isinstance(arg, MockSQL):
                    result = result.replace("{}", arg.text, 1)
                else:
                    result = result.replace("{}", str(arg), 1)
            return MockSQL(result)  # Return MockSQL object for chaining

    class MockIdentifier:
        def __init__(self, name):
            self.name = name

    sql_module = types.ModuleType("sql")
    sql_module.SQL = MockSQL
    sql_module.Identifier = MockIdentifier
    stub.sql = sql_module

    class Cursor:
        def __init__(self, module):
            self.module = module

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            # Handle both string and MockSQL objects
            if isinstance(query, MockSQL):
                query_str = query.text
            else:
                query_str = query
            self.module.queries.append((" ".join(query_str.split()), params))

        def fetchall(self):  # pragma: no cover - ensure compatibility
            return []

    class Connection:
        def __init__(self, module):
            self.module = module
            self.closed = False

        def cursor(self):
            return Cursor(self.module)

        def close(self):
            self.closed = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.close()
            return False

    stub.queries = []

    def connect(dsn, autocommit=True):
        stub.connect_args = (dsn, autocommit)
        return Connection(stub)

    stub.connect = connect
    stub.Connection = Connection  # Make Connection importable from stub

    monkeypatch.setitem(sys.modules, "psycopg", stub)
    monkeypatch.setitem(sys.modules, "psycopg.sql", sql_module)
    # Clear cached import to force reimport with stub
    sys.modules.pop("elspeth.plugins.nodes.sinks.embeddings_store", None)
    # Re-import with stub in place
    import elspeth.plugins.nodes.sinks.embeddings_store as store_module_reloaded

    client = store_module_reloaded.PgVectorClient(dsn="postgresql://example", table="table", upsert_conflict="skip")
    record = VectorRecord(document_id="one", vector=[0.1, 0.2], text="value", metadata={}, security_level="official")
    client.upsert_many("namespace", [record])

    assert "NOTHING" in stub.queries[-1][0]
    assert stub.connect_args == ("postgresql://example", True)

    # Test with unknown policy (should default to "replace")
    client._conflict_policy = "unknown"
    query = client._build_insert_query()
    assert "UPDATE SET" in query.text

    sys.modules.pop("psycopg", None)
    sys.modules.pop("psycopg.sql", None)
