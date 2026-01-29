# Testing Tools

This section documents testing utilities that ship with ELSPETH for load testing, stress testing, and fault injection.

## ChaosLLM

**ChaosLLM** is a fake LLM server for testing pipelines at scale without hitting real LLM APIs.

- [ChaosLLM User Guide](chaosllm.md) - Complete documentation
- [ChaosLLM MCP Server](chaosllm-mcp.md) - Analysis tools for Claude Code

### Quick Start

```bash
# Start server with stress testing preset
chaosllm serve --preset=stress_aimd

# In another terminal, run your pipeline against it
elspeth run --settings pipeline.yaml --execute
```

### Pytest Fixture

```python
def test_pipeline_handles_errors(chaosllm_server):
    """ChaosLLM server auto-starts for the test."""
    # Configure your transform to use chaosllm_server.url
    transform = AzureMultiQueryLLMTransform({
        "endpoint": chaosllm_server.url,
        "api_key": "fake-key",
        ...
    })
```

See the [full guide](chaosllm.md) for presets, configuration, and analysis tools.
