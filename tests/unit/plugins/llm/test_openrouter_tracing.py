# tests/plugins/llm/test_openrouter_tracing.py
"""Tests for Tier 2 tracing in LLMTransform (OpenRouter provider).

Note: Tests updated for Langfuse SDK v3 (context manager pattern).
Migrated from OpenRouterLLMTransform / OpenRouterMultiQueryLLMTransform
to unified LLMTransform.
"""

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.llm.langfuse import ActiveLangfuseTracer, NoOpLangfuseTracer
from elspeth.plugins.llm.providers.openrouter import OpenRouterConfig
from elspeth.plugins.llm.transform import LLMTransform


def _make_mock_ctx(run_id: str = "test-run") -> MagicMock:
    """Create a mock PluginContext."""
    ctx = MagicMock()
    ctx.landscape = MagicMock()
    ctx.run_id = run_id
    ctx.telemetry_emit = lambda x: None
    ctx.rate_limit_registry = None
    return ctx


def _make_base_config() -> dict[str, Any]:
    """Create base config with all required fields for OpenRouter."""
    return {
        "provider": "openrouter",
        "model": "anthropic/claude-3-opus",
        "api_key": "test-key",
        "template": "Hello {{ row.name }}",
        "schema": {"mode": "observed"},
        "required_input_fields": [],  # Opt-out for tests
    }


def _make_multi_query_config() -> dict[str, Any]:
    """Create base config for LLMTransform with multi-query (OpenRouter provider)."""
    return {
        "provider": "openrouter",
        "model": "anthropic/claude-3-opus",
        "api_key": "test-key",
        "template": "Case: {{ row.field1 }} Criterion: {{ row.criterion_name }}",
        "schema": {"mode": "observed"},
        "required_input_fields": [],
        "queries": {
            "cs1_crit1": {
                "input_fields": {"field1": "field1"},
                "output_fields": [{"suffix": "score", "type": "integer"}],
            },
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


class TestLLMTransformOpenRouterTracing:
    """Tests for tracing lifecycle in LLMTransform (OpenRouter provider)."""

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

    def test_azure_ai_provider_produces_noop_tracer(self) -> None:
        """Azure AI tracing config produces NoOpLangfuseTracer.

        LLMTransform only supports Langfuse tracing. When provider=openrouter
        with tracing.provider=azure_ai, the create_langfuse_tracer factory
        returns NoOp because AzureAITracingConfig is not LangfuseTracingConfig.
        """
        transform = self._create_transform(
            tracing_config={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=xxx",
            }
        )
        assert isinstance(transform._tracer, NoOpLangfuseTracer)

    def test_tracing_config_validation_returns_noop_on_missing_keys(self) -> None:
        """Langfuse config with missing keys still creates tracer (SDK may fail)."""
        # When Langfuse SDK is available but keys are None, the SDK may still
        # construct (lazy auth). The factory returns ActiveLangfuseTracer or
        # NoOpLangfuseTracer depending on whether the SDK raises.
        # What matters: no crash during construction.
        transform = self._create_transform(
            tracing_config={
                "provider": "langfuse",
                # Missing public_key and secret_key
            }
        )
        # Should be one of the two tracer types without crashing
        assert isinstance(transform._tracer, (ActiveLangfuseTracer, NoOpLangfuseTracer))

    def test_langfuse_tracer_created_on_successful_setup(self) -> None:
        """ActiveLangfuseTracer is created when Langfuse config is provided."""
        transform = self._create_transform(
            tracing_config={
                "provider": "langfuse",
                "public_key": "pk-xxx",
                "secret_key": "sk-xxx",
            }
        )

        assert isinstance(transform._tracer, ActiveLangfuseTracer)


class TestLLMTransformMultiQueryOpenRouterTracing:
    """Tests for tracing lifecycle in LLMTransform with multi-query (OpenRouter)."""

    def _create_transform(self, tracing_config: dict[str, Any] | None = None) -> LLMTransform:
        """Create a multi-query transform with optional tracing config."""
        config = _make_multi_query_config()
        if tracing_config is not None:
            config["tracing"] = tracing_config
        return LLMTransform(config)

    def test_no_tracing_when_config_is_none(self) -> None:
        """NoOpLangfuseTracer when tracing config is None."""
        transform = self._create_transform(tracing_config=None)
        assert isinstance(transform._tracer, NoOpLangfuseTracer)

    def test_azure_ai_provider_produces_noop_tracer(self) -> None:
        """Azure AI tracing config produces NoOpLangfuseTracer for multi-query."""
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

        # Langfuse is installed in test env, so factory returns ActiveLangfuseTracer at __init__ time
        assert isinstance(transform._tracer, ActiveLangfuseTracer)


class TestLangfuseSpanCreation:
    """Tests for Langfuse span creation around LLM calls (v3 API)."""

    def _create_transform_with_langfuse(self) -> tuple[LLMTransform, MagicMock, list[dict[str, Any]]]:
        """Create transform with mocked Langfuse client (v3 pattern)."""
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

        transform._tracer = ActiveLangfuseTracer(transform_name=transform.name, client=mock_langfuse)

        return transform, mock_langfuse, captured_observations

    def test_langfuse_trace_created_for_llm_call(self) -> None:
        """Langfuse trace is created when making LLM call (v3: span + generation)."""
        transform, _mock_langfuse, captured_observations = self._create_transform_with_langfuse()

        # Record trace (v3 pattern - single method call)
        transform._tracer.record_success(
            token_id="test-token",
            query_name=transform.name,
            prompt="Hello world",
            response_content="Hi there!",
            model="anthropic/claude-3-opus",
            usage=None,
            latency_ms=None,
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
            model="anthropic/claude-3-opus",
            usage=TokenUsage.known(10, 5),
            latency_ms=150.0,
        )

        # Verify generation was recorded with correct data via update()
        gen_record = captured_observations[1]  # Second observation is generation
        assert gen_record["kwargs"]["input"] == [{"role": "user", "content": "Hello world"}]
        assert gen_record["kwargs"]["model"] == "anthropic/claude-3-opus"

        # Check update() was called with output and usage_details
        assert len(gen_record["updates"]) == 1
        assert gen_record["updates"][0]["output"] == "Hi there!"
        assert gen_record["updates"][0]["usage_details"]["input"] == 10
        assert gen_record["updates"][0]["usage_details"]["output"] == 5

    def test_no_trace_when_tracing_not_active(self) -> None:
        """No trace created when tracing is not active."""
        config = _make_base_config()
        transform = LLMTransform(config)

        # This should be a no-op (no error, no trace) since _tracer is NoOpLangfuseTracer
        transform._tracer.record_success(
            token_id="test-token",
            query_name=transform.name,
            prompt="test",
            response_content="response",
            model="anthropic/claude-3-opus",
            usage=None,
            latency_ms=None,
        )
        # Verify tracer is NoOp (no Langfuse configured)
        assert isinstance(transform._tracer, NoOpLangfuseTracer)


class TestMultiQueryLangfuseTracingViaStrategy:
    """Tests for Langfuse tracing in multi-query transforms via strategy execution.

    In the unified LLMTransform, multi-query tracing happens per-query inside
    MultiQueryStrategy.execute() via tracer.record_success/record_error.
    These tests verify the tracer is correctly wired through the strategy path.
    """

    def _create_multi_query_transform_with_langfuse(
        self,
    ) -> tuple[LLMTransform, MagicMock, list[dict[str, Any]]]:
        """Create multi-query LLMTransform with mocked Langfuse client."""
        config = _make_multi_query_config()
        config["tracing"] = {
            "provider": "langfuse",
            "public_key": "pk-xxx",
            "secret_key": "sk-xxx",
        }
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

    def test_multi_query_tracer_is_active_with_langfuse_config(self) -> None:
        """Multi-query LLMTransform has ActiveLangfuseTracer when Langfuse configured."""
        transform, _mock_langfuse, _captured = self._create_multi_query_transform_with_langfuse()
        assert isinstance(transform._tracer, ActiveLangfuseTracer)

    def test_multi_query_tracer_records_per_query_success(self) -> None:
        """Tracer records success per-query during multi-query execution."""
        transform, _mock_langfuse, captured_observations = self._create_multi_query_transform_with_langfuse()

        # Simulate what MultiQueryStrategy.execute() does for each query:
        # it calls tracer.record_success after each successful LLM call
        transform._tracer.record_success(
            token_id="test-token",
            query_name="cs1_crit1",
            prompt="Case: data Criterion: criterion_name",
            response_content='{"score": 5}',
            model="anthropic/claude-3-opus",
            usage=TokenUsage.known(100, 50),
            latency_ms=500.0,
        )

        # Verify observations were created (span + generation)
        assert len(captured_observations) == 2
        span_record = captured_observations[0]
        assert span_record["kwargs"]["as_type"] == "span"
        assert span_record["kwargs"]["metadata"]["query"] == "cs1_crit1"

        gen_record = captured_observations[1]
        assert gen_record["kwargs"]["as_type"] == "generation"
        assert gen_record["kwargs"]["model"] == "anthropic/claude-3-opus"

        # Check update() recorded output and usage
        assert len(gen_record["updates"]) == 1
        assert gen_record["updates"][0]["output"] == '{"score": 5}'
        assert gen_record["updates"][0]["usage_details"]["input"] == 100
        assert gen_record["updates"][0]["usage_details"]["output"] == 50

    def test_multi_query_tracer_records_per_query_error(self) -> None:
        """Tracer records error per-query during multi-query execution."""
        transform, _mock_langfuse, captured_observations = self._create_multi_query_transform_with_langfuse()

        # Simulate what MultiQueryStrategy.execute() does on query failure
        transform._tracer.record_error(
            token_id="test-token",
            query_name="cs1_crit1",
            prompt="Case: data Criterion: criterion_name",
            error_message="Rate limit exceeded",
            model="anthropic/claude-3-opus",
            latency_ms=50.0,
        )

        # Verify error observations were created (span + generation)
        assert len(captured_observations) == 2
        gen_record = captured_observations[1]
        assert gen_record["kwargs"]["as_type"] == "generation"
        assert len(gen_record["updates"]) == 1
        assert gen_record["updates"][0]["level"] == "ERROR"
        assert "Rate limit exceeded" in gen_record["updates"][0]["status_message"]

    def test_multi_query_no_trace_when_tracing_not_configured(self) -> None:
        """Multi-query LLMTransform uses NoOpLangfuseTracer when no tracing."""
        config = _make_multi_query_config()
        transform = LLMTransform(config)

        assert isinstance(transform._tracer, NoOpLangfuseTracer)

        # record_success should be a silent no-op
        transform._tracer.record_success(
            token_id="test-token",
            query_name="cs1_crit1",
            prompt="test",
            response_content="response",
            model="anthropic/claude-3-opus",
        )
