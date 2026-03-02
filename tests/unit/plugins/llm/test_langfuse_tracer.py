# tests/unit/plugins/llm/test_langfuse_tracer.py
"""Tests for LangfuseTracer extraction.

Verifies the extracted Langfuse tracing utilities work correctly:
- Factory returns correct tracer type based on config
- Active tracer records success/error with correct metadata
- No-op tracer is silent
- Failures are logged via structlog (No Silent Failures)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.transforms.llm.langfuse import (
    ActiveLangfuseTracer,
    LangfuseTracer,
    NoOpLangfuseTracer,
    create_langfuse_tracer,
)
from elspeth.plugins.transforms.llm.tracing import AzureAITracingConfig, LangfuseTracingConfig

# ── Factory tests ──────────────────────────────────────────────────


class TestCreateLangfuseTracer:
    """Tests for the create_langfuse_tracer factory."""

    def test_create_with_none_config_returns_noop(self) -> None:
        tracer = create_langfuse_tracer(
            transform_name="test_transform",
            tracing_config=None,
        )
        assert isinstance(tracer, NoOpLangfuseTracer)

    def test_create_with_non_langfuse_config_returns_noop(self) -> None:
        config = AzureAITracingConfig(connection_string="test")
        tracer = create_langfuse_tracer(
            transform_name="test_transform",
            tracing_config=config,
        )
        assert isinstance(tracer, NoOpLangfuseTracer)

    @patch.dict("sys.modules", {"langfuse": MagicMock()})
    def test_create_with_langfuse_config_returns_active_tracer(self) -> None:
        # Must import inside patched context so the langfuse import resolves
        from elspeth.plugins.transforms.llm.langfuse import (
            ActiveLangfuseTracer as PatchedActiveTracer,
        )
        from elspeth.plugins.transforms.llm.langfuse import (
            create_langfuse_tracer as patched_create,
        )

        config = LangfuseTracingConfig(
            public_key="pk-test",
            secret_key="sk-test",
            host="https://test.langfuse.com",
        )
        tracer = patched_create(
            transform_name="test_transform",
            tracing_config=config,
        )
        assert isinstance(tracer, PatchedActiveTracer)
        assert tracer.transform_name == "test_transform"

    def test_create_langfuse_not_installed_raises_runtime_error(self) -> None:
        import builtins

        config = LangfuseTracingConfig(
            public_key="pk-test",
            secret_key="sk-test",
        )

        real_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "langfuse":
                raise ImportError("No module named 'langfuse'")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=mock_import),
            pytest.raises(RuntimeError, match=r"langfuse.*not installed"),
        ):
            create_langfuse_tracer(
                transform_name="test_transform",
                tracing_config=config,
            )


# ── NoOp tracer tests ─────────────────────────────────────────────


class TestNoOpLangfuseTracer:
    """Tests for the no-op tracer implementation."""

    def test_noop_tracer_record_success_is_silent(self) -> None:
        tracer = NoOpLangfuseTracer()
        # Should not raise
        tracer.record_success(
            token_id="tok-1",
            query_name="test",
            prompt="hello",
            response_content="world",
            model="gpt-4",
            usage=TokenUsage.known(10, 20),
        )

    def test_noop_tracer_record_error_is_silent(self) -> None:
        tracer = NoOpLangfuseTracer()
        # Should not raise
        tracer.record_error(
            token_id="tok-1",
            query_name="test",
            prompt="hello",
            error_message="something failed",
            model="gpt-4",
        )

    def test_flush_when_noop_is_silent(self) -> None:
        tracer = NoOpLangfuseTracer()
        # Should not raise
        tracer.flush()

    def test_noop_tracer_matches_protocol_signature(self) -> None:
        """Verify NoOpLangfuseTracer has explicit parameter signatures.

        This ensures mypy can catch signature drift between Protocol and
        implementations — no *args/**kwargs escape hatches.
        """
        import inspect

        for method_name in ("record_success", "record_error", "flush"):
            protocol_sig = inspect.signature(getattr(LangfuseTracer, method_name))
            impl_sig = inspect.signature(getattr(NoOpLangfuseTracer, method_name))

            # Parameter names and kinds must match (ignoring self)
            protocol_params = [(name, p.kind, p.default) for name, p in protocol_sig.parameters.items() if name != "self"]
            impl_params = [(name, p.kind, p.default) for name, p in impl_sig.parameters.items() if name != "self"]

            assert protocol_params == impl_params, (
                f"NoOpLangfuseTracer.{method_name} signature drifted from Protocol: Protocol={protocol_params}, Impl={impl_params}"
            )


# ── Active tracer tests ───────────────────────────────────────────


class TestActiveLangfuseTracer:
    """Tests for the active Langfuse tracer."""

    def _make_tracer(self) -> tuple[Any, Any]:
        """Create an ActiveLangfuseTracer with a mock Langfuse client."""
        mock_client = MagicMock()
        # The context manager pattern: start_as_current_observation returns a context manager
        mock_span_cm = MagicMock()
        mock_generation_cm = MagicMock()
        mock_generation = MagicMock()
        mock_generation_cm.__enter__ = MagicMock(return_value=mock_generation)
        mock_generation_cm.__exit__ = MagicMock(return_value=False)
        mock_span_cm.__enter__ = MagicMock(return_value=MagicMock())
        mock_span_cm.__exit__ = MagicMock(return_value=False)

        # First call creates span, second creates generation
        mock_client.start_as_current_observation.side_effect = [mock_span_cm, mock_generation_cm]

        tracer = ActiveLangfuseTracer(transform_name="test_transform", client=mock_client)
        return tracer, mock_generation

    def test_record_success_creates_span_and_generation(self) -> None:
        tracer, mock_generation = self._make_tracer()

        tracer.record_success(
            token_id="tok-1",
            query_name="classify",
            prompt="Classify this",
            response_content="positive",
            model="gpt-4",
        )

        # Verify generation.update was called with output
        mock_generation.update.assert_called_once()
        call_kwargs = mock_generation.update.call_args[1]
        assert call_kwargs["output"] == "positive"

    def test_record_success_with_usage_updates_generation(self) -> None:
        tracer, mock_generation = self._make_tracer()

        tracer.record_success(
            token_id="tok-1",
            query_name="classify",
            prompt="Classify this",
            response_content="positive",
            model="gpt-4",
            usage=TokenUsage.known(10, 20),
        )

        call_kwargs = mock_generation.update.call_args[1]
        assert call_kwargs["usage_details"] == {"input": 10, "output": 20}

    def test_record_success_without_usage_skips_usage_details(self) -> None:
        tracer, mock_generation = self._make_tracer()

        tracer.record_success(
            token_id="tok-1",
            query_name="classify",
            prompt="Classify this",
            response_content="positive",
            model="gpt-4",
            usage=None,
        )

        call_kwargs = mock_generation.update.call_args[1]
        assert "usage_details" not in call_kwargs

    def test_record_success_with_latency_includes_metadata(self) -> None:
        tracer, mock_generation = self._make_tracer()

        tracer.record_success(
            token_id="tok-1",
            query_name="classify",
            prompt="Classify this",
            response_content="positive",
            model="gpt-4",
            latency_ms=42.5,
        )

        call_kwargs = mock_generation.update.call_args[1]
        assert call_kwargs["metadata"] == {"latency_ms": 42.5}

    def test_record_success_with_extra_metadata_merges(self) -> None:
        """Verify extra_metadata is merged into span metadata."""
        mock_client = MagicMock()
        mock_span_cm = MagicMock()
        mock_generation_cm = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=MagicMock())
        mock_span_cm.__exit__ = MagicMock(return_value=False)
        mock_generation_cm.__enter__ = MagicMock(return_value=MagicMock())
        mock_generation_cm.__exit__ = MagicMock(return_value=False)
        mock_client.start_as_current_observation.side_effect = [mock_span_cm, mock_generation_cm]

        tracer = ActiveLangfuseTracer(transform_name="test_transform", client=mock_client)

        tracer.record_success(
            token_id="tok-1",
            query_name="classify",
            prompt="test",
            response_content="result",
            model="gpt-4",
            extra_metadata={"deployment": "prod-east"},
        )

        # The first call to start_as_current_observation creates the span
        span_call_kwargs = mock_client.start_as_current_observation.call_args_list[0][1]
        assert span_call_kwargs["metadata"]["deployment"] == "prod-east"
        assert span_call_kwargs["metadata"]["token_id"] == "tok-1"

    def test_record_error_sets_error_level(self) -> None:
        tracer, mock_generation = self._make_tracer()

        tracer.record_error(
            token_id="tok-1",
            query_name="classify",
            prompt="Classify this",
            error_message="rate limited",
            model="gpt-4",
        )

        call_kwargs = mock_generation.update.call_args[1]
        assert call_kwargs["level"] == "ERROR"
        assert call_kwargs["status_message"] == "rate limited"

    def test_record_error_with_latency_includes_metadata(self) -> None:
        tracer, mock_generation = self._make_tracer()

        tracer.record_error(
            token_id="tok-1",
            query_name="classify",
            prompt="Classify this",
            error_message="timeout",
            model="gpt-4",
            latency_ms=5000.0,
        )

        call_kwargs = mock_generation.update.call_args[1]
        assert call_kwargs["metadata"] == {"latency_ms": 5000.0}

    def test_record_exception_logs_warning(self) -> None:
        """Tracing failures go to structlog only — No Silent Failures."""
        mock_client = MagicMock()
        mock_client.start_as_current_observation.side_effect = RuntimeError("Langfuse down")

        tracer = ActiveLangfuseTracer(transform_name="test_transform", client=mock_client)

        with patch("elspeth.plugins.transforms.llm.langfuse._handle_trace_failure") as mock_handler:
            tracer.record_success(
                token_id="tok-1",
                query_name="classify",
                prompt="test",
                response_content="result",
                model="gpt-4",
            )
            mock_handler.assert_called_once()
            assert mock_handler.call_args[0][0] == "langfuse_trace_failed"
            assert mock_handler.call_args[0][1] == "test_transform"
            assert isinstance(mock_handler.call_args[0][2], RuntimeError)

    def test_flush_calls_client_flush(self) -> None:
        mock_client = MagicMock()
        tracer = ActiveLangfuseTracer(transform_name="test_transform", client=mock_client)

        tracer.flush()
        mock_client.flush.assert_called_once()

    def test_flush_failure_logs_warning(self) -> None:
        """Flush failures should be logged, not raised — No Silent Failures."""
        mock_client = MagicMock()
        mock_client.flush.side_effect = RuntimeError("Flush failed")

        tracer = ActiveLangfuseTracer(transform_name="test_transform", client=mock_client)

        with patch("elspeth.plugins.transforms.llm.langfuse._handle_trace_failure") as mock_handler:
            tracer.flush()
            mock_handler.assert_called_once()
            assert mock_handler.call_args[0][0] == "langfuse_flush_failed"
            assert isinstance(mock_handler.call_args[0][2], RuntimeError)
