from __future__ import annotations

import importlib


def test_openai_embedder_timeout_passed(monkeypatch):
    captured = {}

    def stub_embedder(*, model, api_key=None, timeout=None):
        captured["model"] = model
        captured["api_key"] = api_key
        captured["timeout"] = timeout

        class E:
            def embed(self, text):
                return [0.0]

        return E()

    svc = importlib.import_module("elspeth.retrieval.service")
    monkeypatch.setattr(svc, "OpenAIEmbedder", stub_embedder)

    _ = svc._create_embedder({"provider": "openai", "model": "text-emb", "api_key": "k", "timeout": 12})

    assert captured["timeout"] == 12


def test_azure_openai_embedder_timeout_passed(monkeypatch):
    captured = {}

    def stub_validate(endpoint, security_level=None, mode=None):
        captured["endpoint"] = endpoint

    def stub_embedder(*, endpoint, deployment, api_key=None, api_version=None, timeout=None):
        captured["endpoint"] = endpoint
        captured["deployment"] = deployment
        captured["api_key"] = api_key
        captured["api_version"] = api_version
        captured["timeout"] = timeout

        class E:
            def embed(self, text):
                return [0.0]

        return E()

    svc = importlib.import_module("elspeth.retrieval.service")
    monkeypatch.setattr(svc, "validate_azure_openai_endpoint", stub_validate)
    monkeypatch.setattr(svc, "AzureOpenAIEmbedder", stub_embedder)

    _ = svc._create_embedder(
        {
            "provider": "azure_openai",
            "endpoint": "https://good.openai.azure.com",
            "deployment": "dep",
            "api_key": "k",
            "api_version": "2024-05-13",
            "timeout": 7.5,
        }
    )

    assert captured["timeout"] == 7.5
