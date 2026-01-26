"""Tests for OpenRouter Multi-Query LLM transform."""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest

from elspeth.contracts import Determinism
from elspeth.plugins.config_base import PluginConfigError
from elspeth.plugins.context import PluginContext
from elspeth.plugins.llm.openrouter_multi_query import OpenRouterMultiQueryLLMTransform

# Common schema config
DYNAMIC_SCHEMA = {"fields": "dynamic"}


def make_config(**overrides: Any) -> dict[str, Any]:
    """Create valid config with optional overrides."""
    config = {
        "model": "anthropic/claude-3-opus",
        "api_key": "test-key",
        "template": "Input: {{ row.input_1 }}\nCriterion: {{ row.criterion.name }}",
        "system_prompt": "You are an assessment AI. Respond in JSON.",
        "case_studies": [
            {"name": "cs1", "input_fields": ["cs1_bg", "cs1_sym", "cs1_hist"]},
            {"name": "cs2", "input_fields": ["cs2_bg", "cs2_sym", "cs2_hist"]},
        ],
        "criteria": [
            {"name": "diagnosis", "code": "DIAG"},
            {"name": "treatment", "code": "TREAT"},
        ],
        "response_format": "json",
        "output_mapping": {"score": "score", "rationale": "rationale"},
        "schema": DYNAMIC_SCHEMA,
        "pool_size": 4,
    }
    config.update(overrides)
    return config


def make_openrouter_response(content: dict[str, Any] | str) -> dict[str, Any]:
    """Create an OpenRouter API response structure."""
    if isinstance(content, dict):
        content_str = json.dumps(content)
    else:
        content_str = content

    return {
        "choices": [
            {
                "message": {
                    "content": content_str,
                    "role": "assistant",
                }
            }
        ],
        "model": "anthropic/claude-3-opus",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }


@contextmanager
def mock_openrouter_http_responses(
    responses: list[dict[str, Any]],
) -> Generator[Mock, None, None]:
    """Mock HTTP client to return sequence of JSON responses."""
    call_count = 0

    def make_response(*args: Any, **kwargs: Any) -> Mock:
        nonlocal call_count
        response_data = responses[call_count % len(responses)]
        call_count += 1

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = response_data
        mock_response.text = json.dumps(response_data)
        mock_response.raise_for_status = Mock()
        mock_response.content = b""
        return mock_response

    with patch("httpx.Client") as mock_client_class:
        mock_client = Mock()
        mock_client.post.side_effect = make_response
        mock_client_class.return_value.__enter__ = Mock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = Mock(return_value=None)
        yield mock_client


def make_plugin_context(state_id: str = "state-123") -> PluginContext:
    """Create a PluginContext with mocked landscape."""
    mock_landscape = Mock()
    mock_landscape.record_external_call = Mock()
    mock_landscape.record_call = Mock()
    return PluginContext(
        run_id="run-123",
        landscape=mock_landscape,
        state_id=state_id,
        config={},
    )


class TestOpenRouterMultiQueryLLMTransformInit:
    """Tests for transform initialization."""

    def test_transform_has_correct_name(self) -> None:
        """Transform registers with correct plugin name."""
        transform = OpenRouterMultiQueryLLMTransform(make_config())
        assert transform.name == "openrouter_multi_query_llm"

    def test_transform_is_non_deterministic(self) -> None:
        """LLM transforms are non-deterministic."""
        transform = OpenRouterMultiQueryLLMTransform(make_config())
        assert transform.determinism == Determinism.NON_DETERMINISTIC

    def test_transform_is_batch_aware(self) -> None:
        """Transform supports batch aggregation."""
        transform = OpenRouterMultiQueryLLMTransform(make_config())
        assert transform.is_batch_aware is True

    def test_transform_expands_queries_on_init(self) -> None:
        """Transform pre-computes query specs on initialization."""
        transform = OpenRouterMultiQueryLLMTransform(make_config())
        # 2 case studies x 2 criteria = 4 queries
        assert len(transform._query_specs) == 4

    def test_transform_requires_case_studies(self) -> None:
        """Transform requires case_studies in config."""
        config = make_config()
        del config["case_studies"]
        with pytest.raises(PluginConfigError):
            OpenRouterMultiQueryLLMTransform(config)

    def test_transform_requires_criteria(self) -> None:
        """Transform requires criteria in config."""
        config = make_config()
        del config["criteria"]
        with pytest.raises(PluginConfigError):
            OpenRouterMultiQueryLLMTransform(config)

    def test_transform_requires_output_mapping(self) -> None:
        """Transform requires output_mapping in config."""
        config = make_config()
        del config["output_mapping"]
        with pytest.raises(PluginConfigError):
            OpenRouterMultiQueryLLMTransform(config)

    def test_transform_requires_non_empty_output_mapping(self) -> None:
        """Transform requires non-empty output_mapping."""
        config = make_config(output_mapping={})
        with pytest.raises(PluginConfigError):
            OpenRouterMultiQueryLLMTransform(config)


class TestSingleQueryProcessing:
    """Tests for _process_single_query method."""

    def test_process_single_query_renders_template(self) -> None:
        """Single query renders template with input fields and criterion."""
        responses = [make_openrouter_response({"score": 85, "rationale": "Good diagnosis"})]

        with mock_openrouter_http_responses(responses) as mock_client:
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            # Call on_start to set up the recorder
            transform.on_start(ctx)

            row = {
                "cs1_bg": "45yo male",
                "cs1_sym": "chest pain",
                "cs1_hist": "family history",
            }
            spec = transform._query_specs[0]  # cs1_diagnosis

            assert ctx.state_id is not None
            transform._process_single_query(row, spec, ctx.state_id)

            # Check HTTP was called
            assert mock_client.post.call_count == 1
            call_args = mock_client.post.call_args

            # Verify JSON body contains correct model and messages
            request_body = call_args.kwargs.get("json") or call_args[1].get("json")
            assert request_body["model"] == "anthropic/claude-3-opus"
            messages = request_body["messages"]
            user_message = messages[-1]["content"]

            assert "45yo male" in user_message
            assert "diagnosis" in user_message.lower()

    def test_process_single_query_parses_json_response(self) -> None:
        """Single query parses JSON and returns mapped fields."""
        responses = [make_openrouter_response({"score": 85, "rationale": "Excellent assessment"})]

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]  # cs1_diagnosis

            assert ctx.state_id is not None
            result = transform._process_single_query(row, spec, ctx.state_id)

            assert result.status == "success"
            assert result.row is not None
            # Output fields use prefix from spec
            assert result.row["cs1_diagnosis_score"] == 85
            assert result.row["cs1_diagnosis_rationale"] == "Excellent assessment"

    def test_process_single_query_handles_invalid_json(self) -> None:
        """Single query returns error on invalid JSON response from LLM content."""
        # LLM returns valid HTTP JSON but content is not JSON
        responses = [make_openrouter_response("not json")]

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            assert ctx.state_id is not None
            result = transform._process_single_query(row, spec, ctx.state_id)

            assert result.status == "error"
            assert result.reason is not None
            assert "json" in result.reason["reason"].lower()

    def test_process_single_query_raises_capacity_error_on_rate_limit(self) -> None:
        """Rate limit errors (HTTP 429) are converted to CapacityError for pooled retry."""
        from elspeth.plugins.pooling import CapacityError

        # Mock HTTP client to return 429
        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = 429
            mock_response.headers = {"content-type": "application/json"}
            mock_response.content = b""
            mock_response.text = ""
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Rate limit exceeded",
                request=Mock(),
                response=mock_response,
            )
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__enter__ = Mock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = Mock(return_value=None)

            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            assert ctx.state_id is not None
            with pytest.raises(CapacityError) as exc_info:
                transform._process_single_query(row, spec, ctx.state_id)

            assert exc_info.value.status_code == 429

    def test_process_single_query_raises_capacity_error_on_503(self) -> None:
        """Service unavailable (HTTP 503) raises CapacityError for pooled retry."""
        from elspeth.plugins.pooling import CapacityError

        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = 503
            mock_response.headers = {"content-type": "application/json"}
            mock_response.content = b""
            mock_response.text = ""
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Service unavailable",
                request=Mock(),
                response=mock_response,
            )
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__enter__ = Mock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = Mock(return_value=None)

            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            assert ctx.state_id is not None
            with pytest.raises(CapacityError) as exc_info:
                transform._process_single_query(row, spec, ctx.state_id)

            assert exc_info.value.status_code == 503

    def test_process_single_query_handles_template_error(self) -> None:
        """Template rendering errors return error result with details."""
        from elspeth.plugins.llm.templates import TemplateError

        responses = [make_openrouter_response({"score": 85, "rationale": "ok"})]

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            # Mock template to raise error
            with patch.object(transform._template, "render_with_metadata") as mock_render:
                mock_render.side_effect = TemplateError("Undefined variable 'missing'")

                assert ctx.state_id is not None
                result = transform._process_single_query(row, spec, ctx.state_id)

                assert result.status == "error"
                assert result.reason is not None
                assert result.reason["reason"] == "template_rendering_failed"
                assert "missing" in result.reason["error"]

    def test_get_http_client_requires_recorder(self) -> None:
        """_get_http_client raises RuntimeError if recorder not set via on_start."""
        transform = OpenRouterMultiQueryLLMTransform(make_config())
        # Don't call on_start - recorder will be None

        with pytest.raises(RuntimeError) as exc_info:
            transform._get_http_client("state-123")

        assert "recorder" in str(exc_info.value).lower()

    def test_process_single_query_strips_markdown_code_blocks(self) -> None:
        """LLM responses wrapped in markdown code blocks are handled correctly."""
        # LLM returns JSON wrapped in ```json ... ```
        content_with_fence = '```json\n{"score": 90, "rationale": "Great"}\n```'
        responses = [make_openrouter_response(content_with_fence)]

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            assert ctx.state_id is not None
            result = transform._process_single_query(row, spec, ctx.state_id)

            assert result.status == "success"
            assert result.row is not None
            assert result.row["cs1_diagnosis_score"] == 90
            assert result.row["cs1_diagnosis_rationale"] == "Great"

    def test_process_single_query_validates_json_is_dict(self) -> None:
        """LLM JSON response must be an object, not array or primitive."""
        # Valid JSON but not an object
        responses = [make_openrouter_response("[1, 2, 3]")]

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            assert ctx.state_id is not None
            result = transform._process_single_query(row, spec, ctx.state_id)

            assert result.status == "error"
            assert result.reason is not None
            assert result.reason["reason"] == "invalid_json_type"
            assert result.reason["expected"] == "object"
            assert result.reason["actual"] == "list"


class TestRowProcessing:
    """Tests for full row processing (all queries)."""

    def test_process_row_executes_all_queries(self) -> None:
        """Process executes all (case_study x criterion) queries."""
        # 2 case studies x 2 criteria = 4 queries
        responses = [
            make_openrouter_response({"score": 85, "rationale": "CS1 diagnosis"}),
            make_openrouter_response({"score": 90, "rationale": "CS1 treatment"}),
            make_openrouter_response({"score": 75, "rationale": "CS2 diagnosis"}),
            make_openrouter_response({"score": 80, "rationale": "CS2 treatment"}),
        ]

        with mock_openrouter_http_responses(responses) as mock_client:
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            transform.on_start(make_plugin_context())
            ctx = make_plugin_context()

            row = {
                "cs1_bg": "case1 bg",
                "cs1_sym": "case1 sym",
                "cs1_hist": "case1 hist",
                "cs2_bg": "case2 bg",
                "cs2_sym": "case2 sym",
                "cs2_hist": "case2 hist",
            }

            result = transform.process(row, ctx)

            assert result.status == "success"
            assert mock_client.post.call_count == 4

    def test_process_row_merges_all_results(self) -> None:
        """All query results are merged into single output row."""
        responses = [
            make_openrouter_response({"score": 85, "rationale": "R1"}),
            make_openrouter_response({"score": 90, "rationale": "R2"}),
            make_openrouter_response({"score": 75, "rationale": "R3"}),
            make_openrouter_response({"score": 80, "rationale": "R4"}),
        ]

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            transform.on_start(make_plugin_context())
            ctx = make_plugin_context()

            row = {
                "cs1_bg": "bg1",
                "cs1_sym": "sym1",
                "cs1_hist": "hist1",
                "cs2_bg": "bg2",
                "cs2_sym": "sym2",
                "cs2_hist": "hist2",
                "original_field": "preserved",
            }

            result = transform.process(row, ctx)

            assert result.status == "success"
            assert result.row is not None
            output = result.row

            # Original fields preserved
            assert output["original_field"] == "preserved"

            # All 4 queries produced output (2 fields each = 8 assessment fields)
            assert "cs1_diagnosis_score" in output
            assert "cs1_diagnosis_rationale" in output
            assert "cs1_treatment_score" in output
            assert "cs2_diagnosis_score" in output
            assert "cs2_treatment_score" in output

    def test_process_row_fails_if_any_query_fails(self) -> None:
        """All-or-nothing: if any query fails, entire row fails."""
        # First 3 succeed, 4th returns invalid JSON
        call_count = [0]

        def make_response(*args: Any, **kwargs: Any) -> Mock:
            call_count[0] += 1
            if call_count[0] == 4:
                content = "not valid json"
            else:
                content = json.dumps({"score": 85, "rationale": "ok"})

            response_data = {
                "choices": [{"message": {"content": content, "role": "assistant"}}],
                "model": "anthropic/claude-3-opus",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.json.return_value = response_data
            mock_response.text = json.dumps(response_data)
            mock_response.content = b""
            mock_response.raise_for_status = Mock()
            return mock_response

        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_client.post.side_effect = make_response
            mock_client_class.return_value.__enter__ = Mock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = Mock(return_value=None)

            transform = OpenRouterMultiQueryLLMTransform(make_config())
            transform.on_start(make_plugin_context())
            ctx = make_plugin_context()

            row = {
                "cs1_bg": "bg",
                "cs1_sym": "sym",
                "cs1_hist": "hist",
                "cs2_bg": "bg",
                "cs2_sym": "sym",
                "cs2_hist": "hist",
            }

            result = transform.process(row, ctx)

            # Entire row fails
            assert result.status == "error"
            assert result.reason is not None
            assert "query_failed" in result.reason["reason"]

    def test_process_row_includes_metadata_in_output(self) -> None:
        """Each query result includes audit metadata (usage, model, template_hash)."""
        responses = [make_openrouter_response({"score": 85, "rationale": "Good"})]

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            transform.on_start(make_plugin_context())
            ctx = make_plugin_context()

            row = {"cs1_bg": "bg", "cs1_sym": "sym", "cs1_hist": "hist"}
            spec = transform._query_specs[0]

            assert ctx.state_id is not None
            result = transform._process_single_query(row, spec, ctx.state_id)

            assert result.status == "success"
            assert result.row is not None
            output = result.row

            # Metadata fields present
            assert "cs1_diagnosis_usage" in output
            assert "cs1_diagnosis_model" in output
            assert "cs1_diagnosis_template_hash" in output
            assert "cs1_diagnosis_variables_hash" in output


class TestBatchProcessing:
    """Tests for batch processing (aggregation mode)."""

    def test_process_batch_handles_list_input(self) -> None:
        """Process accepts list of rows for batch aggregation."""
        # 2 rows x 4 queries each = 8 total HTTP calls
        responses = [make_openrouter_response({"score": i, "rationale": f"R{i}"}) for i in range(8)]

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            transform.on_start(make_plugin_context())
            ctx = make_plugin_context()

            rows = [
                {
                    "cs1_bg": "r1",
                    "cs1_sym": "r1",
                    "cs1_hist": "r1",
                    "cs2_bg": "r1",
                    "cs2_sym": "r1",
                    "cs2_hist": "r1",
                },
                {
                    "cs1_bg": "r2",
                    "cs1_sym": "r2",
                    "cs1_hist": "r2",
                    "cs2_bg": "r2",
                    "cs2_sym": "r2",
                    "cs2_hist": "r2",
                },
            ]

            result = transform.process(rows, ctx)

            assert result.status == "success"
            assert result.is_multi_row
            assert result.rows is not None
            assert len(result.rows) == 2

    def test_process_batch_preserves_row_independence(self) -> None:
        """Each row in batch is processed independently - row 1 succeeds, row 2 fails."""
        # Test that first row succeeds even when second row fails
        # Use pool_size=1 for predictable sequential order
        # Row 1's 4 queries succeed, Row 2's 4th query returns invalid JSON
        # Result should have 2 rows: row 1 with output fields, row 2 with _error marker
        call_count = [0]

        def make_response(*args: Any, **kwargs: Any) -> Mock:
            call_count[0] += 1
            # First 4 calls (row 1) succeed, 5-7 (row 2) succeed, 8th (row 2) fails
            if call_count[0] == 8:
                content = "not valid json"
            else:
                content = json.dumps({"score": call_count[0], "rationale": f"R{call_count[0]}"})

            response_data = {
                "choices": [{"message": {"content": content, "role": "assistant"}}],
                "model": "anthropic/claude-3-opus",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.json.return_value = response_data
            mock_response.text = json.dumps(response_data)
            mock_response.content = b""
            mock_response.raise_for_status = Mock()
            return mock_response

        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_client.post.side_effect = make_response
            mock_client_class.return_value.__enter__ = Mock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = Mock(return_value=None)

            # Use pool_size=1 for sequential execution within each row
            transform = OpenRouterMultiQueryLLMTransform(make_config(pool_size=1))
            transform.on_start(make_plugin_context())
            ctx = make_plugin_context()

            rows = [
                {
                    "cs1_bg": "r1_bg",
                    "cs1_sym": "r1_sym",
                    "cs1_hist": "r1_hist",
                    "cs2_bg": "r1_bg",
                    "cs2_sym": "r1_sym",
                    "cs2_hist": "r1_hist",
                },
                {
                    "cs1_bg": "r2_bg",
                    "cs1_sym": "r2_sym",
                    "cs1_hist": "r2_hist",
                    "cs2_bg": "r2_bg",
                    "cs2_sym": "r2_sym",
                    "cs2_hist": "r2_hist",
                },
            ]

            result = transform.process(rows, ctx)

            # Batch succeeds with partial results
            assert result.status == "success"
            assert result.is_multi_row
            assert result.rows is not None
            assert len(result.rows) == 2

            # Row 1 should have output fields (succeeded)
            assert "cs1_diagnosis_score" in result.rows[0]
            assert "cs1_treatment_score" in result.rows[0]

            # Row 2 should have error marker (failed)
            assert "_error" in result.rows[1]

    def test_process_batch_empty_list_returns_empty_result(self) -> None:
        """Empty batch returns success with empty indicator."""
        responses = [make_openrouter_response({"score": 1, "rationale": "R"})]

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            transform.on_start(make_plugin_context())
            ctx = make_plugin_context()

            result = transform.process([], ctx)

            assert result.status == "success"
            assert result.row is not None
            assert result.row["batch_empty"] is True
            assert result.row["row_count"] == 0

    def test_process_batch_uses_shared_state_id(self) -> None:
        """Batch processing uses shared state_id (FK constraint fix).

        All queries share ctx.state_id to satisfy FK constraint:
        - calls.state_id must reference existing node_states.state_id
        - Uniqueness comes from call_index allocated by recorder
        - Single HTTP client cached per batch (not per query)

        This prevents FK violations and memory leaks from per-query clients.
        """
        # 2 rows x 4 queries = 8 responses needed
        responses = [make_openrouter_response({"score": i, "rationale": f"R{i}"}) for i in range(8)]
        created_state_ids: list[str] = []

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            transform.on_start(make_plugin_context())

            # Patch _get_http_client to track state_ids
            original_get_client = transform._get_http_client

            def tracking_get_client(state_id: str) -> Any:
                created_state_ids.append(state_id)
                return original_get_client(state_id)

            transform._get_http_client = tracking_get_client  # type: ignore[method-assign]

            ctx = make_plugin_context(state_id="batch-001")

            rows = [
                {
                    "cs1_bg": "r1",
                    "cs1_sym": "r1",
                    "cs1_hist": "r1",
                    "cs2_bg": "r1",
                    "cs2_sym": "r1",
                    "cs2_hist": "r1",
                },
                {
                    "cs1_bg": "r2",
                    "cs1_sym": "r2",
                    "cs1_hist": "r2",
                    "cs2_bg": "r2",
                    "cs2_sym": "r2",
                    "cs2_hist": "r2",
                },
            ]

            transform.process(rows, ctx)

            # All queries use shared state_id (FK constraint)
            assert len(created_state_ids) > 0, "Should have tracked state_ids"

            # Verify ALL calls use the shared state_id from context
            unique_state_ids = set(created_state_ids)
            assert len(unique_state_ids) == 1, f"Expected all calls to use shared state_id, but got multiple: {unique_state_ids}"
            assert unique_state_ids == {"batch-001"}, f"Expected shared state_id 'batch-001', got {unique_state_ids}"

            # Verify NO synthetic per-query state_ids were created
            for state_id in created_state_ids:
                assert "_q" not in state_id, f"Found synthetic per-query state_id: {state_id}"
                assert "_r" not in state_id, f"Found synthetic per-row state_id: {state_id}"

    def test_process_batch_cleans_up_shared_client(self) -> None:
        """Batch client is cleaned up after processing all rows.

        Single client for entire batch, keyed by ctx.state_id,
        cleaned up after batch completion.
        """
        responses = [make_openrouter_response({"score": i, "rationale": f"R{i}"}) for i in range(8)]

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            transform.on_start(make_plugin_context())
            ctx = make_plugin_context(state_id="batch-002")

            rows = [
                {
                    "cs1_bg": "r1",
                    "cs1_sym": "r1",
                    "cs1_hist": "r1",
                    "cs2_bg": "r1",
                    "cs2_sym": "r1",
                    "cs2_hist": "r1",
                },
                {
                    "cs1_bg": "r2",
                    "cs1_sym": "r2",
                    "cs1_hist": "r2",
                    "cs2_bg": "r2",
                    "cs2_sym": "r2",
                    "cs2_hist": "r2",
                },
            ]

            transform.process(rows, ctx)

            # After processing, shared batch client cleaned up
            assert "batch-002" not in transform._http_clients, "Batch client should be cleaned up after completion"

            # Verify NO per-row synthetic state_ids in cache
            for client_key in transform._http_clients:
                assert "_row" not in client_key, f"Found synthetic per-row client key: {client_key}"

    def test_sequential_mode_cleans_up_batch_client(self) -> None:
        """Sequential mode (no pool_size) also cleans up batch client after processing.

        Ensures _http_clients doesn't accumulate entries across batches.
        """
        responses = [make_openrouter_response({"score": i, "rationale": f"R{i}"}) for i in range(8)]

        # Create config WITHOUT pool_size - forces sequential mode
        config = make_config()
        del config["pool_size"]

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(config)
            transform.on_start(make_plugin_context())

            # Verify no executor created (sequential mode)
            assert transform._executor is None, "Sequential mode should not have executor"

            # Process first batch
            ctx1 = make_plugin_context(state_id="batch-seq-001")
            rows1 = [
                {
                    "cs1_bg": "r1",
                    "cs1_sym": "r1",
                    "cs1_hist": "r1",
                    "cs2_bg": "r1",
                    "cs2_sym": "r1",
                    "cs2_hist": "r1",
                }
            ]
            result1 = transform.process(rows1, ctx1)
            assert result1.status == "success"

            # CRITICAL: Client should be cleaned up after batch
            assert len(transform._http_clients) == 0, (
                f"Sequential mode leaked batch client! Expected 0 clients, found {len(transform._http_clients)}"
            )

            # Process second batch with different state_id
            ctx2 = make_plugin_context(state_id="batch-seq-002")
            rows2 = [
                {
                    "cs1_bg": "r2",
                    "cs1_sym": "r2",
                    "cs1_hist": "r2",
                    "cs2_bg": "r2",
                    "cs2_sym": "r2",
                    "cs2_hist": "r2",
                }
            ]
            result2 = transform.process(rows2, ctx2)
            assert result2.status == "success"

            # CRITICAL: Still no clients (second batch also cleaned up)
            assert len(transform._http_clients) == 0, (
                "Sequential mode accumulated clients across batches! "
                f"Expected 0 clients, found {len(transform._http_clients)}: {list(transform._http_clients.keys())}"
            )


class TestHTTPSpecificBehavior:
    """Tests specific to HTTP-based implementation (vs SDK-based Azure)."""

    def test_handles_non_json_http_response(self) -> None:
        """HTTP errors with non-JSON body are handled gracefully."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = 500
            mock_response.headers = {"content-type": "text/html"}
            mock_response.text = "<html>Internal Server Error</html>"
            mock_response.content = b""
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Internal Server Error",
                request=Mock(),
                response=mock_response,
            )
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__enter__ = Mock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = Mock(return_value=None)

            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            assert ctx.state_id is not None
            result = transform._process_single_query(row, spec, ctx.state_id)

            # Should return error result, not raise exception
            assert result.status == "error"
            assert result.reason is not None
            assert result.reason["reason"] == "api_call_failed"

    def test_handles_empty_choices_array(self) -> None:
        """Empty choices array in response returns appropriate error."""
        response_data = {
            "choices": [],  # Empty choices
            "model": "anthropic/claude-3-opus",
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        }

        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_response = Mock(spec=httpx.Response)
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.json.return_value = response_data
            mock_response.text = json.dumps(response_data)
            mock_response.content = b""
            mock_response.raise_for_status = Mock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__enter__ = Mock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = Mock(return_value=None)

            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            assert ctx.state_id is not None
            result = transform._process_single_query(row, spec, ctx.state_id)

            assert result.status == "error"
            assert result.reason is not None
            assert result.reason["reason"] == "empty_choices"

    def test_handles_missing_output_field_in_json(self) -> None:
        """Missing expected field in LLM JSON response returns appropriate error."""
        # Response missing 'rationale' field that output_mapping expects
        responses = [make_openrouter_response({"score": 85})]  # Missing 'rationale'

        with mock_openrouter_http_responses(responses):
            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            assert ctx.state_id is not None
            result = transform._process_single_query(row, spec, ctx.state_id)

            assert result.status == "error"
            assert result.reason is not None
            assert result.reason["reason"] == "missing_output_field"
            assert result.reason["field"] == "rationale"

    def test_handles_connection_error(self) -> None:
        """Network connection errors are handled gracefully."""
        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client_class.return_value.__enter__ = Mock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = Mock(return_value=False)

            transform = OpenRouterMultiQueryLLMTransform(make_config())
            ctx = make_plugin_context()
            transform.on_start(ctx)

            row = {"cs1_bg": "data", "cs1_sym": "data", "cs1_hist": "data"}
            spec = transform._query_specs[0]

            assert ctx.state_id is not None
            result = transform._process_single_query(row, spec, ctx.state_id)

            assert result.status == "error"
            assert result.reason is not None
            assert result.reason["reason"] == "api_call_failed"


class TestResourceCleanup:
    """Tests for proper resource cleanup."""

    def test_close_shuts_down_executor(self) -> None:
        """close() shuts down the pooled executor."""
        transform = OpenRouterMultiQueryLLMTransform(make_config())

        # Mock the executor
        mock_executor = Mock()
        transform._executor = mock_executor

        transform.close()

        mock_executor.shutdown.assert_called_once_with(wait=True)

    def test_close_clears_http_clients(self) -> None:
        """close() clears all cached HTTP clients."""
        transform = OpenRouterMultiQueryLLMTransform(make_config())

        # Add some mock clients
        transform._http_clients["state-1"] = Mock()
        transform._http_clients["state-2"] = Mock()

        transform.close()

        assert len(transform._http_clients) == 0

    def test_close_clears_recorder_reference(self) -> None:
        """close() clears the recorder reference."""
        transform = OpenRouterMultiQueryLLMTransform(make_config())
        transform._recorder = Mock()

        transform.close()

        assert transform._recorder is None
