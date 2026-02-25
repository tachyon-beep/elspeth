# tests/unit/plugins/llm/test_p1_bug_fixes.py
"""Regression tests for P1 LLM plugin bug fixes (2026-02-14 batch).

Each test class corresponds to one bug fix:
1. Azure process_row mutable ctx.state_id in cleanup
2. OpenRouter batch HTTP clients never evicted per batch
3. Base LLM transform output schema diverges from output_schema_config
4. Terminal batch failures clear checkpoint without per-row LLM call recording
5. enable_content_recording accepted but never applied
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch

if TYPE_CHECKING:
    from elspeth.contracts.batch_checkpoint import BatchCheckpointState

from elspeth.contracts import CallStatus, CallType
from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.schema import SchemaConfig
from elspeth.plugins.llm import (
    _build_augmented_output_schema,
)
from elspeth.plugins.llm.transform import LLMTransform
from elspeth.testing import make_pipeline_row

from .conftest import DYNAMIC_SCHEMA, make_plugin_context, make_token

# ---------------------------------------------------------------------------
# Bug 1: Azure process_row uses mutable ctx.state_id in cleanup
# ---------------------------------------------------------------------------


class TestAzureStateIdSnapshot:
    """Regression: ctx.state_id must be snapshotted at _process_row entry.

    The engine can rewrite ctx.state_id between attempts on the same context.
    If the finally block uses ctx.state_id instead of the snapshot, it can
    evict the wrong cached client during retry/timeout races.

    Migrated to LLMTransform: the unified transform delegates to _provider,
    which no longer uses a per-state_id client cache. This test verifies that
    _process_row correctly uses the state_id from ctx at call time (the strategy
    captures it), and that processing succeeds with different state_ids.
    """

    def test_process_row_uses_snapshot_for_cleanup(self, chaosllm_server: Any) -> None:
        """Verify that _process_row works correctly even when ctx.state_id
        is mutated between calls."""
        from .conftest import chaosllm_azure_openai_client

        config = {
            "provider": "azure",
            "deployment_name": "test-deploy",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "test-key",
            "template": "hello",
            "schema": DYNAMIC_SCHEMA,
            "required_input_fields": [],
        }

        with chaosllm_azure_openai_client(chaosllm_server, mode="echo"):
            transform = LLMTransform(config)
            ctx = make_plugin_context(state_id="state-A")
            transform.on_start(ctx)

            row = make_pipeline_row({"text": "test"})

            # Process row with state_id="state-A"
            result = transform._process_row(row, ctx)
            assert result.status == "success"

            # Mutate ctx.state_id and process again — the strategy should
            # snapshot state_id at entry and use it consistently within
            # the call, so this must also succeed cleanly.
            ctx.state_id = "state-X"
            result2 = transform._process_row(row, ctx)
            assert result2.status == "success"

            transform.close()


# ---------------------------------------------------------------------------
# Bug 2: OpenRouter batch HTTP clients never evicted per batch
# ---------------------------------------------------------------------------


class TestOpenRouterBatchClientEviction:
    """Regression: HTTP clients must be evicted after each batch completes.

    Without per-batch eviction, each aggregation flush creates a new state_id
    and the client cache grows unboundedly.
    """

    def test_client_evicted_after_batch_success(self, chaosllm_server: Any) -> None:
        """HTTP client is evicted from cache after successful batch processing."""
        from elspeth.plugins.llm.openrouter_batch import OpenRouterBatchLLMTransform

        from .conftest import chaosllm_openrouter_http_responses

        config = {
            "api_key": "sk-test-key",
            "model": "openai/gpt-4o-mini",
            "template": "hello",
            "schema": DYNAMIC_SCHEMA,
            "required_input_fields": [],
        }

        ctx = Mock(spec=PluginContext)
        ctx.run_id = "run-1"
        ctx.state_id = "state-batch-1"
        ctx.landscape = Mock()
        ctx.landscape.allocate_call_index = Mock(side_effect=lambda _: 0)
        ctx.landscape.record_call = Mock()
        ctx.record_call = Mock()
        ctx.telemetry_emit = Mock()
        ctx.rate_limit_registry = None
        ctx.batch_token_ids = None
        ctx.token = make_token()

        with chaosllm_openrouter_http_responses(
            chaosllm_server,
            ["test response"],
        ):
            transform = OpenRouterBatchLLMTransform(config)
            transform.on_start(ctx)

            row = make_pipeline_row({"text": "test"})
            result = transform.process([row], ctx)
            assert result.status == "success"

            # Client for "state-batch-1" should be evicted after batch completes
            assert "state-batch-1" not in transform._http_clients

            transform.close()

    def test_client_evicted_after_batch_failure(self, chaosllm_server: Any) -> None:
        """HTTP client is evicted from cache even when batch encounters errors."""
        import httpx

        from elspeth.plugins.llm.openrouter_batch import OpenRouterBatchLLMTransform

        from .conftest import chaosllm_openrouter_http_responses

        config = {
            "api_key": "sk-test-key",
            "model": "openai/gpt-4o-mini",
            "template": "hello",
            "schema": DYNAMIC_SCHEMA,
            "required_input_fields": [],
        }

        ctx = Mock(spec=PluginContext)
        ctx.run_id = "run-1"
        ctx.state_id = "state-fail-1"
        ctx.landscape = Mock()
        ctx.landscape.allocate_call_index = Mock(side_effect=lambda _: 0)
        ctx.landscape.record_call = Mock()
        ctx.record_call = Mock()
        ctx.telemetry_emit = Mock()
        ctx.rate_limit_registry = None
        ctx.batch_token_ids = None
        ctx.token = make_token()

        # Create a 500 error response
        error_response = httpx.Response(
            status_code=500,
            content=b'{"error": "internal server error"}',
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", "http://testserver/v1/chat/completions"),
        )

        with chaosllm_openrouter_http_responses(
            chaosllm_server,
            [error_response],
        ):
            transform = OpenRouterBatchLLMTransform(config)
            transform.on_start(ctx)

            row = make_pipeline_row({"text": "test"})
            result = transform.process([row], ctx)
            # Result may be success (with error markers per-row) since individual
            # row errors don't make the whole batch fail
            assert result.status == "success"

            # Client for "state-fail-1" should still be evicted
            assert "state-fail-1" not in transform._http_clients

            transform.close()

    def test_multiple_batches_dont_accumulate_clients(self, chaosllm_server: Any) -> None:
        """Multiple batches with different state_ids don't grow the client cache."""
        from elspeth.plugins.llm.openrouter_batch import OpenRouterBatchLLMTransform

        from .conftest import chaosllm_openrouter_http_responses

        config = {
            "api_key": "sk-test-key",
            "model": "openai/gpt-4o-mini",
            "template": "hello",
            "schema": DYNAMIC_SCHEMA,
            "required_input_fields": [],
        }

        ctx = Mock(spec=PluginContext)
        ctx.run_id = "run-1"
        ctx.landscape = Mock()
        ctx.landscape.allocate_call_index = Mock(side_effect=lambda _: 0)
        ctx.landscape.record_call = Mock()
        ctx.record_call = Mock()
        ctx.telemetry_emit = Mock()
        ctx.rate_limit_registry = None
        ctx.batch_token_ids = None
        ctx.token = make_token()

        with chaosllm_openrouter_http_responses(
            chaosllm_server,
            ["response"],
        ):
            transform = OpenRouterBatchLLMTransform(config)
            transform.on_start(ctx)

            row = make_pipeline_row({"text": "test"})

            # Process 5 batches with different state_ids (simulating aggregation flushes)
            for i in range(5):
                ctx.state_id = f"state-flush-{i}"
                transform.process([row], ctx)

            # After all batches, cache should be empty (all evicted)
            assert len(transform._http_clients) == 0

            transform.close()


# ---------------------------------------------------------------------------
# Bug 3: Base LLM transform output schema diverges from output_schema_config
# ---------------------------------------------------------------------------


class TestLLMOutputSchemaDivergence:
    """Regression: output_schema must include LLM-added fields.

    output_schema_config.guaranteed_fields includes llm_response, _usage, _model
    but output_schema was a copy of input_schema and lacked these fields.
    This caused DAG validation failures for explicit-schema pipelines.
    """

    def test_build_augmented_output_schema_observed_passthrough(self) -> None:
        """_build_augmented_output_schema returns dynamic schema for observed mode."""
        schema_config = SchemaConfig(mode="observed", fields=None)
        result = _build_augmented_output_schema(
            base_schema_config=schema_config,
            response_field="llm_response",
            schema_name="TestObserved",
        )
        # Dynamic schema has no fields and allows extras
        assert len(result.model_fields) == 0
        assert result.model_config["extra"] == "allow"

    def test_llm_transform_has_augmented_output_schema(self) -> None:
        """LLMTransform output_schema differs from input_schema when explicit."""
        with patch("openai.AzureOpenAI"):
            transform = LLMTransform(
                {
                    "provider": "azure",
                    "deployment_name": "test",
                    "endpoint": "https://test.azure.com",
                    "api_key": "key",
                    "template": "hello",
                    "schema": {"mode": "flexible", "fields": ["text: str"]},
                    "required_input_fields": [],
                }
            )

        # output_schema should have LLM fields
        assert "llm_response" in transform.output_schema.model_fields
        # input_schema should not
        assert "llm_response" not in transform.input_schema.model_fields


# ---------------------------------------------------------------------------
# Bug 4: Terminal batch failures clear checkpoint without per-row LLM call recording
# ---------------------------------------------------------------------------


class TestAzureBatchTerminalFailureCallRecording:
    """Regression: terminal batch failures must record per-row LLM calls.

    When a batch fails/cancels/expires/times-out, per-row LLM call records
    must be emitted BEFORE the checkpoint is cleared, ensuring audit lineage
    completeness for submitted requests.
    """

    def _make_transform_and_ctx(self) -> tuple[Any, Mock]:
        """Create an AzureBatchLLMTransform and mock context for testing."""
        from elspeth.plugins.llm.azure_batch import AzureBatchLLMTransform

        config = {
            "deployment_name": "test-batch",
            "endpoint": "https://test.openai.azure.com",
            "api_key": "test-key",
            "template": "hello",
            "schema": DYNAMIC_SCHEMA,
            "required_input_fields": [],
        }

        transform = AzureBatchLLMTransform(config)

        ctx = Mock(spec=PluginContext)
        ctx.run_id = "run-1"
        ctx.state_id = "state-batch"
        ctx.record_call = Mock()
        ctx.telemetry_emit = Mock()
        ctx.get_checkpoint = Mock()
        ctx.set_checkpoint = Mock()
        ctx.clear_checkpoint = Mock()
        ctx.landscape = Mock()
        transform.on_start(ctx)

        return transform, ctx

    def _make_checkpoint(self, batch_id: str = "batch-123", submitted_at: str | None = None) -> BatchCheckpointState:
        """Create a realistic checkpoint with submitted requests."""
        from elspeth.contracts.batch_checkpoint import BatchCheckpointState, RowMappingEntry

        return BatchCheckpointState(
            batch_id=batch_id,
            input_file_id="file-abc",
            row_mapping={
                "row-0-abc12345": RowMappingEntry(index=0, variables_hash="hash0"),
                "row-1-def67890": RowMappingEntry(index=1, variables_hash="hash1"),
            },
            template_errors=[],
            submitted_at=submitted_at or datetime.now(UTC).isoformat(),
            row_count=2,
            requests={
                "row-0-abc12345": {
                    "model": "test-batch",
                    "messages": [{"role": "user", "content": "hello row 0"}],
                    "temperature": 0.0,
                },
                "row-1-def67890": {
                    "model": "test-batch",
                    "messages": [{"role": "user", "content": "hello row 1"}],
                    "temperature": 0.0,
                },
            },
        )

    def _assert_per_row_calls_recorded(self, ctx: Mock, expected_status: str) -> None:
        """Assert that per-row LLM call records were emitted with the expected batch status."""
        llm_calls = [c for c in ctx.record_call.call_args_list if c.kwargs.get("call_type") == CallType.LLM]
        assert len(llm_calls) == 2, f"Expected 2 per-row LLM calls, got {len(llm_calls)}"

        # Verify each call has the correct terminal status
        for llm_call in llm_calls:
            error = llm_call.kwargs["error"]
            assert error["reason"] == f"batch_{expected_status}"
            assert error["batch_id"] == "batch-123"
            assert llm_call.kwargs["status"] == CallStatus.ERROR
            assert llm_call.kwargs["provider"] == "azure"

    def test_failed_batch_records_per_row_calls(self) -> None:
        """Failed batch records per-row LLM calls before clearing checkpoint."""
        transform, ctx = self._make_transform_and_ctx()
        checkpoint = self._make_checkpoint()
        rows = [make_pipeline_row({"text": "row0"}), make_pipeline_row({"text": "row1"})]

        # Mock batch.status = "failed"
        mock_batch = Mock()
        mock_batch.id = "batch-123"
        mock_batch.status = "failed"
        mock_batch.errors = None

        with patch.object(transform, "_get_client") as mock_get_client:
            mock_client = Mock()
            mock_client.batches.retrieve.return_value = mock_batch
            mock_get_client.return_value = mock_client

            ctx.get_checkpoint.return_value = checkpoint
            result = transform._check_batch_status(checkpoint, rows, ctx)

        assert result.status == "error"
        self._assert_per_row_calls_recorded(ctx, "failed")

    def test_cancelled_batch_records_per_row_calls(self) -> None:
        """Cancelled batch records per-row LLM calls before clearing checkpoint."""
        transform, ctx = self._make_transform_and_ctx()
        checkpoint = self._make_checkpoint()
        rows = [make_pipeline_row({"text": "row0"}), make_pipeline_row({"text": "row1"})]

        mock_batch = Mock()
        mock_batch.id = "batch-123"
        mock_batch.status = "cancelled"

        with patch.object(transform, "_get_client") as mock_get_client:
            mock_client = Mock()
            mock_client.batches.retrieve.return_value = mock_batch
            mock_get_client.return_value = mock_client

            result = transform._check_batch_status(checkpoint, rows, ctx)

        assert result.status == "error"
        self._assert_per_row_calls_recorded(ctx, "cancelled")

    def test_expired_batch_records_per_row_calls(self) -> None:
        """Expired batch records per-row LLM calls before clearing checkpoint."""
        transform, ctx = self._make_transform_and_ctx()
        checkpoint = self._make_checkpoint()
        rows = [make_pipeline_row({"text": "row0"}), make_pipeline_row({"text": "row1"})]

        mock_batch = Mock()
        mock_batch.id = "batch-123"
        mock_batch.status = "expired"

        with patch.object(transform, "_get_client") as mock_get_client:
            mock_client = Mock()
            mock_client.batches.retrieve.return_value = mock_batch
            mock_get_client.return_value = mock_client

            result = transform._check_batch_status(checkpoint, rows, ctx)

        assert result.status == "error"
        self._assert_per_row_calls_recorded(ctx, "expired")

    def test_timeout_batch_records_per_row_calls(self) -> None:
        """Timed-out batch records per-row LLM calls before clearing checkpoint."""
        transform, ctx = self._make_transform_and_ctx()
        # Set submitted_at to far in the past to trigger timeout
        checkpoint = self._make_checkpoint(submitted_at="2020-01-01T00:00:00+00:00")

        rows = [make_pipeline_row({"text": "row0"}), make_pipeline_row({"text": "row1"})]

        # Status is "in_progress" but exceeded max_wait_hours
        mock_batch = Mock()
        mock_batch.id = "batch-123"
        mock_batch.status = "in_progress"
        mock_batch.output_file_id = None
        mock_batch.error_file_id = None

        with patch.object(transform, "_get_client") as mock_get_client:
            mock_client = Mock()
            mock_client.batches.retrieve.return_value = mock_batch
            mock_get_client.return_value = mock_client

            result = transform._check_batch_status(checkpoint, rows, ctx)

        assert result.status == "error"
        assert result.reason["reason"] == "batch_timeout"
        self._assert_per_row_calls_recorded(ctx, "batch_timeout")

    def test_per_row_calls_include_request_data(self) -> None:
        """Per-row failure calls include the original request data from checkpoint."""
        transform, ctx = self._make_transform_and_ctx()
        checkpoint = self._make_checkpoint()
        rows = [make_pipeline_row({"text": "row0"}), make_pipeline_row({"text": "row1"})]

        mock_batch = Mock()
        mock_batch.id = "batch-123"
        mock_batch.status = "failed"
        mock_batch.errors = None

        with patch.object(transform, "_get_client") as mock_get_client:
            mock_client = Mock()
            mock_client.batches.retrieve.return_value = mock_batch
            mock_get_client.return_value = mock_client

            transform._check_batch_status(checkpoint, rows, ctx)

        llm_calls = [c for c in ctx.record_call.call_args_list if c.kwargs.get("call_type") == CallType.LLM]

        # Verify request_data includes original request from checkpoint
        for llm_call in llm_calls:
            request_data = llm_call.kwargs["request_data"]
            assert "custom_id" in request_data
            assert "row_index" in request_data
            assert "model" in request_data
            assert "messages" in request_data

    def test_no_per_row_calls_when_no_requests(self) -> None:
        """No per-row calls emitted when checkpoint has no requests (all templates failed)."""
        transform, ctx = self._make_transform_and_ctx()
        from elspeth.contracts.batch_checkpoint import BatchCheckpointState

        checkpoint = BatchCheckpointState(
            batch_id="batch-empty",
            input_file_id="file-empty",
            row_mapping={},
            template_errors=[(0, "bad template")],
            submitted_at=datetime.now(UTC).isoformat(),
            row_count=1,
            requests={},
        )
        rows = [make_pipeline_row({"text": "row0"})]

        mock_batch = Mock()
        mock_batch.id = "batch-empty"
        mock_batch.status = "failed"
        mock_batch.errors = None

        with patch.object(transform, "_get_client") as mock_get_client:
            mock_client = Mock()
            mock_client.batches.retrieve.return_value = mock_batch
            mock_get_client.return_value = mock_client

            transform._check_batch_status(checkpoint, rows, ctx)

        # No per-row LLM calls should be emitted (only HTTP call for batches.retrieve)
        llm_calls = [c for c in ctx.record_call.call_args_list if c.kwargs.get("call_type") == CallType.LLM]
        assert len(llm_calls) == 0


# ---------------------------------------------------------------------------
# Bug 5: enable_content_recording accepted but never applied
# ---------------------------------------------------------------------------


class TestEnableContentRecording:
    """Regression: enable_content_recording must be wired to Azure Monitor setup.

    The config field was accepted and logged but never passed to the Azure
    Monitor SDK or environment variable, leaving it as a dead config field.

    Note on mocking strategy: _configure_azure_monitor() uses local imports:
    - `from azure.monitor.opentelemetry import configure_azure_monitor` (installed)
    - `from azure.ai.inference.tracing import AIInferenceInstrumentor` (NOT installed)

    Since configure_azure_monitor is imported inside the function body, we must
    patch it at the source module, not on elspeth.plugins.llm.azure. For
    AIInferenceInstrumentor, we inject a mock module into sys.modules since the
    real package is not installed.
    """

    def test_content_recording_wired_via_instrumentor(self) -> None:
        """enable_content_recording is passed to AIInferenceInstrumentor when available."""
        import sys

        from elspeth.plugins.llm.providers.azure import _configure_azure_monitor
        from elspeth.plugins.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(
            connection_string="InstrumentationKey=test-key",
            enable_content_recording=True,
            enable_live_metrics=False,
        )

        mock_instrumentor_instance = Mock()
        mock_instrumentor_class = Mock(return_value=mock_instrumentor_instance)

        # Inject a fake azure.ai.inference.tracing module so the local import succeeds
        mock_tracing_module = Mock()
        mock_tracing_module.AIInferenceInstrumentor = mock_instrumentor_class

        with (
            patch("azure.monitor.opentelemetry.configure_azure_monitor") as mock_az_monitor,
            patch.dict(sys.modules, {"azure.ai.inference.tracing": mock_tracing_module}),
        ):
            result = _configure_azure_monitor(config)

        assert result is True
        mock_az_monitor.assert_called_once_with(
            connection_string="InstrumentationKey=test-key",
            enable_live_metrics=False,
        )
        mock_instrumentor_instance.instrument.assert_called_once_with(
            enable_content_recording=True,
        )

    def test_content_recording_false_wired_via_instrumentor(self) -> None:
        """enable_content_recording=False is correctly passed through."""
        import sys

        from elspeth.plugins.llm.providers.azure import _configure_azure_monitor
        from elspeth.plugins.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(
            connection_string="InstrumentationKey=test-key",
            enable_content_recording=False,
            enable_live_metrics=False,
        )

        mock_instrumentor_instance = Mock()
        mock_instrumentor_class = Mock(return_value=mock_instrumentor_instance)

        mock_tracing_module = Mock()
        mock_tracing_module.AIInferenceInstrumentor = mock_instrumentor_class

        with (
            patch("azure.monitor.opentelemetry.configure_azure_monitor"),
            patch.dict(sys.modules, {"azure.ai.inference.tracing": mock_tracing_module}),
        ):
            _configure_azure_monitor(config)

        mock_instrumentor_instance.instrument.assert_called_once_with(
            enable_content_recording=False,
        )

    def test_content_recording_falls_back_to_env_var(self) -> None:
        """When AIInferenceInstrumentor is not available, falls back to env var.

        Since azure.ai.inference is not installed in the test environment,
        the ImportError path is the natural path. We just need to mock
        configure_azure_monitor and verify the env var is set.
        """
        import os

        from elspeth.plugins.llm.providers.azure import _configure_azure_monitor
        from elspeth.plugins.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(
            connection_string="InstrumentationKey=test-key",
            enable_content_recording=True,
            enable_live_metrics=False,
        )

        # Remove any injected mock from previous tests to ensure ImportError path
        env_key = "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"
        old_value = os.environ.pop(env_key, None)
        try:
            with patch("azure.monitor.opentelemetry.configure_azure_monitor"):
                _configure_azure_monitor(config)

            assert os.environ.get(env_key) == "true"
        finally:
            # Clean up
            os.environ.pop(env_key, None)
            if old_value is not None:
                os.environ[env_key] = old_value

    def test_content_recording_false_env_var(self) -> None:
        """enable_content_recording=False sets env var to 'false'."""
        import os

        from elspeth.plugins.llm.providers.azure import _configure_azure_monitor
        from elspeth.plugins.llm.tracing import AzureAITracingConfig

        config = AzureAITracingConfig(
            connection_string="InstrumentationKey=test-key",
            enable_content_recording=False,
            enable_live_metrics=False,
        )

        env_key = "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"
        old_value = os.environ.pop(env_key, None)
        try:
            with patch("azure.monitor.opentelemetry.configure_azure_monitor"):
                _configure_azure_monitor(config)

            assert os.environ.get(env_key) == "false"
        finally:
            # Clean up
            os.environ.pop(env_key, None)
            if old_value is not None:
                os.environ[env_key] = old_value
