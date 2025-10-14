from __future__ import annotations

import sys
import types

import pytest

from elspeth.core.validation import ConfigurationError


class StubEmbeddingResponse:
    def __init__(self, embedding):
        self.data = [types.SimpleNamespace(embedding=embedding)]


@pytest.fixture
def openai_stub(monkeypatch):
    module = types.ModuleType("openai")

    class StubClient:
        def __init__(self, **kwargs):
            self.config = kwargs
            self.calls = []

        class _Embeddings:
            def __init__(self, parent):
                self._parent = parent

            def create(self, model: str, input: str):
                self._parent.calls.append((model, input))
                return StubEmbeddingResponse([0.1, 0.2])

        @property
        def embeddings(self):
            return self._Embeddings(self)

    module.OpenAI = StubClient
    module.AzureOpenAI = StubClient

    monkeypatch.setitem(sys.modules, "openai", module)
    yield module
    sys.modules.pop("openai", None)


def test_openai_embedder_requires_api_key(openai_stub, monkeypatch):
    import elspeth.retrieval.embedding as embedding_module

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        embedding_module.OpenAIEmbedder(model="text-embedding-3", api_key=None)


def test_openai_embedder_uses_client(openai_stub, monkeypatch):
    import elspeth.retrieval.embedding as embedding_module

    monkeypatch.setenv("OPENAI_API_KEY", "token")
    embedder = embedding_module.OpenAIEmbedder(model="text-embedding-3", api_key=None)

    vector = embedder.embed("prompt")

    assert vector == [0.1, 0.2]
    assert embedder._client.calls[0] == ("text-embedding-3", "prompt")


def test_azure_openai_embedder_requires_endpoint(monkeypatch):
    import elspeth.retrieval.embedding as embedding_module

    with pytest.raises(ConfigurationError):
        embedding_module.AzureOpenAIEmbedder(endpoint=None, deployment="model", api_key="key")


def test_azure_openai_embedder_uses_env(openai_stub, monkeypatch):
    import elspeth.retrieval.embedding as embedding_module

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-05-13")

    embedder = embedding_module.AzureOpenAIEmbedder(endpoint=None, deployment="model", api_key=None, api_version=None)
    vector = embedder.embed("input")

    assert vector == [0.1, 0.2]
    assert embedder._client.config["azure_endpoint"] == "https://example"
    assert embedder._client.calls[0] == ("model", "input")
