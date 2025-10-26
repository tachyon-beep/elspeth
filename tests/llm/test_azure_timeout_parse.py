from __future__ import annotations

from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.nodes.transforms.llm.azure_openai import AzureOpenAIClient
from tests.test_llm_azure import make_dummy_client


def test_azure_openai_timeout_parse_fallback():
    client = make_dummy_client()
    llm = AzureOpenAIClient(  # ADR-002-B: security hard-coded in plugin
        config={
            "api_key": "key",
            "api_version": "2024-05-01",
            "azure_endpoint": "https://endpoint.openai.azure.com",
            "timeout": "not-a-number",
        },
        client=client,
        deployment="stub-deployment",
    )

    # Parsing should fail and default to 30.0
    assert llm.request_timeout == 30.0
