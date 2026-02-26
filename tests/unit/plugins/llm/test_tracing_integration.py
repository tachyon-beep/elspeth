# tests/plugins/llm/test_tracing_integration.py
"""Integration tests for Tier 2 tracing with mocked endpoints.

These tests verify end-to-end tracing behavior by:
1. Creating transforms with tracing configuration
2. Mocking external SDKs (Langfuse)
3. Verifying traces capture complete LLM call information

Note: Tests updated for unified LLMTransform and Langfuse SDK v3
(context manager pattern).
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.llm.langfuse import ActiveLangfuseTracer, NoOpLangfuseTracer
from elspeth.plugins.llm.transform import LLMTransform


def _make_azure_config(**overrides: Any) -> dict[str, Any]:
    """Create base config for Azure LLM transform."""
    config: dict[str, Any] = {
        "provider": "azure",
        "deployment_name": "gpt-4",
        "endpoint": "https://test.openai.azure.com",
        "api_key": "test-key",
        "template": "Hello {{ row.name }}",
        "schema": {"mode": "observed"},
        "required_input_fields": [],
    }
    config.update(overrides)
    return config


def _make_openrouter_config(**overrides: Any) -> dict[str, Any]:
    """Create base config for OpenRouter LLM transform."""
    config: dict[str, Any] = {
        "provider": "openrouter",
        "model": "anthropic/claude-3-opus",
        "api_key": "test-key",
        "template": "Hello {{ row.name }}",
        "schema": {"mode": "observed"},
        "required_input_fields": [],
    }
    config.update(overrides)
    return config


def _make_mock_ctx(run_id: str = "test-run") -> MagicMock:
    """Create a mock PluginContext."""
    ctx = MagicMock()
    ctx.landscape = MagicMock()
    ctx.run_id = run_id
    ctx.telemetry_emit = lambda x: None
    ctx.rate_limit_registry = None
    return ctx


class TestLangfuseIntegration:
    """Integration tests for Langfuse tracing (v3 API)."""

    @pytest.fixture
    def mock_langfuse_client(self) -> MagicMock:
        """Create a mock Langfuse client that captures v3 observations.

        v3 API uses start_as_current_observation() context manager for both
        spans and generations, with update() to record outputs.
        """
        captured_observations: list[dict[str, Any]] = []

        mock_client = MagicMock()

        @contextmanager
        def mock_start_observation(**kwargs: Any):
            """Mock start_as_current_observation context manager."""
            obs = MagicMock()
            obs_record: dict[str, Any] = {"kwargs": kwargs, "updates": []}
            captured_observations.append(obs_record)

            def capture_update(**update_kwargs: Any) -> None:
                obs_record["updates"].append(update_kwargs)

            obs.update = capture_update
            yield obs

        mock_client.start_as_current_observation = mock_start_observation
        mock_client.captured_observations = captured_observations
        mock_client.flush = MagicMock()

        return mock_client

    def test_langfuse_captures_llm_call_end_to_end(self, mock_langfuse_client: MagicMock) -> None:
        """Langfuse captures complete LLM call with prompt, response, and usage."""
        # Setup transform with Langfuse tracing
        config = _make_azure_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = LLMTransform(config)

        # Inject mock Langfuse client via ActiveLangfuseTracer
        transform._tracer = ActiveLangfuseTracer(
            transform_name=transform.name,
            client=mock_langfuse_client,
        )

        # Record a trace via tracer
        transform._tracer.record_success(
            token_id="token-123",
            query_name=transform.name,
            prompt="Hello world",
            response_content="Hi there!",
            model="gpt-4",
            usage=TokenUsage.known(10, 5),
            latency_ms=150.0,
            extra_metadata={"deployment": "gpt-4"},
        )

        # Verify observations were created (span + generation)
        assert len(mock_langfuse_client.captured_observations) == 2

        # First observation is the outer span
        span_kwargs = mock_langfuse_client.captured_observations[0]["kwargs"]
        assert span_kwargs["as_type"] == "span"
        assert span_kwargs["name"] == "elspeth.llm"
        assert span_kwargs["metadata"]["token_id"] == "token-123"
        assert span_kwargs["metadata"]["plugin"] == "llm"
        assert span_kwargs["metadata"]["deployment"] == "gpt-4"

        # Second observation is the generation
        gen_kwargs = mock_langfuse_client.captured_observations[1]["kwargs"]
        assert gen_kwargs["as_type"] == "generation"
        assert gen_kwargs["name"] == "llm_call"
        assert gen_kwargs["model"] == "gpt-4"
        assert gen_kwargs["input"] == [{"role": "user", "content": "Hello world"}]

        # Verify update() was called with output and usage_details
        gen_updates = mock_langfuse_client.captured_observations[1]["updates"]
        assert len(gen_updates) == 1
        assert gen_updates[0]["output"] == "Hi there!"
        assert gen_updates[0]["usage_details"]["input"] == 10
        assert gen_updates[0]["usage_details"]["output"] == 5
        assert gen_updates[0]["metadata"]["latency_ms"] == 150.0

    def test_langfuse_captures_openrouter_call(self, mock_langfuse_client: MagicMock) -> None:
        """Langfuse captures OpenRouter HTTP call via unified LLMTransform."""
        # Setup transform with Langfuse tracing
        config = _make_openrouter_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = LLMTransform(config)

        # Inject mock Langfuse client via ActiveLangfuseTracer
        transform._tracer = ActiveLangfuseTracer(
            transform_name=transform.name,
            client=mock_langfuse_client,
        )

        # Record a trace via tracer
        transform._tracer.record_success(
            token_id="token-456",
            query_name=transform.name,
            prompt="Analyze this",
            response_content="Analysis complete",
            model="anthropic/claude-3-opus",
            usage=TokenUsage.known(20, 10),
            latency_ms=250.0,
        )

        # Verify observations were created
        assert len(mock_langfuse_client.captured_observations) == 2

        # Span has unified LLMTransform metadata (same name for all providers)
        span_kwargs = mock_langfuse_client.captured_observations[0]["kwargs"]
        assert span_kwargs["name"] == "elspeth.llm"
        assert span_kwargs["metadata"]["plugin"] == "llm"

        # Generation captures OpenRouter response
        gen_kwargs = mock_langfuse_client.captured_observations[1]["kwargs"]
        assert gen_kwargs["model"] == "anthropic/claude-3-opus"
        assert gen_kwargs["input"] == [{"role": "user", "content": "Analyze this"}]

        gen_updates = mock_langfuse_client.captured_observations[1]["updates"]
        assert gen_updates[0]["output"] == "Analysis complete"

    def test_langfuse_tracer_created_at_init(self) -> None:
        """ActiveLangfuseTracer is created at __init__ time when Langfuse config is valid."""
        config = _make_azure_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
                "host": "https://custom.langfuse.com",
            }
        )
        # Langfuse is installed in test env, so factory returns ActiveLangfuseTracer
        transform = LLMTransform(config)

        assert isinstance(transform._tracer, ActiveLangfuseTracer)
        assert transform._tracer.transform_name == "llm"

    def test_langfuse_flush_called_on_close(self) -> None:
        """Langfuse client is flushed when transform closes."""
        config = _make_azure_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = LLMTransform(config)

        # Setup mock tracer
        mock_langfuse = MagicMock()
        transform._tracer = ActiveLangfuseTracer(
            transform_name=transform.name,
            client=mock_langfuse,
        )

        # Close the transform
        transform.close()

        # Verify flush was called
        mock_langfuse.flush.assert_called_once()


class TestGracefulDegradation:
    """Tests for graceful degradation when SDKs are not installed."""

    def test_langfuse_raises_when_not_installed(self) -> None:
        """RuntimeError raised when Langfuse SDK not installed but configured."""
        import builtins

        # Store the original import function
        original_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "langfuse":
                raise ImportError("No module named 'langfuse'")
            return original_import(name, *args, **kwargs)

        # Missing Langfuse package with explicit config is a startup error —
        # the user has a reasonable expectation that configured tracing is active.
        with (
            patch.dict(sys.modules, {"langfuse": None}),
            patch.object(builtins, "__import__", side_effect=mock_import),
            pytest.raises(RuntimeError, match=r"langfuse.*not installed"),
        ):
            config = _make_azure_config(
                tracing={
                    "provider": "langfuse",
                    "public_key": "pk-test",
                    "secret_key": "sk-test",
                }
            )
            LLMTransform(config)

    def test_tracing_raises_when_config_incomplete_and_not_installed(self) -> None:
        """RuntimeError when Langfuse config is incomplete AND package missing.

        Even with incomplete config (missing keys), the user explicitly asked
        for langfuse tracing. Missing package is a startup error.
        """
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "langfuse":
                raise ImportError("No module named 'langfuse'")
            return original_import(name, *args, **kwargs)

        with (
            patch.dict(sys.modules, {"langfuse": None}),
            patch.object(builtins, "__import__", side_effect=mock_import),
            pytest.raises(RuntimeError, match=r"langfuse.*not installed"),
        ):
            config = _make_azure_config(
                tracing={
                    "provider": "langfuse",
                    # Missing public_key and secret_key
                }
            )
            LLMTransform(config)


class TestTracingDisabled:
    """Tests for behavior when tracing is disabled or not configured."""

    def test_no_tracing_when_config_is_none(self) -> None:
        """NoOpLangfuseTracer when tracing config is None."""
        config = _make_azure_config()  # No tracing config
        transform = LLMTransform(config)

        assert isinstance(transform._tracer, NoOpLangfuseTracer)

    def test_no_tracing_when_provider_is_none(self) -> None:
        """NoOpLangfuseTracer when provider is 'none'."""
        config = _make_azure_config(tracing={"provider": "none"})
        transform = LLMTransform(config)

        # parse_tracing_config returns TracingConfig(provider="none"), which is
        # not LangfuseTracingConfig, so create_langfuse_tracer returns NoOp.
        assert isinstance(transform._tracer, NoOpLangfuseTracer)

    def test_record_trace_does_nothing_when_tracing_inactive(self) -> None:
        """NoOpLangfuseTracer.record_success is a no-op when tracing is not configured."""
        config = _make_azure_config()
        transform = LLMTransform(config)

        assert isinstance(transform._tracer, NoOpLangfuseTracer)

        # This should not raise any errors (no-op tracer)
        transform._tracer.record_success(
            token_id="test-token",
            query_name=transform.name,
            prompt="test",
            response_content="response",
            model="gpt-4",
            usage=None,
            latency_ms=None,
        )
        # If we get here without error, test passes

    def test_azure_ai_tracing_results_in_noop(self) -> None:
        """Azure AI tracing config results in NoOpLangfuseTracer.

        LLMTransform does not support Azure AI tracing directly.
        AzureAITracingConfig is parsed but create_langfuse_tracer returns
        NoOpLangfuseTracer for non-Langfuse configs.
        """
        config = _make_azure_config(
            tracing={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )
        transform = LLMTransform(config)

        assert isinstance(transform._tracer, NoOpLangfuseTracer)


class TestTracingMetadata:
    """Tests for tracing metadata completeness (v3 API)."""

    def test_trace_includes_token_id_for_correlation(self) -> None:
        """Trace includes token_id for correlation with Landscape audit trail."""
        config = _make_azure_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = LLMTransform(config)

        captured_observations: list[dict[str, Any]] = []
        mock_langfuse = MagicMock()

        @contextmanager
        def mock_start_observation(**kwargs: Any):
            obs = MagicMock()
            obs.update = MagicMock()
            captured_observations.append(kwargs)
            yield obs

        mock_langfuse.start_as_current_observation = mock_start_observation

        transform._tracer = ActiveLangfuseTracer(
            transform_name=transform.name,
            client=mock_langfuse,
        )

        transform._tracer.record_success(
            token_id="token-abc-123",
            query_name=transform.name,
            prompt="test",
            response_content="response",
            model="gpt-4",
            usage=None,
            latency_ms=None,
        )

        # First observation is the span, which has token_id in metadata
        assert len(captured_observations) >= 1
        assert captured_observations[0]["metadata"]["token_id"] == "token-abc-123"

    def test_generation_includes_usage_metrics(self) -> None:
        """Generation includes token usage for cost tracking (v3: usage_details)."""
        config = _make_azure_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = LLMTransform(config)

        captured_updates: list[dict[str, Any]] = []

        @contextmanager
        def mock_start_observation(**kwargs: Any):
            obs = MagicMock()
            obs.update = lambda **uk: captured_updates.append(uk)
            yield obs

        mock_langfuse = MagicMock()
        mock_langfuse.start_as_current_observation = mock_start_observation

        transform._tracer = ActiveLangfuseTracer(
            transform_name=transform.name,
            client=mock_langfuse,
        )

        transform._tracer.record_success(
            token_id="test-token",
            query_name=transform.name,
            prompt="test prompt",
            response_content="test response",
            model="gpt-4",
            usage=TokenUsage.known(100, 50),
            latency_ms=500.0,
        )

        # Find the update call with usage_details (from the generation observation)
        usage_update = next((u for u in captured_updates if "usage_details" in u), None)
        assert usage_update is not None
        assert usage_update["usage_details"]["input"] == 100
        assert usage_update["usage_details"]["output"] == 50

    def test_generation_includes_latency(self) -> None:
        """Generation includes latency for performance monitoring."""
        config = _make_openrouter_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = LLMTransform(config)

        captured_updates: list[dict[str, Any]] = []

        @contextmanager
        def mock_start_observation(**kwargs: Any):
            obs = MagicMock()
            obs.update = lambda **uk: captured_updates.append(uk)
            yield obs

        mock_langfuse = MagicMock()
        mock_langfuse.start_as_current_observation = mock_start_observation

        transform._tracer = ActiveLangfuseTracer(
            transform_name=transform.name,
            client=mock_langfuse,
        )

        transform._tracer.record_success(
            token_id="test-token",
            query_name=transform.name,
            prompt="test",
            response_content="response",
            model="anthropic/claude-3-opus",
            usage=None,
            latency_ms=1234.5,
        )

        # Find the update call with metadata (from the generation observation)
        metadata_update = next((u for u in captured_updates if "metadata" in u), None)
        assert metadata_update is not None
        assert metadata_update["metadata"]["latency_ms"] == 1234.5


class TestTracingProviderValidation:
    """Tests for explicit tracing provider validation behavior."""

    def test_unknown_provider_raises_at_config_time(self) -> None:
        """Unknown tracing providers raise ValueError during config parsing (fail-fast).

        parse_tracing_config raises ValueError for unknown providers, which
        propagates through LLMTransform.__init__.
        """
        config = _make_openrouter_config(
            tracing={
                "provider": "langfusee",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        with pytest.raises(ValueError, match="Unknown tracing provider"):
            LLMTransform(config)
