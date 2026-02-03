# tests/plugins/llm/test_azure_tracing.py
"""Tests for Tier 2 tracing in AzureLLMTransform."""

from typing import Any
from unittest.mock import MagicMock, patch

from elspeth.plugins.llm.azure import AzureLLMTransform, AzureOpenAIConfig
from elspeth.plugins.llm.tracing import AzureAITracingConfig


def _make_base_config() -> dict[str, Any]:
    """Create base config with all required fields."""
    return {
        "deployment_name": "gpt-4",
        "endpoint": "https://test.openai.azure.com",
        "api_key": "test-key",
        "template": "Hello {{ row.name }}",
        "schema": {"mode": "observed"},
        "required_input_fields": [],  # Opt-out for tests
    }


class TestAzureOpenAIConfigTracing:
    """Tests for tracing configuration in AzureOpenAIConfig."""

    def test_tracing_field_accepts_none(self) -> None:
        """Tracing field defaults to None (no tracing)."""
        config = AzureOpenAIConfig.from_dict(_make_base_config())
        assert config.tracing is None

    def test_tracing_field_accepts_azure_ai_config(self) -> None:
        """Tracing field accepts Azure AI configuration dict."""
        cfg = _make_base_config()
        cfg["tracing"] = {
            "provider": "azure_ai",
            "connection_string": "InstrumentationKey=xxx",
            "enable_content_recording": True,
        }
        config = AzureOpenAIConfig.from_dict(cfg)
        assert config.tracing is not None
        assert config.tracing["provider"] == "azure_ai"

    def test_tracing_field_accepts_langfuse_config(self) -> None:
        """Tracing field accepts Langfuse configuration dict."""
        cfg = _make_base_config()
        cfg["tracing"] = {
            "provider": "langfuse",
            "public_key": "pk-xxx",
            "secret_key": "sk-xxx",
        }
        config = AzureOpenAIConfig.from_dict(cfg)
        assert config.tracing is not None
        assert config.tracing["provider"] == "langfuse"


class TestAzureLLMTransformTracing:
    """Tests for tracing lifecycle in AzureLLMTransform."""

    def _create_transform(self, tracing_config: dict[str, Any] | None = None) -> AzureLLMTransform:
        """Create a transform with optional tracing config."""
        config = _make_base_config()
        if tracing_config is not None:
            config["tracing"] = tracing_config
        return AzureLLMTransform(config)

    def test_no_tracing_when_config_is_none(self) -> None:
        """No tracing setup when tracing config is None."""
        transform = self._create_transform(tracing_config=None)
        assert transform._tracing_config is None
        assert transform._tracing_active is False

    def test_tracing_config_is_parsed(self) -> None:
        """Tracing config dict is parsed into TracingConfig."""
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )
        assert transform._tracing_config is not None
        assert isinstance(transform._tracing_config, AzureAITracingConfig)

    def test_tracing_config_validation_errors_logged(self) -> None:
        """Missing required fields log warning during on_start."""
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                # Missing connection_string
            }
        )

        with patch("structlog.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            ctx = MagicMock()
            ctx.landscape = MagicMock()
            ctx.run_id = "test-run"
            ctx.telemetry_emit = lambda x: None
            ctx.rate_limit_registry = None

            transform.on_start(ctx)

            # Should have logged a warning about missing connection_string
            mock_logger.warning.assert_called()
            assert transform._tracing_active is False

    def test_tracing_active_flag_set_on_successful_setup(self) -> None:
        """_tracing_active is True after successful tracing setup."""
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )

        # Mock successful import and configure
        with patch("elspeth.plugins.llm.azure._configure_azure_monitor") as mock_configure:
            mock_configure.return_value = True  # Success

            # Mock OTEL to avoid conflict check
            with patch("opentelemetry.trace.get_tracer_provider") as mock_get_provider:
                mock_provider = MagicMock()
                mock_provider.__class__.__name__ = "ProxyTracerProvider"
                mock_get_provider.return_value = mock_provider

                ctx = MagicMock()
                ctx.landscape = MagicMock()
                ctx.run_id = "test-run"
                ctx.telemetry_emit = lambda x: None
                ctx.rate_limit_registry = None

                transform.on_start(ctx)

                # Verify configure was called
                mock_configure.assert_called_once()
                assert transform._tracing_active is True

    def test_langfuse_client_stored_on_successful_setup(self) -> None:
        """Langfuse client is stored for use in LLM calls."""
        transform = self._create_transform(
            tracing_config={
                "provider": "langfuse",
                "public_key": "pk-xxx",
                "secret_key": "sk-xxx",
            }
        )

        mock_langfuse_instance = MagicMock()
        mock_langfuse_class = MagicMock(return_value=mock_langfuse_instance)

        # Patch the import inside the method
        import sys
        from unittest.mock import MagicMock as MM

        mock_module = MM()
        mock_module.Langfuse = mock_langfuse_class

        with patch.dict(sys.modules, {"langfuse": mock_module}):
            ctx = MagicMock()
            ctx.landscape = MagicMock()
            ctx.run_id = "test-run"
            ctx.telemetry_emit = lambda x: None
            ctx.rate_limit_registry = None

            transform.on_start(ctx)

            assert transform._tracing_active is True
            assert transform._langfuse_client is mock_langfuse_instance


class TestLangfuseSpanCreation:
    """Tests for Langfuse span creation around LLM calls."""

    def _create_transform_with_langfuse(self) -> tuple[AzureLLMTransform, MagicMock]:
        """Create transform with mocked Langfuse client."""
        config = _make_base_config()
        config["tracing"] = {
            "provider": "langfuse",
            "public_key": "pk-xxx",
            "secret_key": "sk-xxx",
        }
        transform = AzureLLMTransform(config)

        # Mock Langfuse client
        mock_langfuse = MagicMock()
        mock_trace = MagicMock()
        mock_langfuse.trace.return_value = mock_trace

        transform._langfuse_client = mock_langfuse
        transform._tracing_active = True

        return transform, mock_langfuse

    def test_langfuse_trace_created_for_llm_call(self) -> None:
        """Langfuse trace is created when making LLM call."""
        transform, mock_langfuse = self._create_transform_with_langfuse()

        # Simulate an LLM call with tracing
        with transform._create_langfuse_trace("test-token", {"name": "world"}) as trace:
            assert trace is not None

        # Verify trace was created
        mock_langfuse.trace.assert_called_once()

    def test_langfuse_generation_records_input_output(self) -> None:
        """Langfuse generation records prompt and response."""
        transform, _mock_langfuse = self._create_transform_with_langfuse()

        mock_trace = MagicMock()

        # Record a generation
        transform._record_langfuse_generation(
            trace=mock_trace,
            prompt="Hello world",
            response_content="Hi there!",
            model="gpt-4",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            latency_ms=150.0,
        )

        # Verify generation was recorded with correct data
        mock_trace.generation.assert_called_once()
        call_kwargs = mock_trace.generation.call_args.kwargs
        assert call_kwargs["input"] == "Hello world"
        assert call_kwargs["output"] == "Hi there!"
        assert call_kwargs["model"] == "gpt-4"
        assert call_kwargs["usage"]["input"] == 10
        assert call_kwargs["usage"]["output"] == 5

    def test_no_trace_when_tracing_not_active(self) -> None:
        """No trace created when tracing is not active."""
        config = _make_base_config()
        transform = AzureLLMTransform(config)

        with transform._create_langfuse_trace("test-token", {}) as trace:
            assert trace is None
