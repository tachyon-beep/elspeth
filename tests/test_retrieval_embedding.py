from __future__ import annotations

import importlib
import sys
import types
from types import ModuleType
from typing import Any

import pytest

from elspeth.core.validation import ConfigurationError


class StubEmbeddingResponse:
    def __init__(self, embedding: list[float]):
        self.data = [types.SimpleNamespace(embedding=embedding)]


@pytest.fixture
def openai_stub(monkeypatch):
    module = types.ModuleType("openai")
    setattr(module, "_stub_instances", [])

    class StubClient:
        def __init__(self, **kwargs: Any):
            self.config = kwargs
            self.calls: list[tuple[str, str]] = []
            getattr(module, "_stub_instances").append(self)

        class _Embeddings:
            def __init__(self, parent: "StubClient"):
                self._parent = parent

            def create(self, model: str, **kwargs: Any):
                prompt = kwargs.get("input", "")
                self._parent.calls.append((model, prompt))
                return StubEmbeddingResponse([0.1, 0.2])

        @property
        def embeddings(self):
            return self._Embeddings(self)

    setattr(module, "OpenAI", StubClient)
    setattr(module, "AzureOpenAI", StubClient)

    monkeypatch.setitem(sys.modules, "openai", module)
    # Clear any cached imports of embedding module to force reimport with stub
    sys.modules.pop("elspeth.retrieval.embedding", None)
    yield module
    sys.modules.pop("openai", None)
    sys.modules.pop("elspeth.retrieval.embedding", None)


def _import_embedding():
    return importlib.import_module("elspeth.retrieval.embedding")


def _latest_stub_instance(stub_module: ModuleType) -> Any:
    instances: list[Any] = getattr(stub_module, "_stub_instances")
    return instances[-1]


@pytest.mark.usefixtures("openai_stub")
def test_openai_embedder_requires_api_key(monkeypatch):
    embedding_module = _import_embedding()

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        embedding_module.OpenAIEmbedder(model="text-embedding-3", api_key=None)


def test_openai_embedder_uses_client(openai_stub, monkeypatch):
    embedding_module = _import_embedding()

    monkeypatch.setenv("OPENAI_API_KEY", "token")
    embedder = embedding_module.OpenAIEmbedder(model="text-embedding-3", api_key=None)

    vector = embedder.embed("prompt")

    assert vector == [0.1, 0.2]
    client = _latest_stub_instance(openai_stub)
    assert client.calls[0] == ("text-embedding-3", "prompt")


def test_azure_openai_embedder_requires_endpoint(monkeypatch):
    embedding_module = _import_embedding()

    with pytest.raises(ConfigurationError):
        embedding_module.AzureOpenAIEmbedder(endpoint=None, deployment="model", api_key="key")


def test_azure_openai_embedder_uses_env(openai_stub, monkeypatch):
    embedding_module = _import_embedding()

    # Security note:
    # This test uses a non-approved endpoint (https://example) to avoid any
    # dependency on real Azure endpoints. We scope the relaxation strictly to
    # tests by switching secure mode to DEVELOPMENT here. Production code uses
    # get_secure_mode() and remains STRICT/STANDARD as configured.
    monkeypatch.setenv("ELSPETH_SECURE_MODE", "development")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "secret")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-05-13")

    embedder = embedding_module.AzureOpenAIEmbedder(endpoint=None, deployment="model", api_key=None, api_version=None)
    vector = embedder.embed("input")

    assert vector == [0.1, 0.2]
    client = _latest_stub_instance(openai_stub)
    assert client.config["azure_endpoint"] == "https://example"
    assert client.calls[0] == ("model", "input")
