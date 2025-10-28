from __future__ import annotations

from types import SimpleNamespace

from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.nodes.transforms.llm.azure_openai import AzureOpenAIClient


class _FakeCreate:
    def __init__(self, response: object) -> None:
        self._response = response

    def create(self, *args, **kwargs):  # noqa: ANN001 - test shim
        return self._response


class _FakeChat:
    def __init__(self, response: object) -> None:
        self.completions = _FakeCreate(response)


class _FakeClient:
    def __init__(self, response: object) -> None:
        self.chat = _FakeChat(response)


def test_azure_openai_client_timeout_parsing_invalid():
    # Invalid timeout is coerced to default (30.0)
    client = AzureOpenAIClient(  # ADR-002-B: security hard-coded in plugin
        deployment="dep",
        config={"timeout": "not-a-float", "api_key": "k", "api_version": "v", "azure_endpoint": "e"},
        client=_FakeClient(SimpleNamespace(choices=[])),
    )
    assert client.request_timeout == 30.0


def test_azure_openai_client_generate_handles_missing_content():
    # Missing nested attributes should not raise and should return None content
    fake_response = SimpleNamespace(choices=[])
    client = AzureOpenAIClient(  # ADR-002-B: security hard-coded in plugin
        deployment="dep",
        config={"timeout": 5, "api_key": "k", "api_version": "v", "azure_endpoint": "e"},
        client=_FakeClient(fake_response),
    )

    out = client.generate(system_prompt="sys", user_prompt="hi")
    assert "content" in out and out["content"] is None
