# tests/unit/plugins/llm/test_transform.py
"""Tests for unified LLMTransform (Task 9).

Tests strategy dispatch, provider dispatch, error classification,
contract propagation, truncation detection, fence stripping,
tracer wiring, and multi-query partial failure atomicity.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest

from elspeth.contracts import Determinism
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.clients.llm import (
    ContentPolicyError,
    ContextLengthError,
    LLMClientError,
    NetworkError,
    RateLimitError,
    ServerError,
)
from elspeth.plugins.llm.provider import FinishReason, LLMQueryResult
from elspeth.testing import make_pipeline_row

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Common observed schema config
DYNAMIC_SCHEMA = {"mode": "observed"}


def _make_row(data: dict[str, Any] | None = None) -> PipelineRow:
    """Create a test PipelineRow with OBSERVED contract."""
    return make_pipeline_row(data or {"text": "hello"})


def _make_ctx() -> Mock:
    """Create a minimal mock PluginContext."""
    ctx = Mock()
    ctx.state_id = "state-123"
    ctx.run_id = "run-123"
    ctx.token = Mock()
    ctx.token.token_id = "token-1"
    return ctx


def _make_config(*, provider: str = "azure", **overrides: Any) -> dict[str, Any]:
    """Build minimal valid LLMTransform config."""
    base: dict[str, Any] = {
        "provider": provider,
        "template": "Classify: {{ row.text }}",
        "schema": DYNAMIC_SCHEMA,
        "required_input_fields": ["text"],
    }
    if provider == "azure":
        base.update(
            deployment_name="gpt-4o",
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
        )
    elif provider == "openrouter":
        base.update(
            model="openai/gpt-4o",
            api_key="test-key",
        )
    base.update(overrides)
    return base


def _make_multi_query_config(*, provider: str = "azure", **overrides: Any) -> dict[str, Any]:
    """Build LLMTransform config with multi-query specs."""
    config = _make_config(provider=provider, **overrides)
    config["queries"] = {
        "quality": {
            "input_fields": {"text_content": "text"},
        },
        "relevance": {
            "input_fields": {"text_content": "text"},
        },
    }
    return config


def _make_transform_with_mock_provider(
    config: dict[str, Any] | None = None,
) -> tuple[Any, Mock]:
    """Create an LLMTransform with a mocked provider already set."""
    from elspeth.plugins.llm.transform import LLMTransform

    transform = LLMTransform(config or _make_config())
    mock_provider = Mock()
    transform._provider = mock_provider
    return transform, mock_provider


# ---------------------------------------------------------------------------
# Strategy dispatch
# ---------------------------------------------------------------------------


class TestStrategyDispatch:
    """Verify correct strategy selection based on queries field."""

    def test_strategy_type_is_single_query_when_no_queries(self) -> None:
        """When queries is None (default), SingleQueryStrategy is used."""
        from elspeth.plugins.llm.transform import LLMTransform, SingleQueryStrategy

        config = _make_config()
        transform = LLMTransform(config)
        assert isinstance(transform._strategy, SingleQueryStrategy)

    def test_strategy_type_is_multi_query_when_queries_provided(self) -> None:
        """When queries is explicitly provided, MultiQueryStrategy is used."""
        from elspeth.plugins.llm.transform import LLMTransform, MultiQueryStrategy

        config = _make_multi_query_config()
        transform = LLMTransform(config)
        assert isinstance(transform._strategy, MultiQueryStrategy)


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------


class TestProviderDispatch:
    """Verify correct provider creation based on provider field."""

    def test_azure_creates_azure_config(self) -> None:
        from elspeth.plugins.llm.azure import AzureOpenAIConfig
        from elspeth.plugins.llm.transform import LLMTransform

        transform = LLMTransform(_make_config(provider="azure"))
        assert isinstance(transform._config, AzureOpenAIConfig)

    def test_openrouter_creates_openrouter_config(self) -> None:
        from elspeth.plugins.llm.openrouter import OpenRouterConfig
        from elspeth.plugins.llm.transform import LLMTransform

        transform = LLMTransform(_make_config(provider="openrouter"))
        assert isinstance(transform._config, OpenRouterConfig)

    def test_unknown_provider_raises_with_valid_options(self) -> None:
        from elspeth.plugins.llm.transform import LLMTransform

        with pytest.raises(ValueError, match="Unknown LLM provider") as exc_info:
            LLMTransform(_make_config(provider="anthropic"))

        # Error message lists valid providers
        assert "azure" in str(exc_info.value)
        assert "openrouter" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Transform properties
# ---------------------------------------------------------------------------


class TestTransformProperties:
    """Verify LLMTransform class attributes and lifecycle."""

    def test_name_is_llm(self) -> None:
        from elspeth.plugins.llm.transform import LLMTransform

        transform = LLMTransform(_make_config())
        assert transform.name == "llm"

    def test_determinism_is_non_deterministic(self) -> None:
        from elspeth.plugins.llm.transform import LLMTransform

        transform = LLMTransform(_make_config())
        assert transform.determinism == Determinism.NON_DETERMINISTIC

    def test_llm_transform_uses_process_row_not_process(self) -> None:
        """LLMTransform extends BatchTransformMixin — process() raises NotImplementedError."""
        from elspeth.plugins.batching import BatchTransformMixin
        from elspeth.plugins.llm.transform import LLMTransform

        assert issubclass(LLMTransform, BatchTransformMixin)

        transform = LLMTransform(_make_config())
        with pytest.raises(NotImplementedError, match="accept"):
            transform.process(Mock(), Mock())


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class TestErrorClassification:
    """Verify LLM exception types map to correct TransformResult."""

    @pytest.fixture()
    def transform_with_mock_provider(self) -> Any:
        """Create LLMTransform with a mock provider for error testing."""
        transform, mock_provider = _make_transform_with_mock_provider()
        row = _make_row()
        ctx = _make_ctx()
        return transform, mock_provider, row, ctx

    def test_error_classification_rate_limit_is_retryable(self, transform_with_mock_provider: Any) -> None:
        transform, mock_provider, row, ctx = transform_with_mock_provider
        mock_provider.execute_query.side_effect = RateLimitError("429 Too Many Requests")

        # RateLimitError should re-raise (retryable) for engine retry
        with pytest.raises(RateLimitError):
            transform._process_row(row, ctx)

    def test_error_classification_network_error_is_retryable(self, transform_with_mock_provider: Any) -> None:
        transform, mock_provider, row, ctx = transform_with_mock_provider
        mock_provider.execute_query.side_effect = NetworkError("Connection refused")

        with pytest.raises(NetworkError):
            transform._process_row(row, ctx)

    def test_error_classification_server_error_is_retryable(self, transform_with_mock_provider: Any) -> None:
        transform, mock_provider, row, ctx = transform_with_mock_provider
        mock_provider.execute_query.side_effect = ServerError("500 Internal Server Error")

        with pytest.raises(ServerError):
            transform._process_row(row, ctx)

    def test_error_classification_content_policy_not_retryable(self, transform_with_mock_provider: Any) -> None:
        transform, mock_provider, row, ctx = transform_with_mock_provider
        mock_provider.execute_query.side_effect = ContentPolicyError("Content filtered")

        result = transform._process_row(row, ctx)
        assert result.status == "error"
        assert result.retryable is False

    def test_error_classification_context_length_error(self, transform_with_mock_provider: Any) -> None:
        transform, mock_provider, row, ctx = transform_with_mock_provider
        mock_provider.execute_query.side_effect = ContextLengthError("Context too long")

        result = transform._process_row(row, ctx)
        assert result.status == "error"
        assert result.retryable is False
        assert result.reason is not None
        assert result.reason["reason"] == "context_length_exceeded"

    def test_error_classification_llm_client_error_not_retryable(self, transform_with_mock_provider: Any) -> None:
        transform, mock_provider, row, ctx = transform_with_mock_provider
        mock_provider.execute_query.side_effect = LLMClientError("Bad request", retryable=False)

        result = transform._process_row(row, ctx)
        assert result.status == "error"
        assert result.retryable is False


# ---------------------------------------------------------------------------
# Single-query success path
# ---------------------------------------------------------------------------


class TestSingleQuerySuccess:
    """Verify single-query happy path."""

    def test_single_query_success_produces_output(self) -> None:
        transform, mock_provider = _make_transform_with_mock_provider()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="classified as: positive",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        assert result.row["llm_response"] == "classified as: positive"
        assert result.row["llm_response_model"] == "gpt-4o"

    def test_contract_propagation_single_query(self) -> None:
        """Single-query mode uses propagate_contract on input contract."""
        transform, mock_provider = _make_transform_with_mock_provider()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="result",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
        )

        row = _make_row()
        result = transform._process_row(row, _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        # Output row has a contract (propagated from input)
        assert result.row.contract is not None

    def test_contract_propagation_multi_query(self) -> None:
        """Multi-query mode propagates contract with OBSERVED fields from all queries."""
        from elspeth.plugins.llm.transform import LLMTransform

        # Multi-query needs a template that works with build_template_context output.
        # input_fields maps {"text_content": "text"}, meaning row["text"] is accessed
        # as row.text_content in the template (PromptTemplate.render wraps context under "row").
        config = _make_config(
            template="Classify: {{ row.text_content }}",
            queries={
                "quality": {"input_fields": {"text_content": "text"}},
                "relevance": {"input_fields": {"text_content": "text"}},
            },
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content='{"result": "ok"}',
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )
        transform._provider = mock_provider

        row = _make_row()
        result = transform._process_row(row, _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        # Output row has a contract (propagated from input, includes new fields)
        assert result.row.contract is not None
        # Multi-query adds query-prefixed fields
        assert any(k.startswith("quality_") or k.startswith("relevance_") for k in result.row.to_dict())


# ---------------------------------------------------------------------------
# Truncation detection
# ---------------------------------------------------------------------------


class TestTruncationDetection:
    """Verify truncated responses (finish_reason=LENGTH) are errors."""

    def test_truncated_response_returns_error(self) -> None:
        transform, mock_provider = _make_transform_with_mock_provider()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="partial response that got cut",
            usage=TokenUsage.known(10, 500),
            model="gpt-4o",
            finish_reason=FinishReason.LENGTH,
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.reason is not None
        # The error reason should indicate truncation
        reason_str = str(result.reason).lower()
        assert "truncat" in reason_str or "length" in reason_str


# ---------------------------------------------------------------------------
# Fence stripping
# ---------------------------------------------------------------------------


class TestFenceStripping:
    """Verify markdown code fences are stripped in STANDARD response mode."""

    def test_markdown_json_fences_stripped(self) -> None:
        transform, mock_provider = _make_transform_with_mock_provider()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content='```json\n{"result": "positive"}\n```',
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        content = result.row["llm_response"]
        # Fences should be stripped — content should NOT start with ```
        assert not content.startswith("```")
        assert "```" not in content

    def test_plain_fences_stripped(self) -> None:
        transform, mock_provider = _make_transform_with_mock_provider()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content='```\n{"result": "positive"}\n```',
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        content = result.row["llm_response"]
        assert "```" not in content


# ---------------------------------------------------------------------------
# Tracer wiring
# ---------------------------------------------------------------------------


class TestTracerWiring:
    """Verify tracer selection based on config."""

    def test_tracer_is_noop_when_no_tracing_config(self) -> None:
        from elspeth.plugins.llm.langfuse import NoOpLangfuseTracer
        from elspeth.plugins.llm.transform import LLMTransform

        transform = LLMTransform(_make_config())
        assert isinstance(transform._tracer, NoOpLangfuseTracer)

    def test_tracer_is_active_when_langfuse_configured(self) -> None:
        """When Langfuse is configured and importable, ActiveLangfuseTracer is used."""
        from elspeth.plugins.llm.langfuse import ActiveLangfuseTracer
        from elspeth.plugins.llm.transform import LLMTransform

        # Mock the langfuse package at the import level used by create_langfuse_tracer
        mock_langfuse = Mock()
        mock_langfuse_cls = Mock()
        mock_langfuse.Langfuse = mock_langfuse_cls

        with patch.dict("sys.modules", {"langfuse": mock_langfuse}):
            config = _make_config(
                tracing={
                    "provider": "langfuse",
                    "public_key": "pk-test",
                    "secret_key": "sk-test",
                },
            )
            transform = LLMTransform(config)
            assert isinstance(transform._tracer, ActiveLangfuseTracer)


# ---------------------------------------------------------------------------
# Provider client isolation
# ---------------------------------------------------------------------------


class TestTracingLifecycle:
    """Verify tracing setup is in transform lifecycle, not provider init."""

    def test_azure_ai_tracing_not_in_provider_init(self) -> None:
        """Azure AI tracing setup belongs in on_start(), not provider __init__.

        The AzureLLMProvider docstring confirms: 'tracing config belongs to the
        transform lifecycle'. Verify that constructing a provider does NOT
        attempt to configure azure_ai tracing.
        """
        from elspeth.plugins.llm.providers.azure import AzureLLMProvider

        provider = AzureLLMProvider(
            endpoint="https://test.openai.azure.com/",
            api_key="test-key",
            api_version="2024-10-21",
            deployment_name="gpt-4o",
            recorder=Mock(),
            run_id="run-1",
            telemetry_emit=Mock(),
        )
        # Provider should NOT have any tracing attributes — tracing is transform-owned
        assert not hasattr(provider, "_azure_monitor_configured")
        assert not hasattr(provider, "_tracing_config")
        assert not hasattr(provider, "_tracer")


class TestProviderClientIsolation:
    """Verify LLMTransform uses its own provider, not ctx.llm_client."""

    def test_llm_transform_does_not_use_ctx_llm_client(self) -> None:
        """Set ctx.llm_client to sentinel that raises — transform must succeed via provider."""
        transform, mock_provider = _make_transform_with_mock_provider()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="provider response",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
        )

        ctx = _make_ctx()
        # Sentinel: any access to ctx.llm_client raises
        sentinel = Mock()
        sentinel.side_effect = RuntimeError("SENTINEL: ctx.llm_client was accessed!")
        ctx.llm_client = sentinel

        # Should succeed without touching ctx.llm_client
        result = transform._process_row(_make_row(), ctx)
        assert result.status == "success"
        # Verify sentinel was never called
        sentinel.assert_not_called()


# ---------------------------------------------------------------------------
# Multi-query partial failure
# ---------------------------------------------------------------------------


class TestMultiQueryPartialFailure:
    """Verify multi-query atomicity — partial failure discards all results."""

    def test_multi_query_partial_failure_discards_successful_results(self) -> None:
        """4 queries, query 3 fails → ALL results discarded, error has details."""
        from elspeth.plugins.llm.transform import LLMTransform, MultiQueryStrategy

        config = _make_config(template="Classify: {{ row.text_content }}")
        config["queries"] = {
            "q1": {"input_fields": {"text_content": "text"}},
            "q2": {"input_fields": {"text_content": "text"}},
            "q3": {"input_fields": {"text_content": "text"}},
            "q4": {"input_fields": {"text_content": "text"}},
        }
        transform = LLMTransform(config)
        assert isinstance(transform._strategy, MultiQueryStrategy)

        # Mock provider: queries 1,2 succeed, query 3 fails, query 4 would succeed
        call_count = [0]

        def mock_execute_query(messages, *, model, temperature, max_tokens, state_id, token_id):
            call_count[0] += 1
            if call_count[0] == 3:
                raise LLMClientError("Bad response for query 3", retryable=False)
            return LLMQueryResult(
                content=f'{{"result": "success_{call_count[0]}"}}',
                usage=TokenUsage.known(10, 5),
                model="gpt-4o",
                finish_reason=FinishReason.STOP,
            )

        mock_provider = Mock()
        mock_provider.execute_query.side_effect = mock_execute_query
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"

        # Error reason must include: (a) which query failed (name + index),
        # (b) failure detail, (c) how many queries succeeded but were discarded
        assert result.reason is not None
        assert result.reason["failed_query_name"] == "q3"
        assert result.reason["failed_query_index"] == 2  # 0-indexed
        assert result.reason["discarded_successful_queries"] == 2
        assert "Bad response for query 3" in result.reason["error"]

        # No output data should exist
        assert result.row is None


# ---------------------------------------------------------------------------
# Multi-query JSON parsing and field extraction
# ---------------------------------------------------------------------------


class TestMultiQueryJSONExtraction:
    """Verify multi-query JSON parsing and field extraction when output_fields configured."""

    def test_output_fields_extracts_typed_fields_from_json(self) -> None:
        """When output_fields is configured, JSON is parsed and fields extracted."""
        from elspeth.plugins.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "quality": {
                    "input_fields": {"text_content": "text"},
                    "output_fields": [
                        {"suffix": "score", "type": "integer"},
                        {"suffix": "label", "type": "string"},
                    ],
                },
            },
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content='{"score": 85, "label": "high quality"}',
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        output = result.row.to_dict()
        # Extracted typed fields
        assert output["quality_score"] == 85
        assert output["quality_label"] == "high quality"
        # Raw content also stored for audit
        assert output["quality_llm_response"] == '{"score": 85, "label": "high quality"}'

    def test_output_fields_missing_field_returns_none(self) -> None:
        """When a field is missing from JSON response, it stores None."""
        from elspeth.plugins.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {
                    "input_fields": {"text_content": "text"},
                    "output_fields": [
                        {"suffix": "score", "type": "integer"},
                        {"suffix": "missing_field", "type": "string"},
                    ],
                },
            },
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content='{"score": 42}',
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        output = result.row.to_dict()
        assert output["q1_score"] == 42
        assert output["q1_missing_field"] is None

    def test_output_fields_json_parse_failure_returns_error(self) -> None:
        """When LLM returns invalid JSON and output_fields expects JSON, return error."""
        from elspeth.plugins.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {
                    "input_fields": {"text_content": "text"},
                    "output_fields": [{"suffix": "score", "type": "integer"}],
                },
            },
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="not valid json at all",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "json_parse_failed"
        assert result.reason["query_name"] == "q1"

    def test_output_fields_json_array_returns_error(self) -> None:
        """When LLM returns a JSON array instead of object, return structured error."""
        from elspeth.plugins.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {
                    "input_fields": {"text_content": "text"},
                    "output_fields": [{"suffix": "score", "type": "integer"}],
                },
            },
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="[1, 2, 3]",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "invalid_json_type"
        assert result.reason["expected"] == "object"
        assert result.reason["actual"] == "list"

    def test_no_output_fields_stores_raw_content(self) -> None:
        """When output_fields is None, raw content stored (current behavior)."""
        from elspeth.plugins.llm.transform import LLMTransform

        config = _make_config(
            template="Classify: {{ row.text_content }}",
            queries={
                "q1": {"input_fields": {"text_content": "text"}},
            },
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="just plain text",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        assert result.row["q1_llm_response"] == "just plain text"


# ---------------------------------------------------------------------------
# Multi-query context length error
# ---------------------------------------------------------------------------


class TestMultiQueryContextLength:
    """Verify ContextLengthError in multi-query returns specific reason."""

    def test_context_length_error_returns_specific_reason(self) -> None:
        from elspeth.plugins.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {"input_fields": {"text_content": "text"}},
                "q2": {"input_fields": {"text_content": "text"}},
            },
        )
        transform = LLMTransform(config)
        call_count = [0]

        def mock_execute(messages, *, model, temperature, max_tokens, state_id, token_id):
            call_count[0] += 1
            if call_count[0] == 2:
                raise ContextLengthError("Context too long for q2")
            return LLMQueryResult(
                content="ok",
                usage=TokenUsage.known(10, 5),
                model="gpt-4o",
                finish_reason=FinishReason.STOP,
            )

        mock_provider = Mock()
        mock_provider.execute_query.side_effect = mock_execute
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.retryable is False
        assert result.reason is not None
        assert result.reason["reason"] == "context_length_exceeded"
        assert result.reason["failed_query_name"] == "q2"
        assert result.reason["discarded_successful_queries"] == 1


# ---------------------------------------------------------------------------
# Template rendering failure
# ---------------------------------------------------------------------------


class TestTemplateRendering:
    """Verify template rendering errors return error results."""

    def test_template_error_returns_error_result(self) -> None:
        transform, _ = _make_transform_with_mock_provider()

        # Row missing required 'text' field → template rendering fails
        row = _make_row({"other_field": "hello"})
        ctx = _make_ctx()

        result = transform._process_row(row, ctx)
        assert result.status == "error"
        assert result.reason is not None
        assert "template" in str(result.reason).lower()
