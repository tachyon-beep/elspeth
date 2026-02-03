# tests/plugins/llm/test_openrouter_tracing.py
"""Tests for Tier 2 tracing in OpenRouter LLM transforms."""

from typing import Any
from unittest.mock import MagicMock, patch

from elspeth.plugins.llm.openrouter import OpenRouterConfig, OpenRouterLLMTransform
from elspeth.plugins.llm.openrouter_multi_query import (
    OpenRouterMultiQueryConfig,
    OpenRouterMultiQueryLLMTransform,
)
from elspeth.plugins.llm.tracing import LangfuseTracingConfig


def _make_base_config() -> dict[str, Any]:
    """Create base config with all required fields for OpenRouter."""
    return {
        "model": "anthropic/claude-3-opus",
        "api_key": "test-key",
        "template": "Hello {{ row.name }}",
        "schema": {"mode": "observed"},
        "required_input_fields": [],  # Opt-out for tests
    }


def _make_multi_query_config() -> dict[str, Any]:
    """Create base config for OpenRouter multi-query transform."""
    return {
        "model": "anthropic/claude-3-opus",
        "api_key": "test-key",
        "template": "Case: {{ input_1 }} Criterion: {{ criterion.name }}",
        "schema": {"mode": "observed"},
        "required_input_fields": [],
        "case_studies": [
            {"name": "cs1", "input_fields": ["field1"]},
        ],
        "criteria": [
            {"name": "crit1", "code": "C1"},
        ],
        "output_mapping": {
            "score": {"suffix": "score", "type": "integer"},
        },
    }


class TestOpenRouterConfigTracing:
    """Tests for tracing configuration in OpenRouterConfig."""

    def test_tracing_field_accepts_none(self) -> None:
        """Tracing field defaults to None (no tracing)."""
        config = OpenRouterConfig.from_dict(_make_base_config())
        assert config.tracing is None

    def test_tracing_field_accepts_langfuse_config(self) -> None:
        """Tracing field accepts Langfuse configuration dict."""
        cfg = _make_base_config()
        cfg["tracing"] = {
            "provider": "langfuse",
            "public_key": "pk-xxx",
            "secret_key": "sk-xxx",
        }
        config = OpenRouterConfig.from_dict(cfg)
        assert config.tracing is not None
        assert config.tracing["provider"] == "langfuse"


class TestOpenRouterLLMTransformTracing:
    """Tests for tracing lifecycle in OpenRouterLLMTransform."""

    def _create_transform(self, tracing_config: dict[str, Any] | None = None) -> OpenRouterLLMTransform:
        """Create a transform with optional tracing config."""
        config = _make_base_config()
        if tracing_config is not None:
            config["tracing"] = tracing_config
        return OpenRouterLLMTransform(config)

    def test_no_tracing_when_config_is_none(self) -> None:
        """No tracing setup when tracing config is None."""
        transform = self._create_transform(tracing_config=None)
        assert transform._tracing_config is None
        assert transform._tracing_active is False

    def test_tracing_config_is_parsed(self) -> None:
        """Tracing config dict is parsed into TracingConfig."""
        transform = self._create_transform(
            tracing_config={
                "provider": "langfuse",
                "public_key": "pk-xxx",
                "secret_key": "sk-xxx",
            }
        )
        assert transform._tracing_config is not None
        assert isinstance(transform._tracing_config, LangfuseTracingConfig)

    def test_azure_ai_provider_rejected_with_warning(self) -> None:
        """Azure AI tracing is rejected for OpenRouter with a warning."""
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
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

            # Should have logged a warning about azure_ai not being supported
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "Azure AI tracing not supported" in call_args[0][0]
            assert transform._tracing_active is False

    def test_tracing_config_validation_errors_logged(self) -> None:
        """Missing required fields log warning during on_start."""
        transform = self._create_transform(
            tracing_config={
                "provider": "langfuse",
                # Missing public_key and secret_key
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

            # Should have logged warnings about missing keys
            mock_logger.warning.assert_called()
            assert transform._tracing_active is False

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

        mock_module = MagicMock()
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


class TestOpenRouterMultiQueryConfigTracing:
    """Tests for tracing configuration in OpenRouterMultiQueryConfig."""

    def test_tracing_field_accepts_none(self) -> None:
        """Tracing field defaults to None (inherited from OpenRouterConfig)."""
        config = OpenRouterMultiQueryConfig.from_dict(_make_multi_query_config())
        assert config.tracing is None

    def test_tracing_field_accepts_langfuse_config(self) -> None:
        """Tracing field accepts Langfuse configuration dict."""
        cfg = _make_multi_query_config()
        cfg["tracing"] = {
            "provider": "langfuse",
            "public_key": "pk-xxx",
            "secret_key": "sk-xxx",
        }
        config = OpenRouterMultiQueryConfig.from_dict(cfg)
        assert config.tracing is not None
        assert config.tracing["provider"] == "langfuse"


class TestOpenRouterMultiQueryLLMTransformTracing:
    """Tests for tracing lifecycle in OpenRouterMultiQueryLLMTransform."""

    def _create_transform(self, tracing_config: dict[str, Any] | None = None) -> OpenRouterMultiQueryLLMTransform:
        """Create a multi-query transform with optional tracing config."""
        config = _make_multi_query_config()
        if tracing_config is not None:
            config["tracing"] = tracing_config
        return OpenRouterMultiQueryLLMTransform(config)

    def test_no_tracing_when_config_is_none(self) -> None:
        """No tracing setup when tracing config is None."""
        transform = self._create_transform(tracing_config=None)
        assert transform._tracing_config is None
        assert transform._tracing_active is False

    def test_tracing_config_is_parsed(self) -> None:
        """Tracing config dict is parsed into TracingConfig."""
        transform = self._create_transform(
            tracing_config={
                "provider": "langfuse",
                "public_key": "pk-xxx",
                "secret_key": "sk-xxx",
            }
        )
        assert transform._tracing_config is not None
        assert isinstance(transform._tracing_config, LangfuseTracingConfig)

    def test_azure_ai_provider_rejected_with_warning(self) -> None:
        """Azure AI tracing is rejected for OpenRouter with a warning."""
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
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

            # Should have logged a warning about azure_ai not being supported
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "Azure AI tracing not supported" in call_args[0][0]
            assert transform._tracing_active is False

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

        mock_module = MagicMock()
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

    def _create_transform_with_langfuse(self) -> tuple[OpenRouterLLMTransform, MagicMock]:
        """Create transform with mocked Langfuse client."""
        config = _make_base_config()
        config["tracing"] = {
            "provider": "langfuse",
            "public_key": "pk-xxx",
            "secret_key": "sk-xxx",
        }
        transform = OpenRouterLLMTransform(config)

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
            model="anthropic/claude-3-opus",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            latency_ms=150.0,
        )

        # Verify generation was recorded with correct data
        mock_trace.generation.assert_called_once()
        call_kwargs = mock_trace.generation.call_args.kwargs
        assert call_kwargs["input"] == "Hello world"
        assert call_kwargs["output"] == "Hi there!"
        assert call_kwargs["model"] == "anthropic/claude-3-opus"
        assert call_kwargs["usage"]["input"] == 10
        assert call_kwargs["usage"]["output"] == 5

    def test_no_trace_when_tracing_not_active(self) -> None:
        """No trace created when tracing is not active."""
        config = _make_base_config()
        transform = OpenRouterLLMTransform(config)

        with transform._create_langfuse_trace("test-token", {}) as trace:
            assert trace is None


class TestMultiQueryLangfuseSpanCreation:
    """Tests for Langfuse span creation in multi-query transforms."""

    def _create_transform_with_langfuse(
        self,
    ) -> tuple[OpenRouterMultiQueryLLMTransform, MagicMock]:
        """Create multi-query transform with mocked Langfuse client."""
        config = _make_multi_query_config()
        config["tracing"] = {
            "provider": "langfuse",
            "public_key": "pk-xxx",
            "secret_key": "sk-xxx",
        }
        transform = OpenRouterMultiQueryLLMTransform(config)

        # Mock Langfuse client
        mock_langfuse = MagicMock()
        mock_trace = MagicMock()
        mock_langfuse.trace.return_value = mock_trace

        transform._langfuse_client = mock_langfuse
        transform._tracing_active = True

        return transform, mock_langfuse

    def test_langfuse_trace_created_for_row(self) -> None:
        """Langfuse trace is created when processing a row."""
        transform, mock_langfuse = self._create_transform_with_langfuse()

        # Simulate a row processing with tracing
        with transform._create_langfuse_trace("test-token", {"field1": "value"}) as trace:
            assert trace is not None

        # Verify trace was created with multi-query metadata
        mock_langfuse.trace.assert_called_once()
        call_kwargs = mock_langfuse.trace.call_args.kwargs
        assert call_kwargs["metadata"]["query_count"] == 1  # 1 case study x 1 criterion

    def test_langfuse_generation_records_batch_summary(self) -> None:
        """Langfuse generation records batch execution summary."""
        transform, _mock_langfuse = self._create_transform_with_langfuse()

        mock_trace = MagicMock()

        # Record a multi-query batch execution
        transform._record_langfuse_generation(
            trace=mock_trace,
            query_count=4,
            succeeded_count=4,
            total_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            latency_ms=500.0,
        )

        # Verify generation was recorded with correct data
        mock_trace.generation.assert_called_once()
        call_kwargs = mock_trace.generation.call_args.kwargs
        assert call_kwargs["name"] == "multi_query_batch"
        assert call_kwargs["input"] == "4 queries"
        assert call_kwargs["output"] == "4/4 succeeded"
        assert call_kwargs["metadata"]["query_count"] == 4
        assert call_kwargs["metadata"]["succeeded_count"] == 4
        assert call_kwargs["metadata"]["latency_ms"] == 500.0

    def test_no_trace_when_tracing_not_active(self) -> None:
        """No trace created when tracing is not active."""
        config = _make_multi_query_config()
        transform = OpenRouterMultiQueryLLMTransform(config)

        with transform._create_langfuse_trace("test-token", {}) as trace:
            assert trace is None
