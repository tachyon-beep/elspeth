# tests/integration/plugins/llm/test_openrouter_batch_integration.py
"""Integration tests for OpenRouter batch LLM transform.

These tests exercise gaps that unit tests cannot cover because they use
Mock() contexts. Integration tests use real LandscapeRecorder, real
PluginContext, and real AuditedHTTPClient instances to verify:

1. Thread safety: concurrent workers sharing a real recorder
2. httpx.StreamError: batch-level exception handling + audit recording
3. Rate limiter wiring: on_start() passes limiter to AuditedHTTPClient
4. Content-filtered None: null content in JSON response
5. on_start() wiring: real PluginContext fields propagated correctly
"""

from __future__ import annotations

import json
import threading
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from elspeth.contracts import CallStatus, CallType, NodeType
from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.core.landscape.schema import calls_table
from elspeth.plugins.llm.openrouter_batch import OpenRouterBatchLLMTransform
from elspeth.testing import make_pipeline_row
from tests.unit.plugins.llm.conftest import chaosllm_openrouter_http_responses

# Common schema config for dynamic field handling
DYNAMIC_SCHEMA = {"mode": "observed"}


def _make_valid_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a valid config dict with optional overrides."""
    config = {
        "api_key": "sk-or-test-key",
        "model": "openai/gpt-4o-mini",
        "template": "Analyze: {{ row.text }}",
        "schema": DYNAMIC_SCHEMA,
        "required_input_fields": [],
    }
    if overrides:
        config.update(overrides)
    return config


def _setup_recorder_state(
    recorder: LandscapeRecorder,
) -> tuple[str, str, str]:
    """Set up a full run/node/row/token/state chain for integration tests.

    Returns:
        Tuple of (run_id, node_id, state_id)
    """
    schema = SchemaConfig.from_dict({"mode": "observed"})
    run = recorder.begin_run(config={"test": True}, canonical_version="v1")
    node = recorder.register_node(
        run_id=run.run_id,
        plugin_name="openrouter_batch_llm",
        node_type=NodeType.TRANSFORM,
        plugin_version="1.0",
        config={"model": "openai/gpt-4o-mini"},
        schema_config=schema,
    )
    row = recorder.create_row(
        run_id=run.run_id,
        source_node_id=node.node_id,
        row_index=0,
        data={"text": "setup"},
    )
    token = recorder.create_token(row_id=row.row_id)
    state = recorder.begin_node_state(
        token_id=token.token_id,
        node_id=node.node_id,
        run_id=run.run_id,
        step_index=0,
        input_data={"text": "setup"},
    )
    return run.run_id, node.node_id, state.state_id


def _make_real_context(
    recorder: LandscapeRecorder,
    run_id: str,
    state_id: str,
    *,
    rate_limit_registry: Any = None,
) -> PluginContext:
    """Create a real PluginContext backed by a real recorder."""
    return PluginContext(
        run_id=run_id,
        config={},
        landscape=recorder,
        state_id=state_id,
        rate_limit_registry=rate_limit_registry,
    )


def _create_mock_response(
    chaosllm_server,
    *,
    content: str = "Test response",
    status_code: int = 200,
    raw_body: str | bytes | None = None,
    headers: dict[str, str] | None = None,
    usage: dict[str, int] | None = None,
) -> httpx.Response:
    """Create a mock httpx.Response using ChaosLLM."""
    from tests.unit.plugins.llm.conftest import chaosllm_openrouter_httpx_response

    request = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": "test"}],
        "temperature": 0.0,
    }
    return chaosllm_openrouter_httpx_response(
        chaosllm_server,
        request,
        status_code=status_code,
        template_override=content,
        raw_body=raw_body,
        headers=headers,
        usage_override=usage,
    )


# ===================================================================
# TestThreadSafetyConcurrentWorkers
# ===================================================================
class TestThreadSafetyConcurrentWorkers:
    """Verify thread safety when concurrent workers share a real LandscapeRecorder.

    The key invariant: allocate_call_index() uses a lock to ensure
    UNIQUE(state_id, call_index) across all concurrent workers. These tests
    verify no constraint violations occur under real concurrency.
    """

    @pytest.fixture
    def db(self, tmp_path) -> LandscapeDB:
        # Use file-based SQLite for cross-thread access
        return LandscapeDB.from_url(f"sqlite:///{tmp_path / 'audit.db'}")

    @pytest.fixture
    def recorder(self, db: LandscapeDB) -> LandscapeRecorder:
        return LandscapeRecorder(db)

    def test_concurrent_workers_produce_unique_call_indices(self, chaosllm_server, recorder: LandscapeRecorder) -> None:
        """Multiple workers sharing one recorder produce unique call indices.

        Invariant: UNIQUE(state_id, call_index) must hold even when
        pool_size > 1 and all workers allocate indices concurrently.
        """
        run_id, _node_id, state_id = _setup_recorder_state(recorder)
        ctx = _make_real_context(recorder, run_id, state_id)

        batch_size = 8
        pool_size = 4
        transform = OpenRouterBatchLLMTransform(_make_valid_config({"pool_size": pool_size}))
        transform.on_start(ctx)

        rows = [make_pipeline_row({"text": f"Row {i}"}) for i in range(batch_size)]
        responses = [_create_mock_response(chaosllm_server, content=f"Result {i}") for i in range(batch_size)]

        with chaosllm_openrouter_http_responses(chaosllm_server, responses):
            result = transform.process(rows, ctx)

        assert result.status == "success"
        assert result.rows is not None
        assert len(result.rows) == batch_size

        # Verify call indices are unique in the database
        from sqlalchemy import select

        with recorder._db.engine.connect() as conn:
            rows_db = conn.execute(
                select(calls_table.c.call_index, calls_table.c.state_id).where(calls_table.c.state_id == state_id)
            ).fetchall()

        call_indices = [r.call_index for r in rows_db]
        assert len(call_indices) == batch_size, f"Expected {batch_size} call records, got {len(call_indices)}"
        assert len(set(call_indices)) == len(call_indices), f"Duplicate call indices found: {call_indices}"

        transform.close()

    def test_concurrent_workers_all_calls_recorded(self, chaosllm_server, recorder: LandscapeRecorder) -> None:
        """Every row in a concurrent batch produces exactly one audit call record.

        This verifies that no calls are lost under concurrency — the audit
        trail must account for every row processed.
        """
        run_id, _node_id, state_id = _setup_recorder_state(recorder)
        ctx = _make_real_context(recorder, run_id, state_id)

        batch_size = 6
        transform = OpenRouterBatchLLMTransform(_make_valid_config({"pool_size": 3}))
        transform.on_start(ctx)

        rows = [make_pipeline_row({"text": f"Row {i}"}) for i in range(batch_size)]
        responses = [_create_mock_response(chaosllm_server, content=f"Result {i}") for i in range(batch_size)]

        with chaosllm_openrouter_http_responses(chaosllm_server, responses):
            result = transform.process(rows, ctx)

        assert result.status == "success"

        # Every row should have a corresponding call in the audit trail
        calls = recorder.get_calls(state_id)
        assert len(calls) == batch_size, f"Expected {batch_size} audit calls, got {len(calls)}. Some calls were lost under concurrency."

        # All should be HTTP calls (via AuditedHTTPClient)
        assert all(c.call_type == CallType.HTTP for c in calls)
        assert all(c.status == CallStatus.SUCCESS for c in calls)

        transform.close()


# ===================================================================
# TestStreamErrorBatchHandling
# ===================================================================
class TestStreamErrorBatchHandling:
    """Verify httpx.StreamError handling at the _process_batch level.

    StreamError is the only exception type caught at the batch level
    (line 466 of openrouter_batch.py). It occurs during response streaming
    after the request succeeds — _process_single_row's try/except for
    HTTPStatusError and RequestError doesn't cover it.
    """

    @pytest.fixture
    def db(self, tmp_path) -> LandscapeDB:
        return LandscapeDB.from_url(f"sqlite:///{tmp_path / 'audit.db'}")

    @pytest.fixture
    def recorder(self, db: LandscapeDB) -> LandscapeRecorder:
        return LandscapeRecorder(db)

    def test_stream_error_produces_error_marker_not_crash(self, chaosllm_server, recorder: LandscapeRecorder) -> None:
        """StreamError during response streaming produces per-row error marker.

        The batch does NOT crash — the affected row gets an error marker
        and other rows can still succeed.
        """
        run_id, _, state_id = _setup_recorder_state(recorder)
        ctx = _make_real_context(recorder, run_id, state_id)

        transform = OpenRouterBatchLLMTransform(_make_valid_config({"pool_size": 1}))
        transform.on_start(ctx)

        rows = [make_pipeline_row({"text": "Test row"})]

        # StreamError escapes _process_single_row, caught at _process_batch level
        with chaosllm_openrouter_http_responses(
            chaosllm_server,
            [_create_mock_response(chaosllm_server)],
            side_effect=httpx.StreamClosed(),
        ):
            result = transform.process(rows, ctx)

        assert result.status == "success"
        assert result.rows is not None
        assert len(result.rows) == 1

        # Row has error marker with transport_exception reason
        error_row = result.rows[0]
        assert error_row["llm_response"] is None
        assert error_row["llm_response_error"]["reason"] == "transport_exception"
        assert "StreamClosed" in error_row["llm_response_error"]["error_type"]

        transform.close()

    def test_stream_error_recorded_in_audit_trail(self, chaosllm_server, recorder: LandscapeRecorder) -> None:
        """StreamError is recorded to audit trail via ctx.record_call().

        Even though AuditedHTTPClient didn't get to record (the error
        occurs after the HTTP layer), _process_batch records it manually
        so the failure is attributable.
        """
        run_id, _, state_id = _setup_recorder_state(recorder)
        ctx = _make_real_context(recorder, run_id, state_id)

        transform = OpenRouterBatchLLMTransform(_make_valid_config({"pool_size": 1}))
        transform.on_start(ctx)

        rows = [make_pipeline_row({"text": "Test row"})]

        with chaosllm_openrouter_http_responses(
            chaosllm_server,
            [_create_mock_response(chaosllm_server)],
            side_effect=httpx.StreamClosed(),
        ):
            transform.process(rows, ctx)

        # Audit trail should have the transport error recorded
        calls = recorder.get_calls(state_id)
        assert len(calls) >= 1

        transport_calls = [c for c in calls if c.error_json is not None and "transport_exception" in c.error_json]
        assert len(transport_calls) == 1, "StreamError must be recorded in audit trail for attributability"

        transform.close()

    def test_stream_error_mixed_with_success(self, chaosllm_server, recorder: LandscapeRecorder) -> None:
        """Batch with mix of StreamError and success: both recorded correctly.

        One row succeeds, one hits StreamError — both produce output rows
        and both are recorded in the audit trail.
        """
        run_id, _, state_id = _setup_recorder_state(recorder)
        ctx = _make_real_context(recorder, run_id, state_id)

        transform = OpenRouterBatchLLMTransform(
            _make_valid_config({"pool_size": 1})  # pool_size=1 to control ordering
        )
        transform.on_start(ctx)

        rows = [
            make_pipeline_row({"text": "Row 0"}),
            make_pipeline_row({"text": "Row 1"}),
        ]

        # First call succeeds, second raises StreamError
        success_response = _create_mock_response(chaosllm_server, content="Success")
        call_count = [0]
        lock = threading.Lock()

        def side_effect_fn(*args: Any, **kwargs: Any) -> httpx.Response:
            with lock:
                idx = call_count[0]
                call_count[0] += 1
            if idx == 0:
                return success_response
            raise httpx.StreamClosed()

        with patch("httpx.Client") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.__enter__ = lambda self: self
            mock_client.__exit__ = lambda self, *a: False
            mock_client.post.side_effect = side_effect_fn
            result = transform.process(rows, ctx)

        assert result.status == "success"
        assert result.rows is not None
        assert len(result.rows) == 2

        # One success, one error
        success_rows = [r for r in result.rows if r.get("llm_response") is not None]
        error_rows = [r for r in result.rows if r.get("llm_response_error") is not None]
        assert len(success_rows) == 1
        assert len(error_rows) == 1
        assert error_rows[0]["llm_response_error"]["reason"] == "transport_exception"

        transform.close()


# ===================================================================
# TestContentFilteredNoneResponse
# ===================================================================
class TestContentFilteredNoneResponse:
    """Verify handling of null content in JSON response.

    When content moderation filters a response, OpenRouter returns:
    {"choices": [{"message": {"content": null}}]}

    The plugin extracts content via choices[0]["message"]["content"],
    which yields Python None. This must not crash — it should be stored
    as None (a valid signal that content was filtered).
    """

    @pytest.fixture
    def db(self, tmp_path) -> LandscapeDB:
        # File-based for cross-thread access (worker threads write to audit trail)
        return LandscapeDB.from_url(f"sqlite:///{tmp_path / 'audit.db'}")

    @pytest.fixture
    def recorder(self, db: LandscapeDB) -> LandscapeRecorder:
        return LandscapeRecorder(db)

    def test_null_content_stored_as_none(self, chaosllm_server, recorder: LandscapeRecorder) -> None:
        """Content-filtered response with null content produces row with None.

        This validates that the plugin doesn't crash on None content
        (related to P0 NoneType crash pattern in openrouter_multi_query).
        """
        run_id, _, state_id = _setup_recorder_state(recorder)
        ctx = _make_real_context(recorder, run_id, state_id)

        transform = OpenRouterBatchLLMTransform(_make_valid_config())
        transform.on_start(ctx)

        rows = [make_pipeline_row({"text": "Filtered content"})]

        # Response with null content (content moderation)
        filtered_body = json.dumps(
            {
                "choices": [{"message": {"content": None}}],
                "model": "openai/gpt-4o-mini",
                "usage": {"prompt_tokens": 10, "completion_tokens": 0},
            }
        )
        filtered_response = _create_mock_response(
            chaosllm_server,
            raw_body=filtered_body,
            headers={"content-type": "application/json"},
        )

        with chaosllm_openrouter_http_responses(chaosllm_server, [filtered_response]):
            result = transform.process(rows, ctx)

        assert result.status == "success"
        assert result.rows is not None
        assert len(result.rows) == 1

        # Content is None (filtered) — this is a valid output, not an error
        output = result.rows[0]
        assert output["llm_response"] is None
        # No error marker — null content is "success" (content was filtered,
        # but the API call itself succeeded)
        assert output.get("llm_response_error") is None

        transform.close()

    def test_null_content_audit_trail_records_success(self, chaosllm_server, recorder: LandscapeRecorder) -> None:
        """Null-content response is recorded as successful call in audit trail."""
        run_id, _, state_id = _setup_recorder_state(recorder)
        ctx = _make_real_context(recorder, run_id, state_id)

        transform = OpenRouterBatchLLMTransform(_make_valid_config())
        transform.on_start(ctx)

        rows = [make_pipeline_row({"text": "Filtered content"})]

        filtered_body = json.dumps(
            {
                "choices": [{"message": {"content": None}}],
                "model": "openai/gpt-4o-mini",
                "usage": {"prompt_tokens": 10, "completion_tokens": 0},
            }
        )
        filtered_response = _create_mock_response(
            chaosllm_server,
            raw_body=filtered_body,
            headers={"content-type": "application/json"},
        )

        with chaosllm_openrouter_http_responses(chaosllm_server, [filtered_response]):
            transform.process(rows, ctx)

        # The HTTP call itself succeeded — audit trail should show SUCCESS
        calls = recorder.get_calls(state_id)
        assert len(calls) == 1
        assert calls[0].status == CallStatus.SUCCESS

        transform.close()


# ===================================================================
# TestRateLimiterWiring
# ===================================================================
class TestRateLimiterWiring:
    """Verify rate limiter is passed through on_start() to AuditedHTTPClient.

    Unit tests set rate_limit_registry=None. These tests verify the
    real wiring: on_start() extracts the limiter, _get_http_client()
    passes it to AuditedHTTPClient, and the client uses it.
    """

    def test_limiter_passed_to_http_client(self, chaosllm_server, recorder: LandscapeRecorder) -> None:
        """Rate limiter from registry is passed to AuditedHTTPClient.

        Verifies the wiring: ctx.rate_limit_registry.get_limiter("openrouter")
        → transform._limiter → AuditedHTTPClient(limiter=...).
        """
        from unittest.mock import Mock

        run_id, _, state_id = _setup_recorder_state(recorder)

        # Create a mock rate limit registry that returns a mock limiter
        mock_limiter = Mock()
        mock_limiter.try_acquire = Mock(return_value=True)
        mock_registry = Mock()
        mock_registry.get_limiter = Mock(return_value=mock_limiter)

        ctx = _make_real_context(
            recorder,
            run_id,
            state_id,
            rate_limit_registry=mock_registry,
        )

        transform = OpenRouterBatchLLMTransform(_make_valid_config())
        transform.on_start(ctx)

        # Verify on_start extracted the limiter
        assert transform._limiter is mock_limiter
        mock_registry.get_limiter.assert_called_once_with("openrouter")

        # Verify _get_http_client passes limiter to AuditedHTTPClient
        client = transform._get_http_client(state_id)
        assert client._limiter is mock_limiter

        transform.close()

    def test_none_registry_produces_none_limiter(self, chaosllm_server, recorder: LandscapeRecorder) -> None:
        """When rate_limit_registry is None, limiter is None (no throttling)."""
        run_id, _, state_id = _setup_recorder_state(recorder)
        ctx = _make_real_context(recorder, run_id, state_id)

        transform = OpenRouterBatchLLMTransform(_make_valid_config())
        transform.on_start(ctx)

        assert transform._limiter is None

        # Client still created successfully without limiter
        client = transform._get_http_client(state_id)
        assert client._limiter is None

        transform.close()


# ===================================================================
# TestOnStartWiring
# ===================================================================
class TestOnStartWiring:
    """Verify on_start() correctly wires real PluginContext fields.

    Unit tests mock on_start(). These tests verify the real wiring:
    recorder, run_id, telemetry_emit, and rate limiter are all captured.
    """

    def test_on_start_captures_recorder(self, recorder: LandscapeRecorder) -> None:
        """on_start() captures landscape recorder for audit recording."""
        run_id, _, state_id = _setup_recorder_state(recorder)
        ctx = _make_real_context(recorder, run_id, state_id)

        transform = OpenRouterBatchLLMTransform(_make_valid_config())
        assert transform._recorder is None  # Before on_start

        transform.on_start(ctx)

        assert transform._recorder is recorder
        assert transform._run_id == run_id
        transform.close()

    def test_on_start_captures_telemetry_emit(self, recorder: LandscapeRecorder) -> None:
        """on_start() captures telemetry_emit callback from context."""
        run_id, _, state_id = _setup_recorder_state(recorder)

        events: list[Any] = []
        ctx = _make_real_context(recorder, run_id, state_id)
        ctx.telemetry_emit = events.append

        transform = OpenRouterBatchLLMTransform(_make_valid_config())
        transform.on_start(ctx)

        assert transform._telemetry_emit == events.append
        transform.close()

    def test_recorder_none_prevents_http_client_creation(self, recorder: LandscapeRecorder) -> None:
        """_get_http_client crashes if on_start wasn't called (recorder is None).

        Per CLAUDE.md: plugin initialization bugs must crash, not silently
        produce wrong results.
        """
        transform = OpenRouterBatchLLMTransform(_make_valid_config())
        # Deliberately skip on_start()

        with pytest.raises(RuntimeError, match="requires recorder"):
            transform._get_http_client("state-test")

        transform.close()


# ===================================================================
# TestBatchOrderPreservation
# ===================================================================
class TestBatchOrderPreservation:
    """Verify output row order matches input row order under real concurrency.

    Unit tests use pool_size=2 with mocks that execute synchronously.
    This test uses real thread pools with artificial delays to verify
    that results are reassembled in input order even when workers
    complete out-of-order.
    """

    @pytest.fixture
    def db(self, tmp_path) -> LandscapeDB:
        return LandscapeDB.from_url(f"sqlite:///{tmp_path / 'audit.db'}")

    @pytest.fixture
    def recorder(self, db: LandscapeDB) -> LandscapeRecorder:
        return LandscapeRecorder(db)

    def test_output_order_matches_input_order_with_delays(self, chaosllm_server, recorder: LandscapeRecorder) -> None:
        """Results reassembled in input order even when workers finish out-of-order.

        Row 0 gets a slow response, Row 1 gets a fast response.
        Output must still be [Row 0, Row 1].
        """
        import time

        run_id, _, state_id = _setup_recorder_state(recorder)
        ctx = _make_real_context(recorder, run_id, state_id)

        transform = OpenRouterBatchLLMTransform(_make_valid_config({"pool_size": 2}))
        transform.on_start(ctx)

        rows = [
            make_pipeline_row({"text": "Slow row", "idx": "0"}),
            make_pipeline_row({"text": "Fast row", "idx": "1"}),
        ]

        # Row 0 slow, Row 1 fast — completion order is reversed
        call_count = [0]
        lock = threading.Lock()

        slow_response = _create_mock_response(chaosllm_server, content="Slow result")
        fast_response = _create_mock_response(chaosllm_server, content="Fast result")

        def side_effect_fn(*args: Any, **kwargs: Any) -> httpx.Response:
            with lock:
                idx = call_count[0]
                call_count[0] += 1
            if idx == 0:
                time.sleep(0.1)  # Slow
                return slow_response
            return fast_response  # Fast

        with patch("httpx.Client") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.__enter__ = lambda self: self
            mock_client.__exit__ = lambda self, *a: False
            mock_client.post.side_effect = side_effect_fn
            result = transform.process(rows, ctx)

        assert result.status == "success"
        assert result.rows is not None
        assert len(result.rows) == 2

        # Output order must match input order (not completion order)
        assert result.rows[0]["idx"] == "0", "First output row must be input row 0"
        assert result.rows[1]["idx"] == "1", "Second output row must be input row 1"

        transform.close()
