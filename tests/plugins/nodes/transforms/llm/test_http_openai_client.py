from __future__ import annotations

from typing import Any

import pytest

from elspeth.plugins.nodes.transforms.llm.openai_http import HttpOpenAIClient


def test_http_openai_client_mounts_http_for_localhost() -> None:
    client = HttpOpenAIClient(api_base="http://localhost:8080", model="gpt-test")
    # requests.Session stores adapters keyed by scheme prefixes
    assert "http://" in client.session.adapters
    assert "https://" in client.session.adapters


def test_http_openai_client_generate(monkeypatch) -> None:
    client = HttpOpenAIClient(api_base="http://localhost:8080", model="gpt-test", timeout=1.5)

    captured: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None:  # noqa: D401 - simple stub
            """No-op status raiser"""

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "hello"}}]}

    def _fake_post(url, json, headers, timeout):  # noqa: ANN001 - testing shim
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(client.session, "post", _fake_post)

    out = client.generate(system_prompt="sys", user_prompt="hi")
    assert out["content"] == "hello"
    assert captured["url"].endswith("/v1/chat/completions")
    # Ensure the client respected the configured timeout
    assert captured["timeout"] == 1.5


def test_http_openai_client_rejects_non_localhost_http():
    # http:// must be restricted to localhost/loopback by endpoint validator
    with pytest.raises(ValueError):
        _ = HttpOpenAIClient(api_base="http://example.com", model="gpt-test")
