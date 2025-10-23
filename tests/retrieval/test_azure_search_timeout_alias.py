from __future__ import annotations

import importlib


def test_azure_search_timeout_alias(monkeypatch):
    """Passing 'timeout' in options should map to request_timeout on the client."""
    import elspeth.retrieval.providers as providers

    captured: dict[str, object] = {}

    def fake_validate(endpoint, security_level=None, mode=None):  # noqa: D401
        return None

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(providers, "validate_azure_search_endpoint", fake_validate)
    monkeypatch.setattr(providers, "AzureSearchQueryClient", fake_client)

    # Use 'timeout' instead of 'request_timeout'
    providers.create_query_client(
        "azure_search",
        {
            "endpoint": "https://search-example.search.windows.net",
            "index": "experiments",
            "api_key": "token",
            "vector_field": "embedding",
            "namespace_field": "namespace",
            "content_field": "contents",
            "timeout": 5.5,
        },
    )

    assert captured["request_timeout"] == 5.5
