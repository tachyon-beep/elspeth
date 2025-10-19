from __future__ import annotations

import importlib
import os
import sys
import types

import pytest


@pytest.fixture
def openai_stub(monkeypatch):
    module = types.ModuleType("openai")

    class StubClient:
        def __init__(self, **kwargs):  # pragma: no cover - simple stub
            self.kwargs = kwargs

        class _Embeddings:
            def create(self, **kwargs):  # pragma: no cover - not exercised here
                return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[0.0])])

        @property
        def embeddings(self):  # pragma: no cover - not exercised here
            return self._Embeddings()

    module.OpenAI = StubClient
    module.AzureOpenAI = StubClient
    monkeypatch.setitem(sys.modules, "openai", module)
    try:
        yield module
    finally:
        sys.modules.pop("openai", None)


def test_openai_embedder_timeout_from_env(openai_stub, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "token")
    monkeypatch.setenv("ELSPETH_EMBEDDING_TIMEOUT", "7.5")
    sys.modules.pop("elspeth.retrieval.embedding", None)
    embedding = importlib.import_module("elspeth.retrieval.embedding")

    embedder = embedding.OpenAIEmbedder(model="text-embedding", api_key=None)
    assert getattr(embedder, "_timeout") == 7.5


def test_azure_openai_embedder_timeout_from_env(openai_stub, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-05-13")
    monkeypatch.setenv("ELSPETH_EMBEDDING_TIMEOUT", "12")
    sys.modules.pop("elspeth.retrieval.embedding", None)
    embedding = importlib.import_module("elspeth.retrieval.embedding")

    embedder = embedding.AzureOpenAIEmbedder(endpoint=None, deployment="dep")
    assert getattr(embedder, "_timeout") == 12.0
