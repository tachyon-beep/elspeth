from __future__ import annotations

import pytest

import elspeth.retrieval.service as service_module
from elspeth.retrieval.providers import QueryResult
from elspeth.retrieval.service import RetrievalService, _create_embedder, create_retrieval_service


class StubClient:
    def __init__(self):
        self.calls: list[tuple[str, list[float], int, float]] = []

    def query(self, namespace: str, vector, *, top_k: int, min_score: float):
        self.calls.append((namespace, list(vector), top_k, min_score))
        return [QueryResult(document_id="doc-1", text="payload", score=0.9, metadata={})]


def test_create_retrieval_service_with_openai_embedder(monkeypatch):
    created = {}

    def stub_embedder(*, model: str, api_key: str | None = None):
        created["model"] = model
        created["api_key"] = api_key

        class _StubEmbedder:
            def embed(self, text: str):
                created["text"] = text
                return [0.42, 0.17]

        return _StubEmbedder()

    stub_client = StubClient()

    def stub_create_query_client(provider: str, options):
        created["provider"] = provider
        created["options"] = dict(options)
        return stub_client

    from elspeth.retrieval import service as service_module

    monkeypatch.setattr(service_module, "OpenAIEmbedder", stub_embedder)
    monkeypatch.setattr(service_module, "create_query_client", stub_create_query_client)

    retrieval = create_retrieval_service(
        {
            "provider": "pgvector",
            "provider_options": {"dsn": "postgresql://example"},
            "embed_model": {"provider": "openai", "model": "text-embedding", "api_key": "token"},
        }
    )

    results = list(retrieval.retrieve("suite.ns", "question", top_k=3, min_score=0.5))

    assert results[0].document_id == "doc-1"
    assert created["model"] == "text-embedding"
    assert created["provider"] == "pgvector"
    assert created["text"] == "question"
    assert stub_client.calls[0][1] == [0.42, 0.17]


def test_create_retrieval_service_requires_embed_model():
    with pytest.raises(TypeError):
        create_retrieval_service({"provider": "pgvector", "provider_options": {"dsn": "postgres"}})


def test_create_embedder_unsupported_provider():
    with pytest.raises(ValueError):
        _create_embedder({"provider": "unknown"})


def test_create_embedder_validates_azure_endpoint(monkeypatch):
    captured = {}

    def fake_validate(endpoint, security_level=None, mode=None):
        captured["endpoint"] = endpoint

    def fake_embedder(**kwargs):
        captured["kwargs"] = kwargs
        return "EMBEDDER"

    monkeypatch.setattr(service_module, "validate_azure_openai_endpoint", fake_validate)
    monkeypatch.setattr(service_module, "AzureOpenAIEmbedder", fake_embedder)

    config = {
        "provider": "azure_openai",
        "endpoint": "https://my-resource.openai.azure.com",
        "deployment": "embedding",
        "api_key": "secret",
        "api_version": "2024-05-13",
    }

    embedder = _create_embedder(config)

    assert embedder == "EMBEDDER"
    assert captured["endpoint"] == "https://my-resource.openai.azure.com"
    assert captured["kwargs"]["endpoint"] == config["endpoint"]


def test_create_embedder_rejects_unapproved_azure_endpoint(monkeypatch):
    def fake_validate(endpoint, security_level=None, mode=None):
        raise ValueError("not approved")

    monkeypatch.setattr(service_module, "validate_azure_openai_endpoint", fake_validate)

    with pytest.raises(ValueError, match="not approved"):
        _create_embedder(
            {
                "provider": "azure_openai",
                "endpoint": "https://evil.example.com",
                "deployment": "embedding",
                "api_key": "key",
                "api_version": "2024-05-13",
            }
        )


def test_retrieval_service_passthrough_calls():
    class StaticEmbedder:
        def embed(self, text: str):
            return [1, 0, 0]

    client = StubClient()
    service = RetrievalService(client=client, embedder=StaticEmbedder())

    list(service.retrieve("suite.ns", "query", top_k=2, min_score=0.3))

    assert client.calls == [("suite.ns", [1, 0, 0], 2, 0.3)]
