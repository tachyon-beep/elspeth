"""Tests for RAGRetrievalTransform lifecycle and process flow."""

import json
from unittest.mock import MagicMock

import pytest

from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk
from elspeth.plugins.transforms.rag.transform import RAGRetrievalTransform


@pytest.fixture(autouse=True)
def _set_fingerprint_key(monkeypatch):
    """Ensure ELSPETH_FINGERPRINT_KEY is set for all tests."""
    monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "test-fingerprint-key-for-rag-tests")


def _make_transform(**overrides):
    """Create a transform with valid config."""
    config = {
        "output_prefix": "policy",
        "query_field": "question",
        "provider": "azure_search",
        "provider_config": {
            "endpoint": "https://test.search.windows.net",
            "index": "test-index",
            "api_key": "test-key",
        },
        "schema_config": {"mode": "observed"},
    }
    config.update(overrides)
    return RAGRetrievalTransform(config)


def _mock_ctx(state_id="state-1", token_id="token-1"):
    """Create a mock TransformContext."""
    ctx = MagicMock()
    ctx.state_id = state_id
    ctx.run_id = "run-1"
    token = MagicMock()
    token.token_id = token_id
    ctx.token = token
    ctx.contract = MagicMock()
    return ctx


def _mock_lifecycle_ctx():
    """Create a mock LifecycleContext."""
    ctx = MagicMock()
    ctx.run_id = "run-1"
    ctx.landscape = MagicMock()
    ctx.telemetry_emit = MagicMock()
    ctx.rate_limit_registry = None
    return ctx


def _make_row(data):
    """Create a real PipelineRow."""
    contract = SchemaContract(mode="OBSERVED", fields=())
    return PipelineRow(data, contract)


class TestTransformLifecycle:
    def test_close_before_on_start_does_not_raise(self):
        transform = _make_transform()
        transform.close()

    def test_declared_output_fields(self):
        transform = _make_transform()
        expected = frozenset(
            [
                "policy__rag_context",
                "policy__rag_score",
                "policy__rag_count",
                "policy__rag_sources",
            ]
        )
        assert transform.declared_output_fields == expected

    def test_output_schema_config_guaranteed_fields(self):
        transform = _make_transform()
        assert transform._output_schema_config is not None
        assert frozenset(transform._output_schema_config.guaranteed_fields) == frozenset(
            {
                "policy__rag_context",
                "policy__rag_score",
                "policy__rag_count",
                "policy__rag_sources",
            }
        )

    def test_state_id_guard(self):
        transform = _make_transform()
        lifecycle_ctx = _mock_lifecycle_ctx()
        transform.on_start(lifecycle_ctx)

        ctx = _mock_ctx(state_id=None)
        row = _make_row({"question": "test"})

        with pytest.raises(RuntimeError, match="state_id"):
            transform.process(row, ctx)


class TestProcessFlow:
    def _setup_transform_with_mock_provider(self, chunks=None, **config_overrides):
        transform = _make_transform(**config_overrides)
        lifecycle_ctx = _mock_lifecycle_ctx()
        transform.on_start(lifecycle_ctx)

        mock_provider = MagicMock()
        mock_provider.search.return_value = chunks or []
        transform._provider = mock_provider
        return transform, mock_provider

    def test_successful_retrieval(self):
        chunks = [
            RetrievalChunk(content="Result 1", score=0.9, source_id="doc1", metadata={}),
            RetrievalChunk(content="Result 2", score=0.7, source_id="doc2", metadata={}),
        ]
        transform, _ = self._setup_transform_with_mock_provider(chunks)
        row = _make_row({"question": "What is RAG?"})
        ctx = _mock_ctx()

        result = transform.process(row, ctx)

        assert result.status == "success"
        output = result.row.to_dict()
        assert "policy__rag_context" in output
        assert "1. Result 1" in output["policy__rag_context"]
        assert output["policy__rag_count"] == 2
        assert output["policy__rag_score"] == 0.9
        assert "policy__rag_sources" in output
        sources = json.loads(output["policy__rag_sources"])
        assert len(sources["sources"]) == 2

    def test_zero_results_quarantine(self):
        transform, _ = self._setup_transform_with_mock_provider(
            chunks=[],
            on_no_results="quarantine",
        )
        row = _make_row({"question": "obscure query"})
        ctx = _mock_ctx()

        result = transform.process(row, ctx)
        assert result.status == "error"
        assert result.reason["reason"] == "no_results"

    def test_zero_results_continue(self):
        transform, _ = self._setup_transform_with_mock_provider(
            chunks=[],
            on_no_results="continue",
        )
        row = _make_row({"question": "obscure query"})
        ctx = _mock_ctx()

        result = transform.process(row, ctx)

        assert result.status == "success"
        output = result.row.to_dict()
        assert output["policy__rag_context"] is None
        assert output["policy__rag_count"] == 0
        assert output["policy__rag_score"] is None

    def test_retryable_error_propagates(self):
        transform, mock_provider = self._setup_transform_with_mock_provider()
        mock_provider.search.side_effect = RetrievalError(
            "server error",
            retryable=True,
            status_code=500,
        )
        row = _make_row({"question": "test"})
        ctx = _mock_ctx()

        with pytest.raises(RetrievalError) as exc_info:
            transform.process(row, ctx)
        assert exc_info.value.retryable is True

    def test_non_retryable_error_returns_error_result(self):
        transform, mock_provider = self._setup_transform_with_mock_provider()
        mock_provider.search.side_effect = RetrievalError(
            "bad request",
            retryable=False,
            status_code=400,
        )
        row = _make_row({"question": "test"})
        ctx = _mock_ctx()

        result = transform.process(row, ctx)
        assert result.status == "error"
        assert result.reason["reason"] == "retrieval_failed"


class TestOnComplete:
    def test_emits_telemetry(self):
        transform = _make_transform()
        lifecycle_ctx = _mock_lifecycle_ctx()
        transform.on_start(lifecycle_ctx)
        transform.on_complete(lifecycle_ctx)
        lifecycle_ctx.telemetry_emit.assert_called_once()
        payload = lifecycle_ctx.telemetry_emit.call_args[0][0]
        assert payload["event"] == "rag_retrieval_complete"
        assert "run_id" in payload
        assert payload["total_queries"] == 0
        assert payload["quarantine_count"] == 0

    def test_zero_rows_no_statistics_error(self):
        """Welford accumulators with zero rows should not raise."""
        transform = _make_transform()
        lifecycle_ctx = _mock_lifecycle_ctx()
        transform.on_start(lifecycle_ctx)
        transform.on_complete(lifecycle_ctx)


class TestProcessGuards:
    def test_process_before_on_start_raises(self):
        transform = _make_transform()
        row = _make_row({"question": "test"})
        ctx = _mock_ctx()
        with pytest.raises(RuntimeError, match="before on_start"):
            transform.process(row, ctx)


def test_plugin_discoverable():
    """rag_retrieval is found by the plugin scanner."""
    from elspeth.plugins.infrastructure.discovery import PLUGIN_SCAN_CONFIG

    assert "transforms/rag" in PLUGIN_SCAN_CONFIG["transforms"]
