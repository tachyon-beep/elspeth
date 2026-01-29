# src/elspeth/testing/chaosllm/__init__.py
"""ChaosLLM: Fake LLM server for load testing and fault injection.

ChaosLLM provides:
- OpenAI and Azure OpenAI compatible endpoints
- Configurable error injection (rate limits, capacity errors, timeouts, malformed responses)
- Response generation (random, template, preset bank)
- Burst pattern simulation for AIMD throttle testing
- SQLite metrics storage for analysis

Usage:
    # CLI
    elspeth chaosllm --preset=stress-aimd --port=8000

    # Pytest fixture
    def test_pipeline(chaosllm_server):
        transform = AzureMultiQueryLLMTransform({
            "endpoint": chaosllm_server.url,
            ...
        })
"""

from elspeth.testing.chaosllm.config import (
    ChaosLLMConfig,
    ErrorInjectionConfig,
    LatencyConfig,
    ResponseConfig,
    ServerConfig,
    list_presets,
    load_config,
    load_preset,
)

__all__ = [
    "ChaosLLMConfig",
    "ErrorInjectionConfig",
    "LatencyConfig",
    "ResponseConfig",
    "ServerConfig",
    "list_presets",
    "load_config",
    "load_preset",
]
