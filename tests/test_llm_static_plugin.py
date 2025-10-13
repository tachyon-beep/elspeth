from __future__ import annotations

from elspeth.core.registry import registry
from elspeth.plugins.llms.static import StaticLLMClient


def test_static_llm_client_returns_constant_metrics() -> None:
    client = StaticLLMClient(content="Hello", score=0.75, metrics={"flag": True})
    response = client.generate(system_prompt="sys", user_prompt="user", metadata={"row": 1})

    assert response["content"] == "Hello"
    assert response["metrics"]["score"] == 0.75
    assert response["metrics"]["flag"] is True
    assert response["raw"]["user_prompt"] == "user"


def test_static_llm_registry_integration() -> None:
    instance = registry.create_llm(
        "static_test",
        {
            "content": "Registry",
            "score": 0.9,
            "metrics": {"extra": "value"},
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
        },
    )

    response = instance.generate(system_prompt="sys", user_prompt="user", metadata=None)
    assert response["content"] == "Registry"
    assert response["metrics"]["score"] == 0.9
    assert response["metrics"]["extra"] == "value"
