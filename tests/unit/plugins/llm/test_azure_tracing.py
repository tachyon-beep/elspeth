# tests/plugins/llm/test_azure_tracing.py
"""Tests for Tier 2 tracing in AzureLLMTransform.

Note: Tests updated for Langfuse SDK v3 (context manager pattern).
"""

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.llm.azure import AzureLLMTransform, AzureOpenAIConfig
from elspeth.plugins.llm.tracing import AzureAITracingConfig
from elspeth.testing import make_pipeline_row


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

    def test_langfuse_tracer_created_on_langfuse_config(self) -> None:
        """LangfuseTracer is created when Langfuse tracing is configured."""
        from elspeth.plugins.llm.langfuse import ActiveLangfuseTracer

        transform = self._create_transform(
            tracing_config={
                "provider": "langfuse",
                "public_key": "pk-xxx",
                "secret_key": "sk-xxx",
            }
        )

        # Langfuse is installed in test env, so tracer should be active
        assert isinstance(transform._tracer, ActiveLangfuseTracer)


def _make_mock_ctx(run_id: str = "test-run") -> MagicMock:
    """Create a mock PluginContext."""
    ctx = MagicMock()
    ctx.landscape = MagicMock()
    ctx.run_id = run_id
    ctx.telemetry_emit = lambda x: None
    ctx.rate_limit_registry = None
    return ctx


class TestLangfuseSpanCreation:
    """Tests for Langfuse span creation around LLM calls (v3 API)."""

    def _create_transform_with_langfuse(self) -> tuple[AzureLLMTransform, MagicMock, list[dict[str, Any]]]:
        """Create transform with mocked Langfuse client via LangfuseTracer."""
        from elspeth.plugins.llm.langfuse import ActiveLangfuseTracer

        config = _make_base_config()
        transform = AzureLLMTransform(config)

        captured_observations: list[dict[str, Any]] = []

        @contextmanager
        def mock_start_observation(**kwargs: Any):
            obs = MagicMock()
            obs_record: dict[str, Any] = {"kwargs": kwargs, "updates": []}
            captured_observations.append(obs_record)
            obs.update = lambda **uk: obs_record["updates"].append(uk)
            yield obs

        mock_langfuse = MagicMock()
        mock_langfuse.start_as_current_observation = mock_start_observation
        mock_langfuse.flush = MagicMock()

        transform._tracer = ActiveLangfuseTracer(
            transform_name=transform.name,
            client=mock_langfuse,
        )

        return transform, mock_langfuse, captured_observations

    def test_langfuse_trace_created_for_llm_call(self) -> None:
        """Langfuse trace is created when making LLM call (v3: span + generation)."""
        transform, _mock_langfuse, captured_observations = self._create_transform_with_langfuse()

        # Record trace via tracer
        transform._tracer.record_success(
            token_id="test-token",
            query_name=transform.name,
            prompt="Hello world",
            response_content="Hi there!",
            model="gpt-4",
        )

        # Verify observations were created (span + generation)
        assert len(captured_observations) == 2
        assert captured_observations[0]["kwargs"]["as_type"] == "span"
        assert captured_observations[1]["kwargs"]["as_type"] == "generation"

    def test_langfuse_generation_records_input_output(self) -> None:
        """Langfuse generation records prompt and response via update()."""
        transform, _mock_langfuse, captured_observations = self._create_transform_with_langfuse()

        # Record a trace
        transform._tracer.record_success(
            token_id="test-token",
            query_name=transform.name,
            prompt="Hello world",
            response_content="Hi there!",
            model="gpt-4",
            usage=TokenUsage.known(10, 5),
            latency_ms=150.0,
        )

        # Verify generation was recorded with correct data via update()
        gen_record = captured_observations[1]  # Second observation is generation
        assert gen_record["kwargs"]["input"] == [{"role": "user", "content": "Hello world"}]
        assert gen_record["kwargs"]["model"] == "gpt-4"

        # Check update() was called with output and usage_details
        assert len(gen_record["updates"]) == 1
        assert gen_record["updates"][0]["output"] == "Hi there!"
        assert gen_record["updates"][0]["usage_details"]["input"] == 10
        assert gen_record["updates"][0]["usage_details"]["output"] == 5

    def test_no_trace_when_tracing_not_configured(self) -> None:
        """No-op tracer used when tracing is not configured."""
        from elspeth.plugins.llm.langfuse import NoOpLangfuseTracer

        config = _make_base_config()
        transform = AzureLLMTransform(config)

        # When no tracing config, factory returns NoOpLangfuseTracer
        assert isinstance(transform._tracer, NoOpLangfuseTracer)

        # record_success should be a silent no-op
        transform._tracer.record_success(
            token_id="test-token",
            query_name=transform.name,
            prompt="test",
            response_content="response",
            model="gpt-4",
        )


class TestLangfuseFailedCallTracing:
    """Tests for Langfuse tracing of failed LLM calls.

    Verifies that failed LLM calls (rate limit, policy errors, etc.) are
    still traced to Langfuse with level="ERROR" for observability.
    """

    def _create_transform_with_langfuse(self) -> tuple[AzureLLMTransform, MagicMock, list[dict[str, Any]]]:
        """Create transform with mocked Langfuse client via LangfuseTracer."""
        from elspeth.plugins.llm.langfuse import ActiveLangfuseTracer

        config = _make_base_config()
        transform = AzureLLMTransform(config)

        captured_observations: list[dict[str, Any]] = []

        @contextmanager
        def mock_start_observation(**kwargs: Any):
            obs = MagicMock()
            obs_record: dict[str, Any] = {"kwargs": kwargs, "updates": []}
            captured_observations.append(obs_record)
            obs.update = lambda **uk: obs_record["updates"].append(uk)
            yield obs

        mock_langfuse = MagicMock()
        mock_langfuse.start_as_current_observation = mock_start_observation
        mock_langfuse.flush = MagicMock()

        transform._tracer = ActiveLangfuseTracer(
            transform_name=transform.name,
            client=mock_langfuse,
        )

        return transform, mock_langfuse, captured_observations

    def test_langfuse_trace_records_failed_call_with_error_level(self) -> None:
        """Failed LLM call records trace with level=ERROR for observability."""
        transform, _mock_langfuse, captured_observations = self._create_transform_with_langfuse()

        # Record failed trace
        transform._tracer.record_error(
            token_id="test-token",
            query_name=transform.name,
            prompt="Hello world",
            error_message="Rate limit exceeded",
            model="gpt-4",
            latency_ms=50.0,
        )

        # Verify observations were created (span + generation)
        assert len(captured_observations) == 2
        assert captured_observations[0]["kwargs"]["as_type"] == "span"
        assert captured_observations[1]["kwargs"]["as_type"] == "generation"

        # Verify generation was updated with ERROR level
        gen_record = captured_observations[1]
        assert len(gen_record["updates"]) == 1
        assert gen_record["updates"][0]["level"] == "ERROR"
        assert "Rate limit exceeded" in gen_record["updates"][0]["status_message"]

    def test_langfuse_trace_error_includes_metadata(self) -> None:
        """Failed LLM trace includes latency metadata."""
        transform, _mock_langfuse, captured_observations = self._create_transform_with_langfuse()

        transform._tracer.record_error(
            token_id="test-token",
            query_name=transform.name,
            prompt="Test prompt",
            error_message="Content policy violation",
            model="gpt-4",
            latency_ms=25.0,
        )

        # Verify metadata includes latency
        gen_record = captured_observations[1]
        update = gen_record["updates"][0]
        assert update.get("metadata", {}).get("latency_ms") == 25.0

    def test_process_row_records_error_trace_on_llm_failure(self) -> None:
        """_process_row records Langfuse trace when LLM call fails."""
        from elspeth.plugins.clients.llm import LLMClientError

        transform, _mock_langfuse, captured_observations = self._create_transform_with_langfuse()

        # Set up recorder and run_id (required for _get_llm_client)
        transform._recorder = MagicMock()
        transform._run_id = "test-run"

        ctx = _make_mock_ctx()
        ctx.state_id = "test-state"
        ctx.token = MagicMock()
        ctx.token.token_id = "test-token-id"

        # Mock _get_llm_client to return a client that raises an error
        mock_client = MagicMock()
        mock_client.chat_completion.side_effect = LLMClientError("Content policy violation", retryable=False)

        with patch.object(transform, "_get_llm_client", return_value=mock_client):
            result = transform._process_row(make_pipeline_row({"name": "test"}), ctx)

        # Should return error result
        assert result.status == "error"
        assert result.reason is not None and result.reason["reason"] == "llm_call_failed"

        # And also have recorded the error trace in Langfuse
        assert len(captured_observations) == 2  # span + generation
        gen_record = captured_observations[1]
        assert gen_record["kwargs"]["as_type"] == "generation"
        assert len(gen_record["updates"]) == 1
        assert gen_record["updates"][0]["level"] == "ERROR"
        assert "Content policy violation" in gen_record["updates"][0]["status_message"]

    def test_process_row_records_error_trace_on_retryable_failure(self) -> None:
        """_process_row records Langfuse trace even for retryable errors before re-raising."""
        from elspeth.plugins.clients.llm import LLMClientError

        transform, _mock_langfuse, captured_observations = self._create_transform_with_langfuse()

        # Set up recorder and run_id (required for _get_llm_client)
        transform._recorder = MagicMock()
        transform._run_id = "test-run"

        ctx = _make_mock_ctx()
        ctx.state_id = "test-state"
        ctx.token = MagicMock()
        ctx.token.token_id = "test-token-id"

        # Mock _get_llm_client to return a client that raises a retryable error
        mock_client = MagicMock()
        mock_client.chat_completion.side_effect = LLMClientError("Rate limit exceeded", retryable=True)

        with patch.object(transform, "_get_llm_client", return_value=mock_client):
            try:
                transform._process_row(make_pipeline_row({"name": "test"}), ctx)
                raise AssertionError("Should have raised LLMClientError")
            except LLMClientError:
                pass  # Expected

        # Error trace should still have been recorded before re-raising
        assert len(captured_observations) == 2  # span + generation
        gen_record = captured_observations[1]
        assert gen_record["updates"][0]["level"] == "ERROR"
        assert "Rate limit exceeded" in gen_record["updates"][0]["status_message"]
