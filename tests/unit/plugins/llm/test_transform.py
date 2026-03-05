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

from elspeth.contracts.schema_contract import PipelineRow
from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.infrastructure.clients.llm import (
    ContentPolicyError,
    ContextLengthError,
    LLMClientError,
    NetworkError,
    RateLimitError,
    ServerError,
)
from elspeth.plugins.transforms.llm.provider import FinishReason, LLMQueryResult, UnrecognizedFinishReason
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
    from elspeth.plugins.transforms.llm.transform import LLMTransform

    transform = LLMTransform(config or _make_config())
    mock_provider = Mock()
    transform._provider = mock_provider
    return transform, mock_provider


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------


class TestProviderDispatch:
    """Verify correct provider creation based on provider field."""

    def test_unknown_provider_raises_with_valid_options(self) -> None:
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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

    def test_llm_transform_uses_process_row_not_process(self) -> None:
        """LLMTransform extends BatchTransformMixin — process() raises NotImplementedError."""
        from elspeth.plugins.infrastructure.batching import BatchTransformMixin
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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
            finish_reason=FinishReason.STOP,
        )

        row = _make_row()
        result = transform._process_row(row, _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        # Output row has a contract (propagated from input)
        assert result.row.contract is not None

    def test_contract_propagation_multi_query(self) -> None:
        """Multi-query mode propagates contract with OBSERVED fields from all queries."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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

    def test_content_filtered_single_query_returns_error(self) -> None:
        """Provider content filtering must not be recorded as success."""
        transform, mock_provider = _make_transform_with_mock_provider()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="provider fallback text",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.CONTENT_FILTER,
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.row is None
        assert result.reason is not None
        assert result.reason["reason"] == "content_filtered"
        assert result.reason["finish_reason"] == "content_filter"

    def test_tool_calls_finish_reason_returns_error(self) -> None:
        """TOOL_CALLS finish reason must not be treated as successful text output."""
        transform, mock_provider = _make_transform_with_mock_provider()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="some content alongside tool call",
            usage=TokenUsage.known(10, 20),
            model="gpt-4o",
            finish_reason=FinishReason.TOOL_CALLS,
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "unexpected_finish_reason"
        assert result.reason["finish_reason"] == "tool_calls"
        assert result.retryable is False

    def test_missing_finish_reason_returns_retryable_error(self) -> None:
        """Absent finish_reason (None) must not be treated as success."""
        transform, mock_provider = _make_transform_with_mock_provider()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="content with no finish_reason",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=None,
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "missing_finish_reason"
        assert result.retryable is True

    def test_unrecognized_finish_reason_returns_error(self) -> None:
        """Unknown finish reasons must fail closed, not pass through as success."""
        transform, mock_provider = _make_transform_with_mock_provider()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="filtered by new safety system",
            usage=TokenUsage.known(10, 15),
            model="gpt-4o",
            finish_reason=UnrecognizedFinishReason("safety_filter"),
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "unexpected_finish_reason"
        assert result.reason["finish_reason"] == "safety_filter"
        assert result.retryable is False

    def test_multi_query_unrecognized_finish_reason_returns_error(self) -> None:
        """Unknown finish reasons in multi-query mode must also fail closed."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {"input_fields": {"text_content": "text"}},
                "q2": {"input_fields": {"text_content": "text"}},
            },
        )
        transform = LLMTransform(config)

        call_count = [0]

        def mock_execute_query(messages, *, model, temperature, max_tokens, state_id, token_id, response_format=None):
            call_count[0] += 1
            if call_count[0] == 2:
                return LLMQueryResult(
                    content="blocked by moderation",
                    usage=TokenUsage.known(10, 15),
                    model="gpt-4o",
                    finish_reason=UnrecognizedFinishReason("moderation"),
                )
            return LLMQueryResult(
                content='{"result": "ok"}',
                usage=TokenUsage.known(10, 20),
                model="gpt-4o",
                finish_reason=FinishReason.STOP,
            )

        mock_provider = Mock()
        mock_provider.execute_query.side_effect = mock_execute_query
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "unexpected_finish_reason"
        assert result.reason["finish_reason"] == "moderation"
        assert result.reason["query_name"] == "q2"
        assert result.reason["query_index"] == 1


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
        from elspeth.plugins.transforms.llm.langfuse import NoOpLangfuseTracer
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(_make_config())
        assert isinstance(transform._tracer, NoOpLangfuseTracer)

    def test_tracer_is_active_when_langfuse_configured(self) -> None:
        """When Langfuse is configured and importable, ActiveLangfuseTracer is used."""
        from elspeth.plugins.transforms.llm.langfuse import ActiveLangfuseTracer
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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
# Multi-query partial failure
# ---------------------------------------------------------------------------


class TestMultiQueryPartialFailure:
    """Verify multi-query atomicity — partial failure discards all results."""

    def test_multi_query_partial_failure_discards_successful_results(self) -> None:
        """4 queries, query 3 fails → ALL results discarded, error has details."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform, MultiQueryStrategy

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

        def mock_execute_query(messages, *, model, temperature, max_tokens, state_id, token_id, response_format=None):
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

    def test_multi_query_content_filter_discards_successful_results(self) -> None:
        """A content-filtered query must fail the whole multi-query row."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {"input_fields": {"text_content": "text"}},
                "q2": {"input_fields": {"text_content": "text"}},
            },
        )
        transform = LLMTransform(config)

        call_count = [0]

        def mock_execute_query(messages, *, model, temperature, max_tokens, state_id, token_id, response_format=None):
            call_count[0] += 1
            if call_count[0] == 2:
                return LLMQueryResult(
                    content="provider fallback text",
                    usage=TokenUsage.known(10, 5),
                    model="gpt-4o",
                    finish_reason=FinishReason.CONTENT_FILTER,
                )
            return LLMQueryResult(
                content='{"result": "success_1"}',
                usage=TokenUsage.known(10, 5),
                model="gpt-4o",
                finish_reason=FinishReason.STOP,
            )

        mock_provider = Mock()
        mock_provider.execute_query.side_effect = mock_execute_query
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.row is None
        assert result.reason is not None
        assert result.reason["reason"] == "content_filtered"
        assert result.reason["query_name"] == "q2"
        assert result.reason["query_index"] == 1


# ---------------------------------------------------------------------------
# Multi-query JSON parsing and field extraction
# ---------------------------------------------------------------------------


class TestMultiQueryJSONExtraction:
    """Verify multi-query JSON parsing and field extraction when output_fields configured."""

    def test_per_query_template_override_inherits_lookup_context(self) -> None:
        """Per-query template overrides should retain shared lookup data."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        lookup = {"labels": {"base": "BASE", "q1": "OVERRIDE"}}
        config = _make_config(
            template="Base {{ lookup.labels.base }}: {{ row.text_content }}",
            lookup=lookup,
            queries={
                "q1": {
                    "input_fields": {"text_content": "text"},
                    "template": "Override {{ lookup.labels.q1 }}: {{ row.text_content }}",
                },
            },
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="override result",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        assert result.row["q1_llm_response"] == "override result"
        call_messages = mock_provider.execute_query.call_args.args[0]
        assert call_messages == [{"role": "user", "content": "Override OVERRIDE: hello"}]

    def test_per_query_template_override_preserves_lookup_audit_metadata(self) -> None:
        """Per-query template overrides should keep lookup provenance fields."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Base {{ lookup.labels.base }}: {{ row.text_content }}",
            lookup={"labels": {"base": "BASE", "q1": "OVERRIDE"}},
            lookup_source="prompts/lookups.yaml",
            queries={
                "q1": {
                    "input_fields": {"text_content": "text"},
                    "template": "Override {{ lookup.labels.q1 }}: {{ row.text_content }}",
                },
            },
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="override result",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        output = result.row.to_dict()
        assert output["q1_llm_response_lookup_hash"] is not None
        assert output["q1_llm_response_lookup_source"] == "prompts/lookups.yaml"

    def test_output_fields_extracts_typed_fields_from_json(self) -> None:
        """When output_fields is configured, JSON is parsed and fields extracted."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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

    def test_output_fields_missing_field_returns_error(self) -> None:
        """When a declared field is missing from LLM JSON response, return error."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "missing_output_field"
        assert result.reason["field"] == "missing_field"
        assert "score" in result.reason["available_fields"]

    def test_output_fields_json_parse_failure_returns_error(self) -> None:
        """When LLM returns invalid JSON and output_fields expects JSON, return error."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {"input_fields": {"text_content": "text"}},
                "q2": {"input_fields": {"text_content": "text"}},
            },
        )
        transform = LLMTransform(config)
        call_count = [0]

        def mock_execute(messages, *, model, temperature, max_tokens, state_id, token_id, response_format=None):
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


# ---------------------------------------------------------------------------
# Bug fix: NaN/Infinity rejection in multi-query JSON parsing
# ---------------------------------------------------------------------------


class TestMultiQueryNonFiniteRejection:
    """Bug #5: json.loads() without parse_constant accepts NaN/Infinity.

    Multi-query JSON parsing at transform.py:413 uses bare json.loads(content),
    which accepts Python's non-standard NaN, Infinity, -Infinity. These values
    break RFC 8785 canonical JSON hashing downstream and violate audit integrity.

    The correct pattern (used in validation.py:78 and openrouter.py:203) passes
    parse_constant=reject_nonfinite_constant to reject non-finite values at the
    Tier 3 boundary.
    """

    def _make_structured_query_transform(self) -> tuple[Any, Mock]:
        """Create a multi-query transform with output_fields (JSON parsing path)."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {
                    "input_fields": {"text_content": "text"},
                    "output_fields": [{"suffix": "score", "type": "number"}],
                },
            },
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        transform._provider = mock_provider
        return transform, mock_provider

    def test_nan_in_json_response_rejected(self) -> None:
        """LLM response containing NaN must be rejected, not silently accepted."""
        transform, mock_provider = self._make_structured_query_transform()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content='{"score": NaN}',
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "json_parse_failed"

    def test_infinity_in_json_response_rejected(self) -> None:
        """LLM response containing Infinity must be rejected."""
        transform, mock_provider = self._make_structured_query_transform()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content='{"score": Infinity}',
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "json_parse_failed"

    def test_negative_infinity_in_json_response_rejected(self) -> None:
        """LLM response containing -Infinity must be rejected."""
        transform, mock_provider = self._make_structured_query_transform()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content='{"score": -Infinity}',
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "json_parse_failed"

    def test_valid_json_still_accepted(self) -> None:
        """Finite values in JSON must still parse successfully (no regression)."""
        transform, mock_provider = self._make_structured_query_transform()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content='{"score": 3.14}',
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "success"
        assert result.row is not None
        assert result.row["q1_score"] == pytest.approx(3.14)


# ---------------------------------------------------------------------------
# Bug fix: Hardcoded limiter name
# ---------------------------------------------------------------------------


class TestLimiterDispatch:
    """Bug #1: on_start() always requests 'azure_openai' limiter.

    The consolidated transform hardcodes get_limiter("azure_openai") regardless
    of the configured provider. OpenRouter pipelines should get the 'openrouter'
    limiter with potentially different rate limit settings.
    """

    def test_azure_provider_gets_azure_openai_limiter(self) -> None:
        """Azure config should request the 'azure_openai' limiter."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(_make_config(provider="azure"))

        mock_registry = Mock()
        mock_registry.get_limiter.return_value = Mock()

        ctx = _make_ctx()
        ctx.landscape = Mock()
        ctx.rate_limit_registry = mock_registry
        ctx.telemetry_emit = lambda event: None

        transform.on_start(ctx)

        mock_registry.get_limiter.assert_called_once_with("azure_openai")

    def test_openrouter_provider_gets_openrouter_limiter(self) -> None:
        """OpenRouter config should request the 'openrouter' limiter, not 'azure_openai'."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(_make_config(provider="openrouter"))

        mock_registry = Mock()
        mock_registry.get_limiter.return_value = Mock()

        ctx = _make_ctx()
        ctx.landscape = Mock()
        ctx.rate_limit_registry = mock_registry
        ctx.telemetry_emit = lambda event: None

        transform.on_start(ctx)

        mock_registry.get_limiter.assert_called_once_with("openrouter")


# ---------------------------------------------------------------------------
# Bug fix: Multi-query declared_output_fields missing prefixed fields
# ---------------------------------------------------------------------------


class TestMultiQueryDeclaredOutputFields:
    """Bug #4: declared_output_fields only declares unprefixed single-query fields.

    Multi-query mode emits prefixed fields like 'quality_llm_response',
    'quality_score', etc. but these aren't declared in declared_output_fields,
    so TransformExecutor can't detect input/output name collisions.
    """

    def test_single_query_declares_base_output_fields(self) -> None:
        """Baseline: single-query mode declares unprefixed fields correctly."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(_make_config())
        # Should include response field and metadata
        assert "llm_response" in transform.declared_output_fields
        assert "llm_response_usage" in transform.declared_output_fields
        assert "llm_response_model" in transform.declared_output_fields

    def test_multi_query_declares_prefixed_content_fields(self) -> None:
        """Multi-query mode must declare query-prefixed content fields."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Classify: {{ row.text_content }}",
            queries={
                "quality": {"input_fields": {"text_content": "text"}},
                "relevance": {"input_fields": {"text_content": "text"}},
            },
        )
        transform = LLMTransform(config)

        # Must include prefixed content fields
        assert "quality_llm_response" in transform.declared_output_fields
        assert "relevance_llm_response" in transform.declared_output_fields

    def test_multi_query_declares_prefixed_metadata_fields(self) -> None:
        """Multi-query mode must declare query-prefixed metadata fields."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Classify: {{ row.text_content }}",
            queries={
                "quality": {"input_fields": {"text_content": "text"}},
            },
        )
        transform = LLMTransform(config)

        # Must include prefixed metadata (usage, model, audit fields)
        assert "quality_llm_response_usage" in transform.declared_output_fields
        assert "quality_llm_response_model" in transform.declared_output_fields
        assert "quality_llm_response_template_hash" in transform.declared_output_fields

    def test_multi_query_declares_extracted_output_fields(self) -> None:
        """When output_fields are configured, their prefixed names must be declared."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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

        # Extracted fields must be declared
        assert "quality_score" in transform.declared_output_fields
        assert "quality_label" in transform.declared_output_fields

    def test_multi_query_does_not_declare_unprefixed_single_query_fields(self) -> None:
        """Multi-query mode should NOT declare unprefixed base fields that it doesn't emit."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Classify: {{ row.text_content }}",
            queries={
                "quality": {"input_fields": {"text_content": "text"}},
            },
        )
        transform = LLMTransform(config)

        # Multi-query does NOT emit base "llm_response" — only "quality_llm_response"
        assert "llm_response" not in transform.declared_output_fields


# ---------------------------------------------------------------------------
# Regression: Multi-query _output_schema_config must use prefixed fields
# ---------------------------------------------------------------------------


class TestMultiQueryOutputSchemaConfig:
    """Regression for commit 4c7ca1b9: _output_schema_config must match emission.

    Before the fix, _output_schema_config was built unconditionally with
    unprefixed single-query fields (llm_response, llm_response_model, etc.)
    even when multi-query mode emits only prefixed fields (quality_llm_response,
    relevance_llm_response, etc.). This caused DAG contract propagation to
    advertise wrong field names, leading to false missing-field validation
    failures or incorrect contract metadata for downstream transforms.
    """

    def test_multi_query_guaranteed_fields_are_prefixed(self) -> None:
        """_output_schema_config.guaranteed_fields must contain query-prefixed names."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(
            _make_config(
                template="Classify: {{ row.text_content }}",
                queries={
                    "quality": {"input_fields": {"text_content": "text"}},
                    "relevance": {"input_fields": {"text_content": "text"}},
                },
            )
        )

        assert transform._output_schema_config.guaranteed_fields is not None
        guaranteed = set(transform._output_schema_config.guaranteed_fields)
        assert "quality_llm_response" in guaranteed
        assert "quality_llm_response_usage" in guaranteed
        assert "quality_llm_response_model" in guaranteed
        assert "relevance_llm_response" in guaranteed
        assert "relevance_llm_response_usage" in guaranteed
        assert "relevance_llm_response_model" in guaranteed

    def test_multi_query_audit_fields_are_prefixed(self) -> None:
        """_output_schema_config.audit_fields must contain query-prefixed audit names."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(
            _make_config(
                template="Classify: {{ row.text_content }}",
                queries={
                    "quality": {"input_fields": {"text_content": "text"}},
                },
            )
        )

        assert transform._output_schema_config.audit_fields is not None
        audit = set(transform._output_schema_config.audit_fields)
        assert "quality_llm_response_template_hash" in audit
        assert "quality_llm_response_variables_hash" in audit

    def test_multi_query_schema_config_excludes_unprefixed_fields(self) -> None:
        """Multi-query _output_schema_config must NOT contain unprefixed single-query fields.

        This is the exact regression guard: the old code built _output_schema_config
        once with unprefixed fields and never updated it for multi-query.
        """
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(
            _make_config(
                template="Classify: {{ row.text_content }}",
                queries={
                    "quality": {"input_fields": {"text_content": "text"}},
                },
            )
        )

        assert transform._output_schema_config.guaranteed_fields is not None
        assert transform._output_schema_config.audit_fields is not None
        guaranteed = set(transform._output_schema_config.guaranteed_fields)
        audit = set(transform._output_schema_config.audit_fields)
        all_fields = guaranteed | audit

        # Unprefixed single-query fields must NOT appear
        assert "llm_response" not in all_fields
        assert "llm_response_usage" not in all_fields
        assert "llm_response_model" not in all_fields
        assert "llm_response_template_hash" not in all_fields

    def test_multi_query_output_schema_has_prefixed_model_fields(self) -> None:
        """Pydantic output_schema model must include prefixed fields for explicit schemas."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(
            _make_config(
                template="Classify: {{ row.text_content }}",
                schema={"mode": "flexible", "fields": ["text: str"]},
                queries={
                    "quality": {"input_fields": {"text_content": "text"}},
                },
            )
        )

        model_fields = set(transform.output_schema.model_fields)
        assert "quality_llm_response" in model_fields
        assert "quality_llm_response_usage" in model_fields
        # Unprefixed must NOT appear
        assert "llm_response" not in model_fields

    def test_single_query_schema_config_uses_unprefixed_fields(self) -> None:
        """Baseline: single-query _output_schema_config uses unprefixed field names."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(_make_config())

        assert transform._output_schema_config.guaranteed_fields is not None
        guaranteed = set(transform._output_schema_config.guaranteed_fields)
        assert "llm_response" in guaranteed
        assert "llm_response_usage" in guaranteed
        assert "llm_response_model" in guaranteed

    def test_schema_config_consistent_with_declared_output_fields(self) -> None:
        """All guaranteed + audit fields in _output_schema_config must appear in declared_output_fields."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(
            _make_config(
                template="Classify: {{ row.text_content }}",
                queries={
                    "quality": {"input_fields": {"text_content": "text"}},
                    "relevance": {"input_fields": {"text_content": "text"}},
                },
            )
        )

        assert transform._output_schema_config.guaranteed_fields is not None
        assert transform._output_schema_config.audit_fields is not None
        schema_fields = set(transform._output_schema_config.guaranteed_fields) | set(transform._output_schema_config.audit_fields)
        declared = transform.declared_output_fields

        # Every field advertised in schema config must be in declared_output_fields
        missing = schema_fields - declared
        assert not missing, f"Fields in _output_schema_config but not declared_output_fields: {missing}"

    def test_multi_query_with_output_fields_in_schema_config(self) -> None:
        """Extracted output_fields (e.g., score, label) must appear in guaranteed_fields."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(
            _make_config(
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
        )

        assert transform._output_schema_config.guaranteed_fields is not None
        guaranteed = set(transform._output_schema_config.guaranteed_fields)
        assert "quality_score" in guaranteed
        assert "quality_label" in guaranteed

    def test_multi_query_output_schema_includes_extracted_output_fields(self) -> None:
        """Pydantic output_schema must include extracted output_fields for Phase 2 compatibility.

        Bug: _build_multi_query_output_schema only adds LLM metadata fields (usage,
        model, etc.) but omits structured output_fields (score, label). This means
        guaranteed_fields advertises fields the Pydantic schema doesn't have, causing
        Phase 2 type compatibility checks to fail for valid pipelines.
        """
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        transform = LLMTransform(
            _make_config(
                template="Evaluate: {{ row.text_content }}",
                schema={"mode": "flexible", "fields": ["text: str"]},
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
        )

        model_fields = set(transform.output_schema.model_fields)

        # Extracted output_fields must appear in the Pydantic model
        assert "quality_score" in model_fields, (
            f"Extracted field 'quality_score' missing from output_schema. Fields present: {sorted(model_fields)}"
        )
        assert "quality_label" in model_fields, (
            f"Extracted field 'quality_label' missing from output_schema. Fields present: {sorted(model_fields)}"
        )

        # LLM metadata fields must also still be present
        assert "quality_llm_response" in model_fields
        assert "quality_llm_response_usage" in model_fields


# ---------------------------------------------------------------------------
# Bug fix: response_format not passed to providers
# ---------------------------------------------------------------------------


class TestResponseFormatPassthrough:
    """Bug #3: Multi-query response_format not passed to provider.execute_query().

    QuerySpec supports response_format (STANDARD/STRUCTURED), but the provider
    call in MultiQueryStrategy doesn't pass it. This means the LLM is never
    asked to output JSON, making JSON parsing unreliable for structured queries.
    """

    def test_structured_response_format_passed_to_provider(self) -> None:
        """When response_format=structured, provider must receive response_format."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {
                    "input_fields": {"text_content": "text"},
                    "response_format": "structured",
                    "output_fields": [
                        {"suffix": "score", "type": "integer"},
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

        transform._process_row(_make_row(), _make_ctx())

        # Verify response_format was passed to provider
        call_kwargs = mock_provider.execute_query.call_args.kwargs
        assert "response_format" in call_kwargs
        assert call_kwargs["response_format"]["type"] == "json_schema"

    def test_standard_response_format_passes_json_object(self) -> None:
        """When response_format=standard with output_fields, use json_object mode."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {
                    "input_fields": {"text_content": "text"},
                    "response_format": "standard",
                    "output_fields": [
                        {"suffix": "score", "type": "integer"},
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

        transform._process_row(_make_row(), _make_ctx())

        call_kwargs = mock_provider.execute_query.call_args.kwargs
        assert "response_format" in call_kwargs
        assert call_kwargs["response_format"]["type"] == "json_object"

    def test_no_output_fields_omits_response_format(self) -> None:
        """When no output_fields configured, response_format should not be forced."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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

        transform._process_row(_make_row(), _make_ctx())

        call_kwargs = mock_provider.execute_query.call_args.kwargs
        # No response_format constraint when output_fields is None
        assert call_kwargs.get("response_format") is None


# ---------------------------------------------------------------------------
# Multi-query field type validation
# ---------------------------------------------------------------------------


class TestMultiQueryFieldTypeValidation:
    """Verify output field values are validated against declared types.

    LLM responses are Tier 3 (zero trust). In ResponseFormat.STANDARD mode,
    the API doesn't enforce schema — the LLM can return any JSON types.
    Field type validation is our defense-in-depth at the boundary.
    """

    def _make_typed_query_transform(self, output_fields: list[dict[str, Any]]) -> tuple[Any, Mock]:
        """Create a multi-query transform with specific output_fields config."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {
                    "input_fields": {"text_content": "text"},
                    "output_fields": output_fields,
                },
            },
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        transform._provider = mock_provider
        return transform, mock_provider

    def _execute_with_content(self, transform: Any, mock_provider: Mock, content: str) -> Any:
        """Execute _process_row with given LLM response content."""
        mock_provider.execute_query.return_value = LLMQueryResult(
            content=content,
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )
        return transform._process_row(_make_row(), _make_ctx())

    # -- Integer type validation --

    def test_integer_field_rejects_string(self) -> None:
        """String value for integer field must be rejected."""
        transform, provider = self._make_typed_query_transform([{"suffix": "score", "type": "integer"}])
        result = self._execute_with_content(transform, provider, '{"score": "high"}')
        assert result.status == "error"
        assert result.reason["reason"] == "field_type_mismatch"
        assert result.reason["field"] == "score"
        assert "expected integer" in result.reason["error"]

    def test_integer_field_rejects_boolean(self) -> None:
        """Boolean value for integer field must be rejected (bool is subclass of int)."""
        transform, provider = self._make_typed_query_transform([{"suffix": "count", "type": "integer"}])
        result = self._execute_with_content(transform, provider, '{"count": true}')
        assert result.status == "error"
        assert result.reason["reason"] == "field_type_mismatch"
        assert "boolean" in result.reason["error"]

    def test_integer_field_accepts_int(self) -> None:
        """Valid integer value must be accepted."""
        transform, provider = self._make_typed_query_transform([{"suffix": "score", "type": "integer"}])
        result = self._execute_with_content(transform, provider, '{"score": 42}')
        assert result.status == "success"
        assert result.row["q1_score"] == 42

    def test_integer_field_accepts_float_with_integer_value(self) -> None:
        """Float with integer value (e.g. 42.0) should be accepted as integer."""
        transform, provider = self._make_typed_query_transform([{"suffix": "score", "type": "integer"}])
        result = self._execute_with_content(transform, provider, '{"score": 42.0}')
        assert result.status == "success"

    # -- Number type validation --

    def test_number_field_rejects_string(self) -> None:
        """String value for number field must be rejected."""
        transform, provider = self._make_typed_query_transform([{"suffix": "score", "type": "number"}])
        result = self._execute_with_content(transform, provider, '{"score": "3.14"}')
        assert result.status == "error"
        assert result.reason["reason"] == "field_type_mismatch"

    def test_number_field_rejects_boolean(self) -> None:
        """Boolean value for number field must be rejected."""
        transform, provider = self._make_typed_query_transform([{"suffix": "score", "type": "number"}])
        result = self._execute_with_content(transform, provider, '{"score": false}')
        assert result.status == "error"
        assert result.reason["reason"] == "field_type_mismatch"

    def test_number_field_accepts_float(self) -> None:
        """Valid float must be accepted for number field."""
        transform, provider = self._make_typed_query_transform([{"suffix": "score", "type": "number"}])
        result = self._execute_with_content(transform, provider, '{"score": 3.14}')
        assert result.status == "success"
        assert result.row["q1_score"] == pytest.approx(3.14)

    def test_number_field_accepts_int(self) -> None:
        """Integer is valid for number field."""
        transform, provider = self._make_typed_query_transform([{"suffix": "score", "type": "number"}])
        result = self._execute_with_content(transform, provider, '{"score": 42}')
        assert result.status == "success"

    # -- String type validation --

    def test_string_field_rejects_integer(self) -> None:
        """Integer value for string field must be rejected."""
        transform, provider = self._make_typed_query_transform([{"suffix": "label", "type": "string"}])
        result = self._execute_with_content(transform, provider, '{"label": 42}')
        assert result.status == "error"
        assert result.reason["reason"] == "field_type_mismatch"

    # -- Boolean type validation --

    def test_boolean_field_rejects_integer(self) -> None:
        """Integer value for boolean field must be rejected."""
        transform, provider = self._make_typed_query_transform([{"suffix": "flag", "type": "boolean"}])
        result = self._execute_with_content(transform, provider, '{"flag": 1}')
        assert result.status == "error"
        assert result.reason["reason"] == "field_type_mismatch"

    def test_boolean_field_accepts_true(self) -> None:
        """Boolean true must be accepted."""
        transform, provider = self._make_typed_query_transform([{"suffix": "flag", "type": "boolean"}])
        result = self._execute_with_content(transform, provider, '{"flag": true}')
        assert result.status == "success"
        assert result.row["q1_flag"] is True

    # -- Enum type validation --

    def test_enum_field_rejects_invalid_value(self) -> None:
        """Enum value not in allowed list must be rejected."""
        transform, provider = self._make_typed_query_transform([{"suffix": "grade", "type": "enum", "values": ["A", "B", "C"]}])
        result = self._execute_with_content(transform, provider, '{"grade": "D"}')
        assert result.status == "error"
        assert result.reason["reason"] == "field_type_mismatch"
        assert "not in allowed values" in result.reason["error"]

    def test_enum_field_rejects_non_string(self) -> None:
        """Non-string value for enum field must be rejected."""
        transform, provider = self._make_typed_query_transform([{"suffix": "grade", "type": "enum", "values": ["A", "B"]}])
        result = self._execute_with_content(transform, provider, '{"grade": 1}')
        assert result.status == "error"
        assert result.reason["reason"] == "field_type_mismatch"

    def test_enum_field_accepts_valid_value(self) -> None:
        """Valid enum value must be accepted."""
        transform, provider = self._make_typed_query_transform([{"suffix": "grade", "type": "enum", "values": ["A", "B", "C"]}])
        result = self._execute_with_content(transform, provider, '{"grade": "B"}')
        assert result.status == "success"
        assert result.row["q1_grade"] == "B"

    # -- Error metadata --

    def test_field_type_error_includes_query_metadata(self) -> None:
        """Type mismatch error must include query name, index, and discarded count."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "first": {
                    "input_fields": {"text_content": "text"},
                    "output_fields": [{"suffix": "ok", "type": "string"}],
                },
                "second": {
                    "input_fields": {"text_content": "text"},
                    "output_fields": [{"suffix": "score", "type": "integer"}],
                },
            },
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        call_count = [0]

        def mock_execute(messages, *, model, temperature, max_tokens, state_id, token_id, response_format=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return LLMQueryResult(
                    content='{"ok": "good"}',
                    usage=TokenUsage.known(10, 5),
                    model="gpt-4o",
                    finish_reason=FinishReason.STOP,
                )
            return LLMQueryResult(
                content='{"score": "not_a_number"}',
                usage=TokenUsage.known(10, 5),
                model="gpt-4o",
                finish_reason=FinishReason.STOP,
            )

        mock_provider.execute_query.side_effect = mock_execute
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "field_type_mismatch"
        assert result.reason["query_name"] == "second"
        assert result.reason["query_index"] == 1
        assert result.reason["discarded_successful_queries"] == 1


# ---------------------------------------------------------------------------
# Multi-query execution mode: sequential vs parallel
# ---------------------------------------------------------------------------


class TestMultiQueryExecutionMode:
    """Verify multi-query strategy dispatches to sequential/parallel correctly."""

    def test_pool_size_1_uses_sequential(self) -> None:
        """pool_size=1 (default) runs queries sequentially — no parallel executor."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={"q1": {"input_fields": {"text_content": "text"}}},
            pool_size=1,
        )
        transform = LLMTransform(config)
        # Observable: no query executor created for sequential mode
        assert transform._query_executor is None

    def test_pool_size_gt_1_creates_executor(self) -> None:
        """pool_size > 1 creates a parallel executor for multi-query."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={"q1": {"input_fields": {"text_content": "text"}}},
            pool_size=4,
        )
        transform = LLMTransform(config)
        assert transform._query_executor is not None
        # Clean up
        transform._query_executor.shutdown(wait=True)

    def test_single_query_mode_still_creates_executor_for_batching(self) -> None:
        """Single-query mode with pool_size > 1 creates executor for BatchTransformMixin."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(pool_size=4)
        transform = LLMTransform(config)
        # pool_size > 1 creates executor even in single-query mode
        # (it's used by BatchTransformMixin, not query-level parallelism)
        assert transform._query_executor is not None
        transform._query_executor.shutdown(wait=True)


class TestMultiQuerySequentialRetryBehavior:
    """Verify sequential mode handles retryable errors correctly.

    Bug fix: retryable LLMClientErrors should be returned as error results
    (with retryable=True) instead of being re-raised as exceptions. Re-raising
    causes the engine to retry the entire row, wastefully re-executing
    successful queries.
    """

    def test_retryable_error_returns_error_result_not_raises(self) -> None:
        """Sequential mode catches retryable errors as TransformResult.error(retryable=True)."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {"input_fields": {"text_content": "text"}},
                "q2": {"input_fields": {"text_content": "text"}},
            },
            pool_size=1,
        )
        transform = LLMTransform(config)
        call_count = [0]

        def mock_execute(messages, *, model, temperature, max_tokens, state_id, token_id, response_format=None):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RateLimitError("Rate limited on q2")
            return LLMQueryResult(
                content="ok",
                usage=TokenUsage.known(10, 5),
                model="gpt-4o",
                finish_reason=FinishReason.STOP,
            )

        mock_provider = Mock()
        mock_provider.execute_query.side_effect = mock_execute
        transform._provider = mock_provider

        # Should NOT raise — should return TransformResult.error(retryable=True)
        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.retryable is True
        assert result.reason is not None
        assert result.reason["reason"] == "multi_query_failed"
        assert result.reason["failed_query_name"] == "q2"
        assert result.reason["discarded_successful_queries"] == 1

    def test_non_retryable_error_returns_error_result(self) -> None:
        """Non-retryable errors still return error TransformResult(retryable=False)."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={"q1": {"input_fields": {"text_content": "text"}}},
            pool_size=1,
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        mock_provider.execute_query.side_effect = ContentPolicyError("Content blocked")
        transform._provider = mock_provider

        result = transform._process_row(_make_row(), _make_ctx())
        assert result.status == "error"
        assert result.retryable is False


class TestMultiQueryParallelExecution:
    """Verify parallel execution via PooledExecutor."""

    def test_parallel_all_succeed(self) -> None:
        """All queries succeed in parallel — results merged correctly."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {"input_fields": {"text_content": "text"}},
                "q2": {"input_fields": {"text_content": "text"}},
                "q3": {"input_fields": {"text_content": "text"}},
            },
            pool_size=4,
        )
        transform = LLMTransform(config)
        mock_provider = Mock()
        mock_provider.execute_query.return_value = LLMQueryResult(
            content="response text",
            usage=TokenUsage.known(10, 5),
            model="gpt-4o",
            finish_reason=FinishReason.STOP,
        )
        transform._provider = mock_provider

        try:
            result = transform._process_row(_make_row(), _make_ctx())
            assert result.status == "success"
            assert result.row is not None
            output = result.row.to_dict()
            assert output["q1_llm_response"] == "response text"
            assert output["q2_llm_response"] == "response text"
            assert output["q3_llm_response"] == "response text"
            assert mock_provider.execute_query.call_count == 3
        finally:
            assert transform._query_executor is not None
            transform._query_executor.shutdown(wait=True)

    def test_parallel_one_fails_non_retryable(self) -> None:
        """One query fails non-retryable in parallel — row fails atomically."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {"input_fields": {"text_content": "text"}},
                "q2": {"input_fields": {"text_content": "text"}},
            },
            pool_size=4,
        )
        transform = LLMTransform(config)
        call_count = [0]

        def mock_execute(messages, *, model, temperature, max_tokens, state_id, token_id, response_format=None):
            call_count[0] += 1
            if call_count[0] == 2:
                raise ContentPolicyError("Content blocked for q2")
            return LLMQueryResult(
                content="ok",
                usage=TokenUsage.known(10, 5),
                model="gpt-4o",
                finish_reason=FinishReason.STOP,
            )

        mock_provider = Mock()
        mock_provider.execute_query.side_effect = mock_execute
        transform._provider = mock_provider

        try:
            result = transform._process_row(_make_row(), _make_ctx())
            assert result.status == "error"
            assert result.retryable is False
        finally:
            assert transform._query_executor is not None
            transform._query_executor.shutdown(wait=True)

    def test_parallel_with_structured_output(self) -> None:
        """Parallel execution with output_fields — JSON parsed and merged."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

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
                "relevance": {
                    "input_fields": {"text_content": "text"},
                    "output_fields": [
                        {"suffix": "score", "type": "integer"},
                    ],
                },
            },
            pool_size=4,
        )
        transform = LLMTransform(config)
        call_count = [0]

        def mock_execute(messages, *, model, temperature, max_tokens, state_id, token_id, response_format=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return LLMQueryResult(
                    content='{"score": 85, "label": "high"}',
                    usage=TokenUsage.known(10, 5),
                    model="gpt-4o",
                    finish_reason=FinishReason.STOP,
                )
            return LLMQueryResult(
                content='{"score": 72}',
                usage=TokenUsage.known(10, 5),
                model="gpt-4o",
                finish_reason=FinishReason.STOP,
            )

        mock_provider = Mock()
        mock_provider.execute_query.side_effect = mock_execute
        transform._provider = mock_provider

        try:
            result = transform._process_row(_make_row(), _make_ctx())
            assert result.status == "success"
            assert result.row is not None
            output = result.row.to_dict()
            assert output["quality_score"] == 85
            assert output["quality_label"] == "high"
            assert output["relevance_score"] == 72
        finally:
            assert transform._query_executor is not None
            transform._query_executor.shutdown(wait=True)

    def test_parallel_error_accumulation_fields(self) -> None:
        """Parallel failure includes failed_queries, discarded count, and total_count."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {"input_fields": {"text_content": "text"}},
                "q2": {"input_fields": {"text_content": "text"}},
                "q3": {"input_fields": {"text_content": "text"}},
            },
            pool_size=4,
        )
        transform = LLMTransform(config)
        call_count = [0]

        def mock_execute(messages, *, model, temperature, max_tokens, state_id, token_id, response_format=None):
            call_count[0] += 1
            # q2 (2nd call) fails non-retryable; q1 and q3 succeed
            if call_count[0] == 2:
                raise ContentPolicyError("Blocked content in q2")
            return LLMQueryResult(
                content="ok",
                usage=TokenUsage.known(10, 5),
                model="gpt-4o",
                finish_reason=FinishReason.STOP,
            )

        mock_provider = Mock()
        mock_provider.execute_query.side_effect = mock_execute
        transform._provider = mock_provider

        try:
            result = transform._process_row(_make_row(), _make_ctx())
            assert result.status == "error"
            assert result.retryable is False
            assert result.reason is not None
            # Verify the accumulated error fields
            assert "failed_query_name" in result.reason
            assert "failed_query_index" in result.reason
            assert "discarded_successful_queries" in result.reason
            assert "total_count" in result.reason
            assert result.reason["total_count"] == 3
            # failed_queries should list the names of failed queries
            assert "failed_queries" in result.reason
            assert isinstance(result.reason["failed_queries"], list)
        finally:
            assert transform._query_executor is not None
            transform._query_executor.shutdown(wait=True)

    def test_parallel_multiple_queries_fail(self) -> None:
        """When multiple queries fail in parallel, first failure's reason is used."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={
                "q1": {"input_fields": {"text_content": "text"}},
                "q2": {"input_fields": {"text_content": "text"}},
                "q3": {"input_fields": {"text_content": "text"}},
            },
            pool_size=4,
        )
        transform = LLMTransform(config)
        call_count = [0]

        def mock_execute(messages, *, model, temperature, max_tokens, state_id, token_id, response_format=None):
            call_count[0] += 1
            # q1 succeeds, q2 and q3 both fail
            if call_count[0] == 1:
                return LLMQueryResult(
                    content="ok",
                    usage=TokenUsage.known(10, 5),
                    model="gpt-4o",
                    finish_reason=FinishReason.STOP,
                )
            raise ContentPolicyError(f"Blocked call {call_count[0]}")

        mock_provider = Mock()
        mock_provider.execute_query.side_effect = mock_execute
        transform._provider = mock_provider

        try:
            result = transform._process_row(_make_row(), _make_ctx())
            assert result.status == "error"
            assert result.retryable is False
            assert result.reason is not None
            # failed_queries should contain all failed query names
            assert "failed_queries" in result.reason
            assert len(result.reason["failed_queries"]) == 2
            # discarded_successful_queries = total - failed
            assert result.reason["discarded_successful_queries"] == 1
            assert result.reason["total_count"] == 3
        finally:
            assert transform._query_executor is not None
            transform._query_executor.shutdown(wait=True)

    def test_close_shuts_down_executor(self) -> None:
        """LLMTransform.close() shuts down the query executor."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            template="Evaluate: {{ row.text_content }}",
            queries={"q1": {"input_fields": {"text_content": "text"}}},
            pool_size=4,
        )
        transform = LLMTransform(config)
        assert transform._query_executor is not None

        # Mock provider to avoid on_start dependency
        transform._provider = Mock()
        transform.close()
        # After close, executor should be shut down (no error = success)


# ---------------------------------------------------------------------------
# _configure_azure_monitor hardening
# ---------------------------------------------------------------------------


class TestConfigureAzureMonitor:
    """Tests for _configure_azure_monitor hardening."""

    @pytest.fixture(autouse=True)
    def _reset_azure_monitor(self) -> Any:
        """Reset module-level idempotency guard before and after each test.

        Using autouse prevents test contamination if a test fails mid-execution —
        the teardown (after yield) always runs regardless of test outcome.
        """
        from elspeth.plugins.transforms.llm.providers.azure import _reset_azure_monitor_state

        _reset_azure_monitor_state()
        yield
        _reset_azure_monitor_state()

    def test_raises_import_error_when_sdk_is_none(self) -> None:
        """_configure_azure_monitor raises ImportError when SDK is None (not installed)."""
        from elspeth.plugins.transforms.llm.providers.azure import _configure_azure_monitor
        from elspeth.plugins.transforms.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(connection_string="InstrumentationKey=test")
        with (
            patch(
                "elspeth.plugins.transforms.llm.providers.azure.configure_azure_monitor",
                None,  # Simulate missing SDK: configure_azure_monitor is None
            ),
            pytest.raises(ImportError, match="azure-monitor-opentelemetry is not installed"),
        ):
            _configure_azure_monitor(config)

    def test_real_sdk_typeerror_propagates(self) -> None:
        """Real TypeError from SDK (e.g., bad keyword arg) propagates as crash.

        After replacing the broad except TypeError with an explicit None check,
        a real TypeError from the SDK itself must NOT be caught — it indicates
        an incompatible SDK version or a bug in our call, both of which we
        need to know about immediately.
        """
        from elspeth.plugins.transforms.llm.providers.azure import _configure_azure_monitor
        from elspeth.plugins.transforms.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(connection_string="InstrumentationKey=test")

        def broken_sdk(**kwargs: Any) -> None:
            raise TypeError("unexpected keyword argument 'enable_live_metrics'")

        with (
            patch("elspeth.plugins.transforms.llm.providers.azure.configure_azure_monitor", broken_sdk),
            pytest.raises(TypeError, match="unexpected keyword argument"),
        ):
            _configure_azure_monitor(config)

    def test_returns_false_for_non_azure_ai_config(self) -> None:
        """_configure_azure_monitor returns False for non-AzureAITracingConfig.

        Directly tests the isinstance guard at the top of the function,
        rather than relying on indirect coverage through on_start().
        """
        from elspeth.plugins.transforms.llm.providers.azure import _configure_azure_monitor
        from elspeth.plugins.transforms.llm.tracing import TracingConfig

        config = TracingConfig(provider="none")
        result = _configure_azure_monitor(config)
        assert result is False

    def test_idempotency_second_call_returns_true_without_reconfiguring(self) -> None:
        """Second call to _configure_azure_monitor returns True without calling SDK again."""
        from elspeth.plugins.transforms.llm.providers.azure import _configure_azure_monitor
        from elspeth.plugins.transforms.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(connection_string="InstrumentationKey=test")
        with patch(
            "elspeth.plugins.transforms.llm.providers.azure.configure_azure_monitor",
        ) as mock_sdk:
            # First call — configures
            result1 = _configure_azure_monitor(config)
            assert result1 is True
            assert mock_sdk.call_count == 1

            # Second call — idempotent, skips SDK
            result2 = _configure_azure_monitor(config)
            assert result2 is True
            assert mock_sdk.call_count == 1  # NOT called again

    def test_idempotency_logs_warning_on_second_call(self) -> None:
        """Second call logs a warning about duplicate initialization."""
        from elspeth.plugins.transforms.llm.providers.azure import _configure_azure_monitor
        from elspeth.plugins.transforms.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(connection_string="InstrumentationKey=test")
        with (
            patch("elspeth.plugins.transforms.llm.providers.azure.configure_azure_monitor"),
            patch("elspeth.plugins.transforms.llm.providers.azure.logger") as mock_logger,
        ):
            _configure_azure_monitor(config)
            mock_logger.reset_mock()  # Clear warnings from first call (env-var fallback)

            _configure_azure_monitor(config)
            # Assert warning was emitted — don't match exact message prose
            mock_logger.warning.assert_called_once()

    def test_failed_first_call_allows_retry(self) -> None:
        """Failed first call (None SDK) does NOT set idempotency flag, allowing recovery.

        If the first call raises ImportError because the SDK is not installed,
        a subsequent call with a working SDK should succeed. The idempotency
        guard must only be set on success.
        """
        from elspeth.plugins.transforms.llm.providers.azure import _configure_azure_monitor
        from elspeth.plugins.transforms.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(connection_string="InstrumentationKey=test")

        # First call with None SDK — should raise ImportError
        with (
            patch("elspeth.plugins.transforms.llm.providers.azure.configure_azure_monitor", None),
            pytest.raises(ImportError, match="azure-monitor-opentelemetry is not installed"),
        ):
            _configure_azure_monitor(config)

        # Second call with working SDK — should succeed (not blocked by idempotency)
        with patch("elspeth.plugins.transforms.llm.providers.azure.configure_azure_monitor") as mock_sdk:
            result2 = _configure_azure_monitor(config)
            assert result2 is True
            mock_sdk.assert_called_once()


class TestAzureAITracingSetup:
    """Tests for Azure AI tracing integration in unified LLM transform."""

    def test_langfuse_factory_no_warning_for_azure_ai_config(self) -> None:
        """create_langfuse_tracer returns NoOp without warning for AzureAITracingConfig.

        Azure AI tracing is handled separately in on_start(), so the Langfuse
        factory should not warn about it being 'unrecognized'.
        """
        from elspeth.plugins.transforms.llm.langfuse import NoOpLangfuseTracer, create_langfuse_tracer
        from elspeth.plugins.transforms.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(connection_string="InstrumentationKey=test")
        with patch("elspeth.plugins.transforms.llm.langfuse.logger") as mock_logger:
            tracer = create_langfuse_tracer("test_transform", config)
            assert isinstance(tracer, NoOpLangfuseTracer)
            mock_logger.warning.assert_not_called()

    def test_langfuse_factory_returns_noop_for_provider_none(self) -> None:
        """create_langfuse_tracer returns NoOp for TracingConfig(provider='none').

        The documented 'tracing: {provider: none}' setting produces a base
        TracingConfig. The Langfuse factory must not crash on it — it's a
        valid no-op. Unknown providers are rejected by parse_tracing_config()
        at config parse time, so the factory only sees valid configs.
        """
        from elspeth.plugins.transforms.llm.langfuse import NoOpLangfuseTracer, create_langfuse_tracer
        from elspeth.plugins.transforms.llm.tracing import TracingConfig

        config = TracingConfig(provider="none")
        tracer = create_langfuse_tracer("test_transform", config)
        assert isinstance(tracer, NoOpLangfuseTracer)

    def test_azure_ai_tracing_rejected_for_openrouter_provider(self) -> None:
        """azure_ai tracing with openrouter provider raises ValueError at init.

        Azure Monitor auto-instruments the OpenAI SDK. OpenRouter uses httpx
        directly, so Azure AI tracing would silently do nothing.
        """
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            provider="openrouter",
            model="openai/gpt-4o",
            api_key="test-key",
            tracing={"provider": "azure_ai", "connection_string": "InstrumentationKey=test"},
        )
        with pytest.raises(ValueError, match=r"azure_ai tracing.*azure provider"):
            LLMTransform(config)

    def test_azure_ai_tracing_accepted_for_azure_provider(self) -> None:
        """azure_ai tracing with azure provider does not raise."""
        from elspeth.plugins.transforms.llm.tracing import AzureAITracingConfig
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            provider="azure",
            tracing={"provider": "azure_ai", "connection_string": "InstrumentationKey=test"},
        )
        # Should not raise
        transform = LLMTransform(config)
        assert transform._tracing_config is not None
        assert isinstance(transform._tracing_config, AzureAITracingConfig)


def _make_lifecycle_ctx() -> Mock:
    """Create a mock LifecycleContext for on_start() tests."""
    ctx = _make_ctx()
    ctx.landscape = Mock()
    ctx.rate_limit_registry = None
    ctx.telemetry_emit = Mock()
    ctx.node_id = "node-1"
    ctx.payload_store = None
    ctx.concurrency_config = None
    return ctx


class TestAzureAITracingOnStart:
    """Tests for _configure_azure_monitor() wiring in on_start()."""

    def test_on_start_calls_configure_azure_monitor(self) -> None:
        """on_start() calls _configure_azure_monitor for AzureAITracingConfig.

        Also verifies success-path logging: logger.info is called with
        "Azure AI tracing initialized" and the content_recording value.
        """
        from elspeth.plugins.transforms.llm.tracing import AzureAITracingConfig
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            provider="azure",
            tracing={
                "provider": "azure_ai",
                "connection_string": "InstrumentationKey=test",
                "enable_content_recording": True,
            },
        )
        transform = LLMTransform(config)
        ctx = _make_lifecycle_ctx()

        with (
            patch(
                "elspeth.plugins.transforms.llm.transform._configure_azure_monitor",
                return_value=True,
            ) as mock_configure,
            patch("elspeth.plugins.transforms.llm.transform.logger") as mock_logger,
        ):
            transform.on_start(ctx)

            mock_configure.assert_called_once()
            call_arg = mock_configure.call_args.args[0]
            assert isinstance(call_arg, AzureAITracingConfig)
            assert call_arg.connection_string == "InstrumentationKey=test"

            # Verify success-path logging includes content_recording value
            mock_logger.info.assert_any_call(
                "Azure AI tracing initialized",
                provider="azure_ai",
                content_recording=True,
            )

    def test_on_start_propagates_import_error_from_configure(self) -> None:
        """on_start() lets ImportError propagate when _configure_azure_monitor fails."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            provider="azure",
            tracing={"provider": "azure_ai", "connection_string": "InstrumentationKey=test"},
        )
        transform = LLMTransform(config)
        ctx = _make_lifecycle_ctx()

        with (
            patch(
                "elspeth.plugins.transforms.llm.transform._configure_azure_monitor",
                side_effect=ImportError("azure-monitor-opentelemetry is not installed"),
            ),
            pytest.raises(ImportError, match="azure-monitor-opentelemetry is not installed"),
        ):
            transform.on_start(ctx)

    def test_on_start_skips_azure_monitor_for_langfuse(self) -> None:
        """on_start() does NOT call _configure_azure_monitor for Langfuse tracing."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(
            provider="azure",
            tracing={"provider": "langfuse", "public_key": "pk", "secret_key": "sk"},
        )
        # Langfuse client creation will fail (no real server), but we mock the tracer
        with patch("elspeth.plugins.transforms.llm.transform.create_langfuse_tracer"):
            transform = LLMTransform(config)

        ctx = _make_lifecycle_ctx()
        with patch(
            "elspeth.plugins.transforms.llm.transform._configure_azure_monitor",
        ) as mock_configure:
            transform.on_start(ctx)
            mock_configure.assert_not_called()

    def test_on_start_skips_azure_monitor_when_no_tracing(self) -> None:
        """on_start() does NOT call _configure_azure_monitor when tracing is None."""
        from elspeth.plugins.transforms.llm.transform import LLMTransform

        config = _make_config(provider="azure")
        transform = LLMTransform(config)
        ctx = _make_lifecycle_ctx()

        with patch(
            "elspeth.plugins.transforms.llm.transform._configure_azure_monitor",
        ) as mock_configure:
            transform.on_start(ctx)
            mock_configure.assert_not_called()
