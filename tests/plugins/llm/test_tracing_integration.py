# tests/plugins/llm/test_tracing_integration.py
"""Integration tests for Tier 2 tracing with mocked endpoints.

These tests verify end-to-end tracing behavior by:
1. Creating transforms with tracing configuration
2. Mocking external SDKs (Langfuse, Azure Monitor)
3. Verifying traces capture complete LLM call information
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from elspeth.plugins.llm.azure import AzureLLMTransform
from elspeth.plugins.llm.openrouter import OpenRouterLLMTransform
from elspeth.plugins.llm.tracing import AzureAITracingConfig, LangfuseTracingConfig


def _make_azure_config(**overrides: Any) -> dict[str, Any]:
    """Create base config for Azure LLM transform."""
    config = {
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
    config = {
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
    """Integration tests for Langfuse tracing."""

    @pytest.fixture
    def mock_langfuse_client(self) -> MagicMock:
        """Create a mock Langfuse client that captures traces."""
        captured_traces: list[dict[str, Any]] = []
        captured_generations: list[dict[str, Any]] = []

        mock_client = MagicMock()

        def capture_trace(**kwargs: Any) -> MagicMock:
            trace = MagicMock()
            captured_traces.append(kwargs)

            def capture_generation(**gen_kwargs: Any) -> MagicMock:
                captured_generations.append(gen_kwargs)
                return MagicMock()

            trace.generation = capture_generation
            return trace

        mock_client.trace = capture_trace
        mock_client.captured_traces = captured_traces
        mock_client.captured_generations = captured_generations

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
        transform = AzureLLMTransform(config)

        # Inject mock Langfuse client and activate tracing
        transform._langfuse_client = mock_langfuse_client
        transform._tracing_active = True

        # Create a trace and record a generation
        with transform._create_langfuse_trace("token-123", {"name": "world"}) as trace:
            assert trace is not None
            # Simulate recording after LLM call
            transform._record_langfuse_generation(
                trace=trace,
                prompt="Hello world",
                response_content="Hi there!",
                model="gpt-4",
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                latency_ms=150.0,
            )

        # Verify trace was created with correct metadata
        assert len(mock_langfuse_client.captured_traces) == 1
        trace_kwargs = mock_langfuse_client.captured_traces[0]
        assert trace_kwargs["name"] == "elspeth.azure_llm"
        assert trace_kwargs["metadata"]["token_id"] == "token-123"
        assert trace_kwargs["metadata"]["plugin"] == "azure_llm"
        assert trace_kwargs["metadata"]["deployment"] == "gpt-4"

        # Verify generation was recorded with complete data
        assert len(mock_langfuse_client.captured_generations) == 1
        gen_kwargs = mock_langfuse_client.captured_generations[0]
        assert gen_kwargs["name"] == "llm_call"
        assert gen_kwargs["model"] == "gpt-4"
        assert gen_kwargs["input"] == "Hello world"
        assert gen_kwargs["output"] == "Hi there!"
        assert gen_kwargs["usage"]["input"] == 10
        assert gen_kwargs["usage"]["output"] == 5
        assert gen_kwargs["usage"]["total"] == 15
        assert gen_kwargs["metadata"]["latency_ms"] == 150.0

    def test_langfuse_captures_openrouter_call(self, mock_langfuse_client: MagicMock) -> None:
        """Langfuse captures OpenRouter HTTP call."""
        # Setup transform with Langfuse tracing
        config = _make_openrouter_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = OpenRouterLLMTransform(config)

        # Inject mock Langfuse client and activate tracing
        transform._langfuse_client = mock_langfuse_client
        transform._tracing_active = True

        # Create a trace and record a generation
        with transform._create_langfuse_trace("token-456", {"name": "test"}) as trace:
            assert trace is not None
            # Simulate recording after OpenRouter call
            transform._record_langfuse_generation(
                trace=trace,
                prompt="Analyze this",
                response_content="Analysis complete",
                model="anthropic/claude-3-opus",
                usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                latency_ms=250.0,
            )

        # Verify trace was created with OpenRouter-specific metadata
        assert len(mock_langfuse_client.captured_traces) == 1
        trace_kwargs = mock_langfuse_client.captured_traces[0]
        assert trace_kwargs["name"] == "elspeth.openrouter_llm"
        assert trace_kwargs["metadata"]["plugin"] == "openrouter_llm"
        assert trace_kwargs["metadata"]["model"] == "anthropic/claude-3-opus"

        # Verify generation captures OpenRouter response
        assert len(mock_langfuse_client.captured_generations) == 1
        gen_kwargs = mock_langfuse_client.captured_generations[0]
        assert gen_kwargs["model"] == "anthropic/claude-3-opus"
        assert gen_kwargs["input"] == "Analyze this"
        assert gen_kwargs["output"] == "Analysis complete"

    def test_langfuse_client_created_on_start(self) -> None:
        """Langfuse client is created during on_start when config is valid."""
        config = _make_azure_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
                "host": "https://custom.langfuse.com",
            }
        )
        transform = AzureLLMTransform(config)

        # Mock langfuse module
        mock_langfuse_instance = MagicMock()
        mock_langfuse_class = MagicMock(return_value=mock_langfuse_instance)

        mock_module = MagicMock()
        mock_module.Langfuse = mock_langfuse_class

        with patch.dict(sys.modules, {"langfuse": mock_module}):
            ctx = _make_mock_ctx()
            transform.on_start(ctx)

            # Verify client was created with correct parameters
            mock_langfuse_class.assert_called_once_with(
                public_key="pk-test",
                secret_key="sk-test",
                host="https://custom.langfuse.com",
            )
            assert transform._tracing_active is True
            assert transform._langfuse_client is mock_langfuse_instance

    def test_langfuse_flush_called_on_close(self) -> None:
        """Langfuse client is flushed when transform closes."""
        config = _make_azure_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = AzureLLMTransform(config)

        # Setup mock client
        mock_langfuse = MagicMock()
        transform._langfuse_client = mock_langfuse
        transform._tracing_active = True

        # Close the transform
        transform.close()

        # Verify flush was called
        mock_langfuse.flush.assert_called_once()


class TestAzureAIAutoInstrumentation:
    """Tests for Azure AI auto-instrumentation verification."""

    def test_azure_ai_configures_opentelemetry(self) -> None:
        """Azure AI calls configure_azure_monitor with correct parameters."""
        config = _make_azure_config(
            tracing={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
                "enable_content_recording": True,
                "enable_live_metrics": True,
            }
        )
        transform = AzureLLMTransform(config)

        # Verify parsed config
        assert transform._tracing_config is not None
        assert isinstance(transform._tracing_config, AzureAITracingConfig)
        assert transform._tracing_config.connection_string == "InstrumentationKey=xxx"
        assert transform._tracing_config.enable_content_recording is True
        assert transform._tracing_config.enable_live_metrics is True

        # Mock configure_azure_monitor and OTEL provider check
        with patch("elspeth.plugins.llm.azure._configure_azure_monitor") as mock_configure:
            mock_configure.return_value = True

            with patch("opentelemetry.trace.get_tracer_provider") as mock_get_provider:
                mock_provider = MagicMock()
                mock_provider.__class__.__name__ = "ProxyTracerProvider"
                mock_get_provider.return_value = mock_provider

                ctx = _make_mock_ctx()
                transform.on_start(ctx)

                # Verify configure was called with the tracing config
                mock_configure.assert_called_once()
                call_args = mock_configure.call_args[0][0]
                assert isinstance(call_args, AzureAITracingConfig)
                assert call_args.connection_string == "InstrumentationKey=xxx"
                assert call_args.enable_live_metrics is True

                assert transform._tracing_active is True

    def test_azure_ai_warns_on_existing_otel_provider(self) -> None:
        """Azure AI logs warning when OTEL already configured (Tier 1 conflict)."""
        config = _make_azure_config(
            tracing={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )
        transform = AzureLLMTransform(config)

        with patch("elspeth.plugins.llm.azure._configure_azure_monitor") as mock_configure:
            mock_configure.return_value = True

            # Simulate existing OTEL provider (not ProxyTracerProvider)
            with patch("opentelemetry.trace.get_tracer_provider") as mock_get_provider:
                mock_provider = MagicMock()
                mock_provider.__class__.__name__ = "TracerProvider"  # Not Proxy
                mock_get_provider.return_value = mock_provider

                with patch("structlog.get_logger") as mock_get_logger:
                    mock_logger = MagicMock()
                    mock_get_logger.return_value = mock_logger

                    ctx = _make_mock_ctx()
                    transform.on_start(ctx)

                    # Verify warning was logged about potential conflict
                    mock_logger.warning.assert_called()
                    call_args = mock_logger.warning.call_args
                    assert "Existing OpenTelemetry tracer detected" in call_args[0][0]

    def test_azure_ai_not_supported_for_openrouter(self) -> None:
        """Azure AI tracing is rejected for OpenRouter with appropriate warning."""
        config = _make_openrouter_config(
            tracing={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )
        transform = OpenRouterLLMTransform(config)

        with patch("structlog.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ctx = _make_mock_ctx()
            transform.on_start(ctx)

            # Verify warning about unsupported provider
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "Azure AI tracing not supported" in call_args[0][0]
            assert transform._tracing_active is False


class TestGracefulDegradation:
    """Tests for graceful degradation when SDKs are not installed."""

    def test_langfuse_warning_when_not_installed(self) -> None:
        """Warning logged when Langfuse SDK not installed."""
        import builtins

        config = _make_azure_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = AzureLLMTransform(config)

        # Store the original import function
        original_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "langfuse":
                raise ImportError("No module named 'langfuse'")
            return original_import(name, *args, **kwargs)

        # Ensure langfuse is not already imported
        with (
            patch.dict(sys.modules, {"langfuse": None}),
            patch.object(builtins, "__import__", side_effect=mock_import),
            patch("structlog.get_logger") as mock_get_logger,
        ):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ctx = _make_mock_ctx()
            transform.on_start(ctx)

            # Verify warning was logged
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "package not installed" in call_args[0][0]
            assert transform._tracing_active is False

    def test_azure_ai_warning_when_not_installed(self) -> None:
        """Warning logged when Azure Monitor SDK not installed."""
        config = _make_azure_config(
            tracing={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )
        transform = AzureLLMTransform(config)

        # Mock OTEL check to pass
        mock_provider = MagicMock()
        mock_provider.__class__.__name__ = "ProxyTracerProvider"

        with (
            patch("opentelemetry.trace.get_tracer_provider", return_value=mock_provider),
            patch(
                "elspeth.plugins.llm.azure._configure_azure_monitor",
                side_effect=ImportError("No module named 'azure.monitor.opentelemetry'"),
            ),
            patch("structlog.get_logger") as mock_get_logger,
        ):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ctx = _make_mock_ctx()
            transform.on_start(ctx)

            # Verify warning was logged about missing package
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "package not installed" in call_args[0][0]
            assert transform._tracing_active is False

    def test_tracing_inactive_when_config_validation_fails(self) -> None:
        """Tracing not activated when configuration is incomplete."""
        config = _make_azure_config(
            tracing={
                "provider": "langfuse",
                # Missing public_key and secret_key
            }
        )
        transform = AzureLLMTransform(config)

        # Verify config was parsed as LangfuseTracingConfig
        assert transform._tracing_config is not None
        assert isinstance(transform._tracing_config, LangfuseTracingConfig)

        with patch("structlog.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ctx = _make_mock_ctx()
            transform.on_start(ctx)

            # Verify warnings about missing keys
            assert mock_logger.warning.call_count >= 2  # At least 2 errors (public_key, secret_key)
            assert transform._tracing_active is False


class TestTracingDisabled:
    """Tests for behavior when tracing is disabled or not configured."""

    def test_no_tracing_when_config_is_none(self) -> None:
        """No tracing setup when tracing config is None."""
        config = _make_azure_config()  # No tracing config
        transform = AzureLLMTransform(config)

        assert transform._tracing_config is None
        assert transform._tracing_active is False

        # Verify trace context returns None
        with transform._create_langfuse_trace("token-123", {}) as trace:
            assert trace is None

    def test_no_tracing_when_provider_is_none(self) -> None:
        """No tracing setup when provider is 'none'."""
        config = _make_azure_config(tracing={"provider": "none"})
        transform = AzureLLMTransform(config)

        assert transform._tracing_config is not None
        assert transform._tracing_config.provider == "none"

        ctx = _make_mock_ctx()
        transform.on_start(ctx)

        assert transform._tracing_active is False

    def test_generation_not_recorded_when_trace_is_none(self) -> None:
        """No generation recorded when trace is None."""
        config = _make_azure_config()
        transform = AzureLLMTransform(config)

        # This should not raise any errors
        transform._record_langfuse_generation(
            trace=None,
            prompt="test",
            response_content="response",
            model="gpt-4",
        )
        # If we get here without error, test passes


class TestTracingMetadata:
    """Tests for tracing metadata completeness."""

    def test_trace_includes_token_id_for_correlation(self) -> None:
        """Trace includes token_id for correlation with Landscape audit trail."""
        config = _make_azure_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = AzureLLMTransform(config)

        captured_traces: list[dict[str, Any]] = []
        mock_langfuse = MagicMock()

        def capture_trace(**kwargs: Any) -> MagicMock:
            captured_traces.append(kwargs)
            return MagicMock()

        mock_langfuse.trace = capture_trace

        transform._langfuse_client = mock_langfuse
        transform._tracing_active = True

        with transform._create_langfuse_trace("token-abc-123", {"field": "value"}):
            pass

        assert len(captured_traces) == 1
        assert captured_traces[0]["metadata"]["token_id"] == "token-abc-123"

    def test_generation_includes_usage_metrics(self) -> None:
        """Generation includes token usage for cost tracking."""
        config = _make_azure_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = AzureLLMTransform(config)

        captured_generations: list[dict[str, Any]] = []
        mock_trace = MagicMock()
        mock_trace.generation = lambda **kwargs: captured_generations.append(kwargs)

        transform._langfuse_client = MagicMock()
        transform._tracing_active = True

        transform._record_langfuse_generation(
            trace=mock_trace,
            prompt="test prompt",
            response_content="test response",
            model="gpt-4",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            latency_ms=500.0,
        )

        assert len(captured_generations) == 1
        usage = captured_generations[0]["usage"]
        assert usage["input"] == 100
        assert usage["output"] == 50
        assert usage["total"] == 150

    def test_generation_includes_latency(self) -> None:
        """Generation includes latency for performance monitoring."""
        config = _make_openrouter_config(
            tracing={
                "provider": "langfuse",
                "public_key": "pk-test",
                "secret_key": "sk-test",
            }
        )
        transform = OpenRouterLLMTransform(config)

        captured_generations: list[dict[str, Any]] = []
        mock_trace = MagicMock()
        mock_trace.generation = lambda **kwargs: captured_generations.append(kwargs)

        transform._langfuse_client = MagicMock()
        transform._tracing_active = True

        transform._record_langfuse_generation(
            trace=mock_trace,
            prompt="test",
            response_content="response",
            model="anthropic/claude-3-opus",
            latency_ms=1234.5,
        )

        assert len(captured_generations) == 1
        assert captured_generations[0]["metadata"]["latency_ms"] == 1234.5
