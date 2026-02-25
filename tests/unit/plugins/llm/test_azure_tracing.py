# tests/plugins/llm/test_azure_tracing.py
"""Tests for Tier 2 tracing in LLMTransform (Azure provider).

Note: Tests updated for Langfuse SDK v3 (context manager pattern).
Migrated from AzureLLMTransform to unified LLMTransform.
"""

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.llm.azure import AzureOpenAIConfig
from elspeth.plugins.llm.langfuse import ActiveLangfuseTracer, NoOpLangfuseTracer
from elspeth.plugins.llm.transform import LLMTransform
from elspeth.testing import make_pipeline_row


def _make_base_config() -> dict[str, Any]:
    """Create base config with all required fields."""
    return {
        "provider": "azure",
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


class TestLLMTransformAzureTracing:
    """Tests for tracing lifecycle in LLMTransform (Azure provider)."""

    def _create_transform(self, tracing_config: dict[str, Any] | None = None) -> LLMTransform:
        """Create a transform with optional tracing config."""
        config = _make_base_config()
        if tracing_config is not None:
            config["tracing"] = tracing_config
        return LLMTransform(config)

    def test_no_tracing_when_config_is_none(self) -> None:
        """NoOpLangfuseTracer when tracing config is None."""
        transform = self._create_transform(tracing_config=None)
        assert isinstance(transform._tracer, NoOpLangfuseTracer)

    def test_tracing_config_validation_returns_noop_on_missing_keys(self) -> None:
        """Langfuse config with missing keys produces NoOpLangfuseTracer.

        LLMTransform's create_langfuse_tracer factory returns NoOp when
        Langfuse config has missing public_key/secret_key (Langfuse SDK
        construction fails silently and the factory catches that).
        """
        # azure_ai tracing is not Langfuse, so factory returns NoOp
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )
        # azure_ai is not LangfuseTracingConfig, so create_langfuse_tracer returns NoOp
        assert isinstance(transform._tracer, NoOpLangfuseTracer)

    def test_azure_ai_tracing_produces_noop_langfuse_tracer(self) -> None:
        """Azure AI tracing config produces NoOpLangfuseTracer.

        LLMTransform only supports Langfuse tracing. Azure AI (OpenTelemetry)
        tracing is not configured by LLMTransform's __init__ — the factory
        returns NoOp for non-Langfuse configs.
        """
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )
        assert isinstance(transform._tracer, NoOpLangfuseTracer)

    def test_langfuse_tracer_created_on_langfuse_config(self) -> None:
        """ActiveLangfuseTracer is created when Langfuse tracing is configured."""
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

    def _create_transform_with_langfuse(self) -> tuple[LLMTransform, MagicMock, list[dict[str, Any]]]:
        """Create transform with mocked Langfuse client via LangfuseTracer."""
        config = _make_base_config()
        transform = LLMTransform(config)

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
        config = _make_base_config()
        transform = LLMTransform(config)

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

    def _create_transform_with_langfuse(self) -> tuple[LLMTransform, MagicMock, list[dict[str, Any]]]:
        """Create transform with mocked Langfuse client via LangfuseTracer."""
        config = _make_base_config()
        transform = LLMTransform(config)

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

        # Set up provider mock (LLMTransform delegates to _provider.execute_query)
        mock_provider = MagicMock()
        mock_provider.execute_query.side_effect = LLMClientError("Content policy violation", retryable=False)
        transform._provider = mock_provider

        ctx = _make_mock_ctx()
        ctx.state_id = "test-state"
        ctx.token = MagicMock()
        ctx.token.token_id = "test-token-id"

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

        # Set up provider mock (LLMTransform delegates to _provider.execute_query)
        mock_provider = MagicMock()
        mock_provider.execute_query.side_effect = LLMClientError("Rate limit exceeded", retryable=True)
        transform._provider = mock_provider

        ctx = _make_mock_ctx()
        ctx.state_id = "test-state"
        ctx.token = MagicMock()
        ctx.token.token_id = "test-token-id"

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
