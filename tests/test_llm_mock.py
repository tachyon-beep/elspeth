from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.nodes.transforms.llm.mock import MockLLMClient


def test_mock_llm_generates_deterministic_scores():
    client = MockLLMClient(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        seed=123
    )
    response1 = client.generate(system_prompt="sys", user_prompt="user", metadata={"criteria": "c1"})
    response2 = client.generate(system_prompt="sys", user_prompt="user", metadata={"criteria": "c1"})

    assert response1["metrics"]["score"] == response2["metrics"]["score"]
    assert "mock" in response1["content"]
    assert 0.4 <= response1["metrics"]["score"] <= 0.9
