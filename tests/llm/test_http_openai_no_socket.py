from __future__ import annotations

from types import SimpleNamespace

from elspeth.plugins.nodes.transforms.llm.openai_http import HttpOpenAIClient


class _FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    def raise_for_status(self) -> None:  # noqa: D401
        return None

    def json(self) -> dict[str, object]:  # noqa: D401
        return self._payload


def test_http_openai_client_generate_without_socket(monkeypatch):
    # Patch requests.Session in the module to avoid real network sockets
    def _fake_session():  # noqa: D401
        obj = SimpleNamespace()
        # Simulate a successful chat/completions response
        def _post(url, json, headers, timeout):  # noqa: D401, ARG001
            assert url.endswith("/v1/chat/completions")
            assert json["messages"][0]["role"] == "system"
            assert json["messages"][1]["role"] == "user"
            payload = {
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}},
                ]
            }
            return _FakeResponse(payload)

        obj.post = _post
        def _mount(*_args, **_kwargs):  # noqa: D401
            return None

        obj.mount = _mount
        return obj

    monkeypatch.setattr("elspeth.plugins.nodes.transforms.llm.openai_http.requests.Session", _fake_session)

    # Use a localhost endpoint (allowed by endpoint validator) but do not bind sockets
    # Provide API key via environment and extra params to exercise headers and payload branches
    monkeypatch.setenv("HTTP_OPENAI_KEY", "secret")
    client = HttpOpenAIClient(
        api_base="http://127.0.0.1:12345",
        model="m",
        api_key_env="HTTP_OPENAI_KEY",
        temperature=0.3,
        max_tokens=64,
    )
    out = client.generate(system_prompt="s", user_prompt="u", metadata={"k": "v"})

    assert out["content"] == "ok"
    assert out["metadata"] == {"k": "v"}
    assert "choices" in out["raw"]
