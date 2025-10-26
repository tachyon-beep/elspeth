from __future__ import annotations

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.registries.llm import llm_registry
from elspeth.plugins.nodes.transforms.llm.static import StaticLLMClient


def test_static_llm_client_returns_constant_metrics() -> None:
    client = StaticLLMClient(
        content="Hello",
        score=0.75,
        metrics={"flag": True}
    )
    response = client.generate(system_prompt="sys", user_prompt="user", metadata={"row": 1})

    assert response["content"] == "Hello"
    assert response["metrics"]["score"] == 0.75
    assert response["metrics"]["flag"] is True
    assert response["raw"]["user_prompt"] == "user"


def test_static_llm_registry_integration() -> None:
    # ADR-002-B: security_level via parent_context, not in options
    parent = PluginContext(
        plugin_name="test",
        plugin_kind="test",
        security_level="OFFICIAL",
        determinism_level="guaranteed",
        provenance=("test:registry_integration",),
    )

    instance = llm_registry.create(
        "static_test",
        {
            "content": "Registry",
            "score": 0.9,
            "metrics": {"extra": "value"},
            "determinism_level": "guaranteed",  # determinism_level is user-configurable
        },
        parent_context=parent,
    )

    response = instance.generate(system_prompt="sys", user_prompt="user", metadata=None)
    assert response["content"] == "Registry"
    assert response["metrics"]["score"] == 0.9
    assert response["metrics"]["extra"] == "value"
