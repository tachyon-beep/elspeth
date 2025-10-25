import os

import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.nodes.transforms.llm.azure_openai import AzureOpenAIClient


def make_dummy_client():
    class DummyMessage:
        def __init__(self, content):
            self.content = content

    class DummyChoice:
        def __init__(self, content):
            self.message = DummyMessage(content)

    class DummyResponse:
        def __init__(self, payload):
            self.choices = [DummyChoice(payload)]

    class DummyCompletions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return DummyResponse("generated")

    class DummyChat:
        def __init__(self):
            self.completions = DummyCompletions()

    class DummyClient:
        def __init__(self):
            self.chat = DummyChat()

    return DummyClient()


def test_generate_uses_client_calls(monkeypatch):
    dummy_client = make_dummy_client()

    llm = AzureOpenAIClient(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        deployment="gpt",
        config={
            "api_key": "key",
            "api_version": "2024-05-01",
            "azure_endpoint": "https://endpoint.openai.azure.com",
            "temperature": 0.5,
            "max_tokens": 256,
        },
        client=dummy_client,
    )

    result = llm.generate(system_prompt="system", user_prompt="user")

    call = dummy_client.chat.completions.calls[0]
    assert call["model"] == "gpt"
    assert call["messages"][0]["content"] == "system"
    assert call["temperature"] == 0.5
    assert call["max_tokens"] == 256
    assert result["content"] == "generated"


def test_missing_config_uses_env(monkeypatch):
    monkeypatch.setenv("OPENAI_TEST_KEY", "secret")
    monkeypatch.setenv("ELSPETH_AZURE_OPENAI_DEPLOYMENT", "env-model")

    llm = AzureOpenAIClient(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        config={
            "api_key_env": "OPENAI_TEST_KEY",
            "api_version": "2024-05-01",
            "azure_endpoint": "https://endpoint.openai.azure.com",
        },
        client=make_dummy_client(),
    )

    assert llm.generate(system_prompt="sys", user_prompt="user")["content"] == "generated"


def test_missing_required_raises():
    os.environ.pop("ELSPETH_AZURE_OPENAI_DEPLOYMENT", None)
    with pytest.raises(ValueError):
        AzureOpenAIClient(
            security_level=SecurityLevel.UNOFFICIAL,
            allow_downgrade=True,
            deployment="gpt",
            config={
                "api_key": "key",
                "azure_endpoint": "https://endpoint.openai.azure.com",
            },
        )
