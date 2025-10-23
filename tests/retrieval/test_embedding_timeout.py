from __future__ import annotations

import os

import pytest


def test_openai_embedder_timeout_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch OpenAI client to avoid real client construction
    class _DummyOpenAI:
        def __init__(self, *args, **kwargs):  # noqa: D401
            pass

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("elspeth.retrieval.embedding.OpenAI", _DummyOpenAI)

    from elspeth.retrieval.embedding import OpenAIEmbedder

    # Valid env value
    monkeypatch.setenv("ELSPETH_EMBEDDING_TIMEOUT", "12.25")
    e1 = OpenAIEmbedder(model="m")
    assert abs(e1._timeout - 12.25) < 1e-9

    # Invalid env value -> default
    monkeypatch.setenv("ELSPETH_EMBEDDING_TIMEOUT", "bad")
    e2 = OpenAIEmbedder(model="m")
    assert abs(e2._timeout - 30.0) < 1e-9

    # Explicit arg wins
    monkeypatch.delenv("ELSPETH_EMBEDDING_TIMEOUT", raising=False)
    e3 = OpenAIEmbedder(model="m", timeout=9)
    assert abs(e3._timeout - 9.0) < 1e-9


def test_azure_openai_embedder_timeout_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch Azure client and endpoint validator to avoid external deps/validation
    class _DummyAzure:
        def __init__(self, *args, **kwargs):  # noqa: D401
            pass

    monkeypatch.setattr("elspeth.retrieval.embedding.AzureOpenAI", _DummyAzure)
    monkeypatch.setattr("elspeth.retrieval.embedding.validate_azure_openai_endpoint", lambda *a, **k: None)
    monkeypatch.setattr("elspeth.retrieval.embedding.get_secure_mode", lambda: None)

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-05-01")

    from elspeth.retrieval.embedding import AzureOpenAIEmbedder

    # Valid env value
    monkeypatch.setenv("ELSPETH_EMBEDDING_TIMEOUT", "7.5")
    a1 = AzureOpenAIEmbedder(endpoint=None, deployment="d")
    assert abs(a1._timeout - 7.5) < 1e-9

    # Invalid env value -> default
    monkeypatch.setenv("ELSPETH_EMBEDDING_TIMEOUT", "oops")
    a2 = AzureOpenAIEmbedder(endpoint=None, deployment="d")
    assert abs(a2._timeout - 30.0) < 1e-9

    # Explicit arg wins
    monkeypatch.delenv("ELSPETH_EMBEDDING_TIMEOUT", raising=False)
    a3 = AzureOpenAIEmbedder(endpoint=None, deployment="d", timeout=15)
    assert abs(a3._timeout - 15.0) < 1e-9
