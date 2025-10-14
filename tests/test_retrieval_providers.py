from __future__ import annotations

import importlib
import sys
import types

import pytest

from elspeth.core.validation import ConfigurationError


@pytest.fixture
def psycopg_stub(monkeypatch):
    module = types.ModuleType("psycopg")
    module._rows: list[tuple[str, str, str | None, float]] = []
    module._queries: list[tuple[str, tuple]] = []
    module._connect_calls: list[tuple[str, bool]] = []

    class FakeCursor:
        def __init__(self, parent):
            self._parent = parent

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            normalized = " ".join(query.split())
            self._parent._queries.append((normalized, params))

        def fetchall(self):
            return list(self._parent._rows)

    class FakeConnection:
        def __init__(self, parent):
            self._parent = parent
            self.closed = False

        def cursor(self):
            return FakeCursor(self._parent)

        def close(self):
            self.closed = True

    def connect(dsn, autocommit=True):
        module._connect_calls.append((dsn, autocommit))
        return FakeConnection(module)

    module.connect = connect

    monkeypatch.setitem(sys.modules, "psycopg", module)
    try:
        yield module
    finally:
        sys.modules.pop("psycopg", None)
        importlib.reload(sys.modules["elspeth.retrieval.providers"])


@pytest.fixture
def providers_module():
    import elspeth.retrieval.providers as providers

    return providers


def test_pgvector_query_filters_by_min_score(psycopg_stub, providers_module):
    psycopg_stub._rows = [
        ("doc-1", "context", '{"foo": 1}', 0.91),
        ("doc-2", "ignored", None, 0.25),
    ]
    providers = importlib.reload(providers_module)
    client = providers.PgVectorQueryClient(dsn="postgresql://example", table="custom_table")

    hits = list(client.query("suite.experiment.official", [0.1, 0.2], top_k=5, min_score=0.5))

    assert len(hits) == 1
    assert hits[0].document_id == "doc-1"
    assert hits[0].metadata == {"foo": 1}
    assert psycopg_stub._connect_calls == [("postgresql://example", True)]
    executed_query, params = psycopg_stub._queries[0]
    assert "FROM custom_table" in executed_query
    assert params[1] == "suite.experiment.official"


def test_pgvector_vector_literal_format(psycopg_stub, providers_module):
    providers = importlib.reload(providers_module)
    client = providers.PgVectorQueryClient(dsn="postgresql://example", table="elspeth_rag")

    literal = client._vector_literal([0.123456789, 1, 2])

    assert literal == "[0.123456789,1,2]"


def test_create_query_client_requires_dsn(providers_module):
    providers = importlib.reload(providers_module)
    with pytest.raises(ConfigurationError):
        providers.create_query_client("pgvector", {"table": "missing_dsn"})


@pytest.fixture
def azure_modules(monkeypatch):
    base = types.ModuleType("azure")
    search_pkg = types.ModuleType("azure.search")
    documents_module = types.ModuleType("azure.search.documents")
    core_pkg = types.ModuleType("azure.core")
    credentials_module = types.ModuleType("azure.core.credentials")

    class StubCredential:
        def __init__(self, key):
            self.key = key

    class StubDocument(dict):
        def __getattr__(self, item):  # pragma: no cover - defensive
            return self[item]

    class StubSearchClient:
        def __init__(self, *, endpoint, index_name, credential):
            self.endpoint = endpoint
            self.index_name = index_name
            self.credential = credential
            self.calls: list[dict[str, object]] = []

        def search(self, *, search_text, filter, vector, top_k, vector_fields):
            self.calls.append(
                {
                    "search_text": search_text,
                    "filter": filter,
                    "vector": list(vector),
                    "top_k": top_k,
                    "vector_fields": vector_fields,
                }
            )
            return [
                StubDocument(
                    {
                        "document_id": "doc-1",
                        "contents": "trace",
                        "metadata": {"region": "test"},
                        "@search.score": 0.83,
                    }
                )
            ]

    documents_module.SearchClient = StubSearchClient
    credentials_module.AzureKeyCredential = StubCredential
    search_pkg.documents = documents_module
    core_pkg.credentials = credentials_module

    monkeypatch.setitem(sys.modules, "azure", base)
    monkeypatch.setitem(sys.modules, "azure.search", search_pkg)
    monkeypatch.setitem(sys.modules, "azure.search.documents", documents_module)
    monkeypatch.setitem(sys.modules, "azure.core", core_pkg)
    monkeypatch.setitem(sys.modules, "azure.core.credentials", credentials_module)

    try:
        yield documents_module
    finally:
        for name in [
            "azure.core.credentials",
            "azure.core",
            "azure.search.documents",
            "azure.search",
            "azure",
        ]:
            sys.modules.pop(name, None)


def test_create_query_client_azure_success(monkeypatch, azure_modules, providers_module):
    providers = importlib.reload(providers_module)
    monkeypatch.setenv("AZURE_SEARCH_KEY", "secret-token")

    client = providers.create_query_client(
        "azure_search",
        {
            "endpoint": "https://search.example",
            "index": "experiments",
            "api_key_env": "AZURE_SEARCH_KEY",
            "vector_field": "embedding",
            "namespace_field": "namespace",
            "content_field": "contents",
        },
    )

    results = list(client.query("suite.ns", [0.4, 0.2], top_k=3, min_score=0.5))

    assert len(results) == 1
    assert results[0].metadata == {"region": "test"}
    assert results[0].score == pytest.approx(0.83)
