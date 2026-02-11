# tests/integration/plugins/llm/test_external_boundary.py
"""Integration tests for external boundary validation in LLM transforms.

Per ELSPETH's Three-Tier Trust Model, LLM responses are Tier 3 (external data)
and must be validated immediately at the boundary. These tests verify:

1. Malformed/unexpected LLM responses produce TransformResult.error (not crashes)
2. Content-filtered responses (content=None) are handled gracefully
3. The Landscape audit trail correctly records errors and successes
4. The HTTP client layer properly classifies errors by retryability

Test architecture:
- TestLLMResponseBoundaryValidation: Uses BaseLLMTransform with mocked SDK client
- TestExternalBoundaryAuditTrail: Verifies Landscape records for boundary errors
- TestHTTPClientBoundary: Tests AuditedHTTPClient error classification
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from elspeth.contracts import CallStatus, CallType, NodeType
from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.plugins.clients.llm import AuditedLLMClient
from elspeth.plugins.llm.base import BaseLLMTransform
from elspeth.testing import make_pipeline_row

DYNAMIC_SCHEMA = {"mode": "observed"}


# ---------------------------------------------------------------------------
# Concrete BaseLLMTransform subclass for testing.
# Named without 'Test' prefix to avoid pytest collection warning.
# ---------------------------------------------------------------------------
class BoundaryTestLLMTransform(BaseLLMTransform):
    """Concrete LLM transform for boundary validation tests.

    Returns the client stored on ctx.llm_client, which is set up
    by test fixtures with controlled mock behaviour.
    """

    name = "boundary_test_llm"

    def _get_llm_client(self, ctx: PluginContext) -> AuditedLLMClient:
        return ctx.llm_client  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_mock_openai_response(
    content: str | None = "valid response",
    model: str = "gpt-4",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> MagicMock:
    """Build a mock object mimicking an OpenAI ChatCompletion response.

    Args:
        content: The content of the first choice message.
                 Set to None to simulate Azure content-filtered responses.
        model: Model name string.
        prompt_tokens: Number of prompt tokens.
        completion_tokens: Number of completion tokens.
    """
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.model = model
    response.usage = MagicMock()
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.model_dump.return_value = {}
    return response


def _setup_recorder_state(recorder: LandscapeRecorder) -> tuple[str, str, str, str, str]:
    """Create a full run/node/row/token/state chain for testing.

    Returns:
        Tuple of (run_id, node_id, row_id, token_id, state_id).
    """
    schema = SchemaConfig.from_dict({"mode": "observed"})
    run = recorder.begin_run(config={}, canonical_version="v1")
    node = recorder.register_node(
        run_id=run.run_id,
        plugin_name="boundary_test_llm",
        node_type=NodeType.TRANSFORM,
        plugin_version="1.0",
        config={},
        schema_config=schema,
    )
    row = recorder.create_row(
        run_id=run.run_id,
        source_node_id=node.node_id,
        row_index=0,
        data={"text": "hello"},
    )
    token = recorder.create_token(row_id=row.row_id)
    state = recorder.begin_node_state(
        token_id=token.token_id,
        node_id=node.node_id,
        run_id=run.run_id,
        step_index=0,
        input_data={"text": "hello"},
    )
    return run.run_id, node.node_id, row.row_id, token.token_id, state.state_id


def _make_transform() -> BoundaryTestLLMTransform:
    """Create a BoundaryTestLLMTransform with a minimal template."""
    return BoundaryTestLLMTransform(
        {
            "model": "gpt-4",
            "template": "Process: {{ row.text }}",
            "schema": DYNAMIC_SCHEMA,
            "required_input_fields": [],  # Explicit opt-out
        }
    )


def _make_audited_client(
    recorder: LandscapeRecorder,
    run_id: str,
    state_id: str,
    mock_openai_client: MagicMock,
) -> AuditedLLMClient:
    """Create an AuditedLLMClient wrapping a mocked OpenAI client."""
    return AuditedLLMClient(
        recorder=recorder,
        state_id=state_id,
        run_id=run_id,
        telemetry_emit=lambda event: None,
        underlying_client=mock_openai_client,
        provider="openai",
    )


# ===================================================================
# TestLLMResponseBoundaryValidation
# ===================================================================
class TestLLMResponseBoundaryValidation:
    """Tests that malformed LLM responses are caught at the boundary
    and produce TransformResult.error, not crashes or silent pass-through.

    These tests use BaseLLMTransform (via BoundaryTestLLMTransform) with
    a mocked OpenAI SDK client. The AuditedLLMClient layer converts raw
    SDK responses to LLMResponse before returning to the transform.
    """

    @pytest.fixture
    def setup(self, recorder: LandscapeRecorder) -> tuple[str, str, str, str, str]:
        return _setup_recorder_state(recorder)

    def test_non_json_content_stored_as_raw_string(self, recorder: LandscapeRecorder, setup: tuple[str, str, str, str, str]) -> None:
        """BaseLLMTransform stores raw content without JSON parsing.

        BaseLLMTransform stores response.content directly without
        parsing it as JSON (that is the transform consumer's concern).
        The AuditedLLMClient converts the SDK response to an LLMResponse
        which stores content as a plain string.

        When the underlying SDK returns non-JSON content, the transform
        produces a success result (content stored as raw string).
        JSON parsing happens in higher-level transforms like OpenRouter
        which parse the HTTP response body.

        For JSON boundary validation at the HTTP layer, see
        TestOpenRouterResponseBoundaryValidation.
        """
        run_id, _, _, _, state_id = setup

        # SDK returns non-JSON text -- AuditedLLMClient wraps it as LLMResponse.content
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response(content="this is not json at all")

        audited = _make_audited_client(recorder, run_id, state_id, mock_client)
        ctx = PluginContext(run_id=run_id, config={})
        ctx.llm_client = audited

        transform = _make_transform()
        result = transform.process(make_pipeline_row({"text": "hello"}), ctx)

        # BaseLLMTransform stores raw content -- no JSON parse at this layer
        assert result.status == "success"
        assert result.row is not None
        assert result.row["llm_response"] == "this is not json at all"

    def test_json_array_content_stored_as_raw_string(self, recorder: LandscapeRecorder, setup: tuple[str, str, str, str, str]) -> None:
        """LLM returns JSON array ``[1,2,3]`` as content string.

        BaseLLMTransform does NOT parse response content as JSON; it
        stores the raw string. JSON structure validation is the
        responsibility of downstream consumers or specific transforms
        (e.g., OpenRouter's ``_process_row`` parses and validates).

        This test documents the behavior: array content is stored as-is.
        """
        run_id, _, _, _, state_id = setup

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response(content="[1, 2, 3]")

        audited = _make_audited_client(recorder, run_id, state_id, mock_client)
        ctx = PluginContext(run_id=run_id, config={})
        ctx.llm_client = audited

        transform = _make_transform()
        result = transform.process(make_pipeline_row({"text": "hello"}), ctx)

        assert result.status == "success"
        assert result.row is not None
        assert result.row["llm_response"] == "[1, 2, 3]"

    def test_empty_string_content_flows_through(self, recorder: LandscapeRecorder, setup: tuple[str, str, str, str, str]) -> None:
        """LLM returns empty string ``""`` as content.

        The AuditedLLMClient converts None content to ``""`` (line 312
        of clients/llm.py: ``response.choices[0].message.content or ""``).
        Empty string is a valid (if useless) response and flows through.

        This test verifies the transform does not crash on empty content.
        """
        run_id, _, _, _, state_id = setup

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response(content="")

        audited = _make_audited_client(recorder, run_id, state_id, mock_client)
        ctx = PluginContext(run_id=run_id, config={})
        ctx.llm_client = audited

        transform = _make_transform()
        result = transform.process(make_pipeline_row({"text": "hello"}), ctx)

        # Empty string is coerced from None via ``or ""``, stored as-is
        assert result.status == "success"
        assert result.row is not None
        assert result.row["llm_response"] == ""

    def test_content_filtered_none_response_returns_empty_string(
        self, recorder: LandscapeRecorder, setup: tuple[str, str, str, str, str]
    ) -> None:
        """Azure content filter case: response.content is None.

        The AuditedLLMClient handles this at line 312:
        ``content = response.choices[0].message.content or ""``

        This coerces None to empty string rather than crashing with
        NoneType. The test verifies no crash and that the empty string
        flows through to the output.

        NOTE: This is the known P0 issue for openrouter_multi_query.py
        line 846, but BaseLLMTransform handles it via the ``or ""``
        guard in AuditedLLMClient. The OpenRouter single-query transform
        handles it explicitly with a ``content_filtered`` error result
        (see openrouter.py line 621-628).
        """
        run_id, _, _, _, state_id = setup

        mock_client = MagicMock()
        # Simulate Azure content filter: content is None
        mock_client.chat.completions.create.return_value = _make_mock_openai_response(content=None)

        audited = _make_audited_client(recorder, run_id, state_id, mock_client)
        ctx = PluginContext(run_id=run_id, config={})
        ctx.llm_client = audited

        transform = _make_transform()
        result = transform.process(make_pipeline_row({"text": "hello"}), ctx)

        # AuditedLLMClient converts None -> "" via ``or ""``.
        # BaseLLMTransform stores that empty string; no crash.
        assert result.status == "success"
        assert result.row is not None
        assert result.row["llm_response"] == ""

    def test_valid_json_object_succeeds(self, recorder: LandscapeRecorder, setup: tuple[str, str, str, str, str]) -> None:
        """LLM returns valid JSON object string -> TransformResult.success."""
        run_id, _, _, _, state_id = setup

        valid_json = json.dumps({"category": "positive", "score": 0.95})
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response(content=valid_json)

        audited = _make_audited_client(recorder, run_id, state_id, mock_client)
        ctx = PluginContext(run_id=run_id, config={})
        ctx.llm_client = audited

        transform = _make_transform()
        result = transform.process(make_pipeline_row({"text": "hello"}), ctx)

        assert result.status == "success"
        assert result.row is not None
        assert result.row["llm_response"] == valid_json

    def test_content_policy_error_returns_non_retryable_error(
        self, recorder: LandscapeRecorder, setup: tuple[str, str, str, str, str]
    ) -> None:
        """Content policy violation from SDK -> non-retryable error result.

        When the OpenAI SDK raises a content policy error, AuditedLLMClient
        classifies it as ContentPolicyError (non-retryable). BaseLLMTransform
        catches non-retryable LLMClientError and returns TransformResult.error.
        """
        run_id, _, _, _, state_id = setup

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("content_policy_violation: The response was filtered")

        audited = _make_audited_client(recorder, run_id, state_id, mock_client)
        ctx = PluginContext(run_id=run_id, config={})
        ctx.llm_client = audited

        transform = _make_transform()
        result = transform.process(make_pipeline_row({"text": "hello"}), ctx)

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "llm_call_failed"
        assert result.retryable is False


# ===================================================================
# TestExternalBoundaryAuditTrail
# ===================================================================
class TestExternalBoundaryAuditTrail:
    """Tests that error/success results from external calls are
    recorded in the Landscape audit trail correctly.
    """

    @pytest.fixture
    def setup(self, recorder: LandscapeRecorder) -> tuple[str, str, str, str, str]:
        return _setup_recorder_state(recorder)

    def test_malformed_response_recorded_as_transform_error(
        self, recorder: LandscapeRecorder, setup: tuple[str, str, str, str, str]
    ) -> None:
        """Bad JSON response from SDK exception -> Landscape calls table has error record.

        When the SDK raises an exception, AuditedLLMClient records the call
        with CallStatus.ERROR in the calls table BEFORE raising LLMClientError.
        """
        run_id, _, _, _, state_id = setup

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Invalid response from API")

        audited = _make_audited_client(recorder, run_id, state_id, mock_client)
        ctx = PluginContext(run_id=run_id, config={})
        ctx.llm_client = audited

        transform = _make_transform()
        result = transform.process(make_pipeline_row({"text": "hello"}), ctx)

        # Transform returns error result
        assert result.status == "error"

        # Verify Landscape recorded the failed call
        calls = recorder.get_calls(state_id)
        assert len(calls) == 1
        call = calls[0]
        assert call.call_type == CallType.LLM
        assert call.status == CallStatus.ERROR
        assert call.error_json is not None
        assert "Invalid response from API" in call.error_json

    def test_error_metadata_contains_response_snippet(self, recorder: LandscapeRecorder, setup: tuple[str, str, str, str, str]) -> None:
        """Error metadata includes the error message for debugging.

        The AuditedLLMClient records the exception type and message in the
        error_json field. The transform's error reason includes the error
        string, providing a truncated view for debugging.
        """
        run_id, _, _, _, state_id = setup

        long_error = "x" * 500
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception(long_error)

        audited = _make_audited_client(recorder, run_id, state_id, mock_client)
        ctx = PluginContext(run_id=run_id, config={})
        ctx.llm_client = audited

        transform = _make_transform()
        result = transform.process(make_pipeline_row({"text": "hello"}), ctx)

        assert result.status == "error"
        assert result.reason is not None
        # The error reason includes the error message
        assert "error" in result.reason

        # Landscape error_json has the raw error
        calls = recorder.get_calls(state_id)
        assert len(calls) == 1
        assert calls[0].error_json is not None
        error_data = json.loads(calls[0].error_json)
        assert error_data["type"] == "Exception"
        assert long_error in error_data["message"]

    def test_successful_call_recorded_with_hashes(self, recorder: LandscapeRecorder, setup: tuple[str, str, str, str, str]) -> None:
        """Valid LLM call -> Landscape calls table has record with response hash."""
        run_id, _, _, _, state_id = setup

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_openai_response(content="Valid output")

        audited = _make_audited_client(recorder, run_id, state_id, mock_client)
        ctx = PluginContext(run_id=run_id, config={})
        ctx.llm_client = audited

        transform = _make_transform()
        result = transform.process(make_pipeline_row({"text": "hello"}), ctx)

        assert result.status == "success"

        # Verify Landscape recorded the successful call
        calls = recorder.get_calls(state_id)
        assert len(calls) == 1
        call = calls[0]
        assert call.call_type == CallType.LLM
        assert call.status == CallStatus.SUCCESS
        assert call.request_hash is not None
        assert len(call.request_hash) == 64  # SHA-256 hex digest
        assert call.response_hash is not None
        assert len(call.response_hash) == 64
        assert call.latency_ms is not None
        assert call.latency_ms > 0
        assert call.error_json is None

    def test_content_policy_error_recorded_in_landscape(self, recorder: LandscapeRecorder, setup: tuple[str, str, str, str, str]) -> None:
        """Content policy error -> both calls table error AND error result."""
        run_id, _, _, _, state_id = setup

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("content_policy_violation: blocked")

        audited = _make_audited_client(recorder, run_id, state_id, mock_client)
        ctx = PluginContext(run_id=run_id, config={})
        ctx.llm_client = audited

        transform = _make_transform()
        result = transform.process(make_pipeline_row({"text": "hello"}), ctx)

        assert result.status == "error"
        assert result.retryable is False

        # Verify the call was recorded as an error in the audit trail
        calls = recorder.get_calls(state_id)
        assert len(calls) == 1
        assert calls[0].status == CallStatus.ERROR
        assert calls[0].error_json is not None
        error_data = json.loads(calls[0].error_json)
        assert error_data["retryable"] is False

    def test_rate_limit_error_recorded_before_raising(self, recorder: LandscapeRecorder, setup: tuple[str, str, str, str, str]) -> None:
        """Rate limit error is recorded in audit trail BEFORE being re-raised.

        Rate limit errors (429) are retryable -- they re-raise as
        RateLimitError for the engine's RetryManager. The audit trail
        must record the attempt before the exception propagates.
        """
        from elspeth.plugins.clients.llm import RateLimitError

        run_id, _, _, _, state_id = setup

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Error 429: Rate limit exceeded")

        audited = _make_audited_client(recorder, run_id, state_id, mock_client)
        ctx = PluginContext(run_id=run_id, config={})
        ctx.llm_client = audited

        transform = _make_transform()

        with pytest.raises(RateLimitError):
            transform.process(make_pipeline_row({"text": "hello"}), ctx)

        # Even though the error propagated, it was recorded first
        calls = recorder.get_calls(state_id)
        assert len(calls) == 1
        assert calls[0].status == CallStatus.ERROR
        assert calls[0].error_json is not None
        error_data = json.loads(calls[0].error_json)
        assert error_data["retryable"] is True


# ===================================================================
# TestHTTPClientBoundary
# ===================================================================
class TestHTTPClientBoundary:
    """Tests for the AuditedHTTPClient boundary validation.

    These tests verify that HTTP-level errors are correctly classified
    as retryable or non-retryable, and that the Landscape audit trail
    records each call attempt.
    """

    @pytest.fixture
    def recorder(self) -> LandscapeRecorder:
        db = LandscapeDB.in_memory()
        return LandscapeRecorder(db)

    @pytest.fixture
    def setup(self, recorder: LandscapeRecorder) -> tuple[str, str]:
        """Create run and state for HTTP client testing.

        Returns:
            Tuple of (run_id, state_id).
        """
        schema = SchemaConfig.from_dict({"mode": "observed"})
        run = recorder.begin_run(config={}, canonical_version="v1")
        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="http_test",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=schema,
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data={},
        )
        token = recorder.create_token(row_id=row.row_id)
        state = recorder.begin_node_state(
            token_id=token.token_id,
            node_id=node.node_id,
            run_id=run.run_id,
            step_index=0,
            input_data={},
        )
        return run.run_id, state.state_id

    def test_server_error_returns_appropriate_error(self, recorder: LandscapeRecorder, setup: tuple[str, str]) -> None:
        """HTTP 500 -> recorded as error in audit trail, exception propagates.

        AuditedHTTPClient records HTTP errors in the calls table and
        re-raises the exception. The transform layer (e.g., OpenRouter)
        catches HTTPStatusError and raises ServerError (retryable).
        """
        from unittest.mock import patch

        from elspeth.plugins.clients.http import AuditedHTTPClient

        run_id, state_id = setup

        http_client = AuditedHTTPClient(
            recorder=recorder,
            state_id=state_id,
            run_id=run_id,
            telemetry_emit=lambda event: None,
            base_url="https://api.example.com",
        )

        # Mock httpx.Client.post to return a 500 response
        mock_response = httpx.Response(
            status_code=500,
            content=b'{"error": "Internal Server Error"}',
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", "https://api.example.com/v1/test"),
        )

        with patch.object(http_client._client, "post", return_value=mock_response):
            response = http_client.post("/v1/test", json={"data": "test"})

        # AuditedHTTPClient returns the response (does not raise for HTTP errors)
        # The transform layer is responsible for calling raise_for_status()
        assert response.status_code == 500

        # Verify audit trail recorded this as an error
        calls = recorder.get_calls(state_id)
        assert len(calls) == 1
        assert calls[0].call_type == CallType.HTTP
        assert calls[0].status == CallStatus.ERROR
        assert calls[0].error_json is not None
        error_data = json.loads(calls[0].error_json)
        assert error_data["status_code"] == 500

        http_client.close()

    def test_client_error_returns_non_retryable(self, recorder: LandscapeRecorder, setup: tuple[str, str]) -> None:
        """HTTP 400 -> recorded as error, non-retryable at transform layer.

        AuditedHTTPClient records the call. The transform layer determines
        retryability based on the status code.
        """
        from unittest.mock import patch

        from elspeth.plugins.clients.http import AuditedHTTPClient

        run_id, state_id = setup

        http_client = AuditedHTTPClient(
            recorder=recorder,
            state_id=state_id,
            run_id=run_id,
            telemetry_emit=lambda event: None,
            base_url="https://api.example.com",
        )

        mock_response = httpx.Response(
            status_code=400,
            content=b'{"error": "Bad Request"}',
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", "https://api.example.com/v1/test"),
        )

        with patch.object(http_client._client, "post", return_value=mock_response):
            response = http_client.post("/v1/test", json={"bad": "request"})

        assert response.status_code == 400

        # Verify audit trail recorded as error
        calls = recorder.get_calls(state_id)
        assert len(calls) == 1
        assert calls[0].status == CallStatus.ERROR
        assert calls[0].error_json is not None
        error_data = json.loads(calls[0].error_json)
        assert error_data["status_code"] == 400

        http_client.close()

    def test_timeout_returns_retryable_error(self, recorder: LandscapeRecorder, setup: tuple[str, str]) -> None:
        """Connection timeout -> recorded as error, exception propagates.

        httpx.ConnectTimeout is a network-level failure. AuditedHTTPClient
        records the error in the calls table and re-raises the exception.
        The transform layer catches this and raises NetworkError (retryable).
        """
        from unittest.mock import patch

        from elspeth.plugins.clients.http import AuditedHTTPClient

        run_id, state_id = setup

        http_client = AuditedHTTPClient(
            recorder=recorder,
            state_id=state_id,
            run_id=run_id,
            telemetry_emit=lambda event: None,
            base_url="https://api.example.com",
            timeout=1.0,
        )

        with (
            patch.object(
                http_client._client,
                "post",
                side_effect=httpx.ConnectTimeout("Connection timed out"),
            ),
            pytest.raises(httpx.ConnectTimeout),
        ):
            http_client.post("/v1/test", json={"data": "test"})

        # Verify audit trail recorded the error even though exception propagated
        calls = recorder.get_calls(state_id)
        assert len(calls) == 1
        assert calls[0].status == CallStatus.ERROR
        assert calls[0].error_json is not None
        error_data = json.loads(calls[0].error_json)
        assert error_data["type"] == "ConnectTimeout"
        assert "timed out" in error_data["message"].lower()

        http_client.close()

    def test_successful_http_call_recorded(self, recorder: LandscapeRecorder, setup: tuple[str, str]) -> None:
        """Successful HTTP 200 -> recorded with request and response hashes."""
        from unittest.mock import patch

        from elspeth.plugins.clients.http import AuditedHTTPClient

        run_id, state_id = setup

        http_client = AuditedHTTPClient(
            recorder=recorder,
            state_id=state_id,
            run_id=run_id,
            telemetry_emit=lambda event: None,
            base_url="https://api.example.com",
        )

        mock_response = httpx.Response(
            status_code=200,
            content=b'{"result": "ok"}',
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", "https://api.example.com/v1/test"),
        )

        with patch.object(http_client._client, "post", return_value=mock_response):
            response = http_client.post("/v1/test", json={"data": "test"})

        assert response.status_code == 200

        # Verify audit trail
        calls = recorder.get_calls(state_id)
        assert len(calls) == 1
        call = calls[0]
        assert call.call_type == CallType.HTTP
        assert call.status == CallStatus.SUCCESS
        assert call.request_hash is not None
        assert call.response_hash is not None
        assert call.latency_ms is not None
        assert call.latency_ms > 0
        assert call.error_json is None

        http_client.close()


# ===================================================================
# TestOpenRouterResponseBoundaryValidation
# ===================================================================
class TestOpenRouterResponseBoundaryValidation:
    """Tests for OpenRouter-specific response boundary validation.

    OpenRouterLLMTransform parses HTTP response bodies as JSON and
    validates the structure (choices, message, content). These tests
    verify that malformed HTTP responses produce TransformResult.error
    rather than crashes.

    Uses TransformExecutor to bridge the accept()/emit() pattern used
    by BatchTransformMixin-based transforms.
    """

    @pytest.fixture
    def recorder(self, tmp_path) -> LandscapeRecorder:
        """File-based DB for cross-thread access (BatchTransformMixin uses threads)."""
        db = LandscapeDB.from_url(f"sqlite:///{tmp_path / 'audit.db'}")
        return LandscapeRecorder(db)

    @pytest.fixture
    def run_id(self, recorder: LandscapeRecorder) -> str:
        run = recorder.begin_run(config={}, canonical_version="v1")
        return run.run_id

    @pytest.fixture
    def node_id(self, recorder: LandscapeRecorder, run_id: str) -> str:
        schema = SchemaConfig.from_dict(DYNAMIC_SCHEMA)
        node = recorder.register_node(
            run_id=run_id,
            plugin_name="openrouter_llm",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=schema,
        )
        return node.node_id

    @pytest.fixture
    def executor(self, recorder: LandscapeRecorder):
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        spans = SpanFactory()
        step_resolver = lambda node_id: 0  # noqa: E731
        return TransformExecutor(recorder, spans, step_resolver)

    def _create_token(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        node_id: str,
        row_data: dict[str, Any],
        row_index: int = 0,
    ):
        from elspeth.contracts.identity import TokenInfo

        row_id = f"row-{row_index}"
        token_id = f"token-{row_index}"
        row = recorder.create_row(
            run_id=run_id,
            source_node_id=node_id,
            row_index=row_index,
            data=row_data,
            row_id=row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token_id)
        pipeline_row = make_pipeline_row(row_data)
        return TokenInfo(row_id=row_id, token_id=token_id, row_data=pipeline_row)

    def _patch_httpx_for_response(self, status_code: int, body: str | bytes, content_type: str = "application/json"):
        """Create a context manager that patches httpx.Client to return a fixed response.

        Replaces httpx.Client with a factory that returns a mock client
        whose post() method returns a pre-built httpx.Response.
        """
        import warnings
        from contextlib import ExitStack
        from unittest.mock import patch

        if isinstance(body, str):
            body = body.encode()

        mock_response = httpx.Response(
            status_code=status_code,
            content=body,
            headers={"content-type": content_type},
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
        )

        def _client_factory(*_args: Any, **kwargs: Any) -> MagicMock:
            client = MagicMock()
            client.post.return_value = mock_response
            return client

        stack = ExitStack()
        stack.enter_context(warnings.catch_warnings())
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        stack.enter_context(patch("httpx.Client", side_effect=_client_factory))
        return stack

    def _make_openrouter_transform(self, node_id: str) -> Any:
        """Create an OpenRouterLLMTransform with on_error configured."""
        from elspeth.plugins.llm.openrouter import OpenRouterLLMTransform

        transform = OpenRouterLLMTransform(
            {
                "model": "test-model",
                "template": "{{ row.text }}",
                "api_key": "test-key",
                "base_url": "https://openrouter.ai/api/v1",
                "schema": DYNAMIC_SCHEMA,
                "required_input_fields": [],
                "pool_size": 5,
            }
        )
        transform.node_id = node_id
        # TransformExecutor requires on_error when transform returns error results.
        # Use "discard" to avoid needing a DIVERT edge in the DAG (edge lookup
        # is skipped for "discard" destination).
        transform.on_error = "discard"
        return transform

    def test_invalid_json_response_returns_error(
        self,
        recorder: LandscapeRecorder,
        executor,
        run_id: str,
        node_id: str,
    ) -> None:
        """OpenRouter receives non-JSON response -> TransformResult.error."""
        transform = self._make_openrouter_transform(node_id)

        ctx = PluginContext(run_id=run_id, config={}, landscape=recorder)
        transform.on_start(ctx)

        row_data = {"text": "test"}
        token = self._create_token(recorder, run_id, node_id, row_data)

        # Return non-JSON response body
        with self._patch_httpx_for_response(200, "this is not json", "text/plain"):
            result, _, _error_sink = executor.execute_transform(
                transform=transform,
                token=token,
                ctx=ctx,
            )

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "invalid_json_response"

        transform.close()

    def test_empty_choices_returns_error(
        self,
        recorder: LandscapeRecorder,
        executor,
        run_id: str,
        node_id: str,
    ) -> None:
        """OpenRouter receives response with empty choices -> error."""
        transform = self._make_openrouter_transform(node_id)

        ctx = PluginContext(run_id=run_id, config={}, landscape=recorder)
        transform.on_start(ctx)

        token = self._create_token(recorder, run_id, node_id, {"text": "test"})

        # Return JSON with empty choices array
        body = json.dumps({"choices": [], "model": "test-model"})
        with self._patch_httpx_for_response(200, body):
            result, _, _error_sink = executor.execute_transform(
                transform=transform,
                token=token,
                ctx=ctx,
            )

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "empty_choices"

        transform.close()

    def test_null_content_returns_content_filtered_error(
        self,
        recorder: LandscapeRecorder,
        executor,
        run_id: str,
        node_id: str,
    ) -> None:
        """OpenRouter receives null content (content-filtered) -> error.

        This is the explicit content_filtered handling in OpenRouter
        (openrouter.py lines 621-628).
        """
        transform = self._make_openrouter_transform(node_id)

        ctx = PluginContext(run_id=run_id, config={}, landscape=recorder)
        transform.on_start(ctx)

        token = self._create_token(recorder, run_id, node_id, {"text": "test"})

        # Return JSON with null content (simulates content filtering)
        body = json.dumps(
            {
                "choices": [{"message": {"content": None}}],
                "model": "test-model",
                "usage": {"prompt_tokens": 10, "completion_tokens": 0},
            }
        )
        with self._patch_httpx_for_response(200, body):
            result, _, _error_sink = executor.execute_transform(
                transform=transform,
                token=token,
                ctx=ctx,
            )

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "content_filtered"

        transform.close()

    def test_malformed_response_structure_returns_error(
        self,
        recorder: LandscapeRecorder,
        executor,
        run_id: str,
        node_id: str,
    ) -> None:
        """OpenRouter receives JSON missing expected keys -> error."""
        transform = self._make_openrouter_transform(node_id)

        ctx = PluginContext(run_id=run_id, config={}, landscape=recorder)
        transform.on_start(ctx)

        token = self._create_token(recorder, run_id, node_id, {"text": "test"})

        # Return JSON without 'choices' key
        body = json.dumps({"error": "something went wrong", "model": "test-model"})
        with self._patch_httpx_for_response(200, body):
            result, _, _error_sink = executor.execute_transform(
                transform=transform,
                token=token,
                ctx=ctx,
            )

        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "malformed_response"

        transform.close()

    def test_valid_openrouter_response_succeeds(
        self,
        recorder: LandscapeRecorder,
        executor,
        run_id: str,
        node_id: str,
    ) -> None:
        """OpenRouter receives valid response -> TransformResult.success."""
        transform = self._make_openrouter_transform(node_id)

        ctx = PluginContext(run_id=run_id, config={}, landscape=recorder)
        transform.on_start(ctx)

        token = self._create_token(recorder, run_id, node_id, {"text": "test"})

        body = json.dumps(
            {
                "choices": [{"message": {"content": "Hello from LLM"}}],
                "model": "test-model",
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            }
        )
        with self._patch_httpx_for_response(200, body):
            result, _, _error_sink = executor.execute_transform(
                transform=transform,
                token=token,
                ctx=ctx,
            )

        assert result.status == "success"
        assert result.row is not None
        assert result.row["llm_response"] == "Hello from LLM"
        assert _error_sink is None

        transform.close()
