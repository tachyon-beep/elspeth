"""Tests for ChromaSink plugin lifecycle and write operations."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from elspeth.contracts.enums import CallStatus
from elspeth.contracts.errors import AuditIntegrityError, DuplicateDocumentError
from elspeth.plugins.sinks.chroma_sink import ChromaSink


def _make_config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "collection": "test-collection",
        "mode": "persistent",
        "persist_directory": "./test_chroma",
        "distance_function": "cosine",
        "field_mapping": {
            "document": "text",
            "id": "doc_id",
            "metadata": ["topic"],
        },
        "on_duplicate": "overwrite",
        "schema": {
            "mode": "fixed",
            "fields": ["doc_id: str", "text: str", "topic: str"],
        },
    }
    config.update(overrides)
    return config


def _make_sink_with_collection(mock_collection: MagicMock, **config_overrides: Any) -> ChromaSink:
    """Create a ChromaSink with a pre-set mock collection (skips on_start)."""
    sink = ChromaSink(_make_config(**config_overrides))
    sink._collection = mock_collection
    sink._run_id = "test-run"
    return sink


class TestChromaSinkOnStart:
    def test_constructs_persistent_client(self) -> None:
        sink = ChromaSink(_make_config())
        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"
        mock_ctx.telemetry_emit = MagicMock()

        with patch("elspeth.plugins.sinks.chroma_sink.chromadb") as mock_chromadb:
            mock_client = MagicMock()
            mock_chromadb.PersistentClient.return_value = mock_client
            mock_client.get_or_create_collection.return_value = MagicMock()

            sink.on_start(mock_ctx)

            mock_chromadb.PersistentClient.assert_called_once()

    def test_constructs_http_client(self) -> None:
        config = {
            "collection": "test-collection",
            "mode": "client",
            "host": "localhost",
            "port": 8000,
            "ssl": False,
            "field_mapping": {
                "document": "text",
                "id": "doc_id",
                "metadata": [],
            },
            "schema": {
                "mode": "fixed",
                "fields": ["doc_id: str", "text: str"],
            },
        }
        sink = ChromaSink(config)
        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"
        mock_ctx.telemetry_emit = MagicMock()

        with patch("elspeth.plugins.sinks.chroma_sink.chromadb") as mock_chromadb:
            mock_client = MagicMock()
            mock_chromadb.HttpClient.return_value = mock_client
            mock_client.get_or_create_collection.return_value = MagicMock()

            sink.on_start(mock_ctx)

            mock_chromadb.HttpClient.assert_called_once_with(
                host="localhost",
                port=8000,
                ssl=False,
            )

    def test_on_start_failure_raises(self) -> None:
        sink = ChromaSink(_make_config())
        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        with patch("elspeth.plugins.sinks.chroma_sink.chromadb") as mock_chromadb:
            mock_chromadb.PersistentClient.side_effect = RuntimeError("Connection refused")

            with pytest.raises(RuntimeError, match="Connection refused"):
                sink.on_start(mock_ctx)


class TestChromaSinkWriteOverwrite:
    def test_upserts_rows_with_correct_mapping(self) -> None:
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        rows = [
            {"doc_id": "d1", "text": "Hello world", "topic": "greeting"},
            {"doc_id": "d2", "text": "Goodbye", "topic": "farewell"},
        ]

        result = sink.write(rows, mock_ctx)

        mock_collection.upsert.assert_called_once()
        call_kwargs = mock_collection.upsert.call_args
        assert call_kwargs.kwargs["ids"] == ["d1", "d2"]
        assert call_kwargs.kwargs["documents"] == ["Hello world", "Goodbye"]
        assert call_kwargs.kwargs["metadatas"] == [
            {"topic": "greeting"},
            {"topic": "farewell"},
        ]
        assert result is not None

    def test_records_audit_call(self) -> None:
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        rows = [{"doc_id": "d1", "text": "Hello", "topic": "t"}]
        sink.write(rows, mock_ctx)

        mock_ctx.record_call.assert_called_once()
        call_kwargs = mock_ctx.record_call.call_args.kwargs
        assert call_kwargs["provider"] == "chromadb"

    def test_returns_artifact_with_content_hash(self) -> None:
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        rows = [{"doc_id": "d1", "text": "Hello", "topic": "t"}]
        result = sink.write(rows, mock_ctx)

        assert result.content_hash is not None
        assert len(result.content_hash) == 64  # SHA-256 hex

    def test_empty_rows_returns_empty_artifact(self) -> None:
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        result = sink.write([], mock_ctx)

        assert result.metadata is not None
        assert result.metadata["row_count"] == 0
        mock_collection.upsert.assert_not_called()


class TestChromaSinkWriteSkip:
    def test_skip_filters_existing_ids(self) -> None:
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": ["d1"]}
        sink = _make_sink_with_collection(mock_collection, on_duplicate="skip")

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        rows = [
            {"doc_id": "d1", "text": "Existing", "topic": "t"},
            {"doc_id": "d2", "text": "New", "topic": "t"},
        ]
        sink.write(rows, mock_ctx)

        mock_collection.add.assert_called_once()
        add_kwargs = mock_collection.add.call_args.kwargs
        assert add_kwargs["ids"] == ["d2"]
        assert add_kwargs["documents"] == ["New"]

    def test_skip_all_existing_does_not_call_add(self) -> None:
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": ["d1", "d2"]}
        sink = _make_sink_with_collection(mock_collection, on_duplicate="skip")

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        rows = [
            {"doc_id": "d1", "text": "A", "topic": "t"},
            {"doc_id": "d2", "text": "B", "topic": "t"},
        ]
        sink.write(rows, mock_ctx)

        mock_collection.add.assert_not_called()


class TestChromaSinkWriteError:
    def test_error_mode_raises_on_duplicates(self) -> None:
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": ["d1", "d3"]}
        sink = _make_sink_with_collection(mock_collection, on_duplicate="error")

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        rows = [
            {"doc_id": "d1", "text": "A", "topic": "t"},
            {"doc_id": "d2", "text": "B", "topic": "t"},
            {"doc_id": "d3", "text": "C", "topic": "t"},
        ]

        with pytest.raises(DuplicateDocumentError) as exc_info:
            sink.write(rows, mock_ctx)

        assert "d1" in exc_info.value.duplicate_ids
        assert "d3" in exc_info.value.duplicate_ids
        mock_collection.add.assert_not_called()

    def test_error_mode_succeeds_when_no_duplicates(self) -> None:
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": []}
        sink = _make_sink_with_collection(mock_collection, on_duplicate="error")

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        rows = [{"doc_id": "d1", "text": "A", "topic": "t"}]
        result = sink.write(rows, mock_ctx)

        mock_collection.add.assert_called_once()
        assert result is not None

    def test_error_mode_records_audit_before_raising(self) -> None:
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": ["d1"]}
        sink = _make_sink_with_collection(mock_collection, on_duplicate="error")

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        with pytest.raises(DuplicateDocumentError):
            sink.write([{"doc_id": "d1", "text": "A", "topic": "t"}], mock_ctx)

        mock_ctx.record_call.assert_called_once()
        call_kwargs = mock_ctx.record_call.call_args.kwargs
        assert call_kwargs["status"] is CallStatus.ERROR


class TestChromaSinkAuditIntegrity:
    def test_audit_recording_failure_raises_audit_integrity_error(self) -> None:
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"
        mock_ctx.record_call.side_effect = RuntimeError("DB write failed")

        rows = [{"doc_id": "d1", "text": "Hello", "topic": "t"}]

        with pytest.raises(AuditIntegrityError, match="audit"):
            sink.write(rows, mock_ctx)

        # The ChromaDB write still happened
        mock_collection.upsert.assert_called_once()


class TestChromaSinkFlush:
    def test_flush_is_noop(self) -> None:
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        sink.flush()

        mock_collection.assert_not_called()


class TestChromaSinkClose:
    def test_close_releases_resources(self) -> None:
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)
        sink._client = MagicMock()

        sink.close()

        assert sink._client is None
        assert sink._collection is None
