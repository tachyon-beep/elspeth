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
            "document_field": "text",
            "id_field": "doc_id",
            "metadata_fields": ["topic"],
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

    def test_constructs_http_client_with_heartbeat(self) -> None:
        config = {
            "collection": "test-collection",
            "mode": "client",
            "host": "localhost",
            "port": 8000,
            "ssl": False,
            "field_mapping": {
                "document_field": "text",
                "id_field": "doc_id",
                "metadata_fields": [],
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
            mock_client.heartbeat.assert_called_once()

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

        assert result.artifact.content_hash is not None
        assert len(result.artifact.content_hash) == 64  # SHA-256 hex

    def test_empty_rows_returns_empty_artifact(self) -> None:
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        result = sink.write([], mock_ctx)

        assert result.artifact.metadata is not None
        assert result.artifact.metadata["row_count"] == 0
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

    def test_skip_audit_records_actual_rows_written(self) -> None:
        """Skip mode must record only the rows actually sent to ChromaDB."""
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": ["d1"]}
        sink = _make_sink_with_collection(mock_collection, on_duplicate="skip")

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        rows = [
            {"doc_id": "d1", "text": "Existing", "topic": "t"},
            {"doc_id": "d2", "text": "New", "topic": "t"},
        ]
        artifact = sink.write(rows, mock_ctx)

        # Artifact must reflect actual write, not full batch
        assert artifact.artifact.metadata is not None
        assert artifact.artifact.metadata["row_count"] == 1

        # Audit call must include skip info
        call_kwargs = mock_ctx.record_call.call_args.kwargs
        assert call_kwargs["request_data"]["row_count"] == 1  # Actual write, not full batch
        assert call_kwargs["request_data"]["batch_size"] == 2  # Full batch size
        assert call_kwargs["request_data"]["document_ids"] == ["d2"]  # Only written IDs
        assert call_kwargs["response_data"]["rows_written"] == 1
        assert call_kwargs["response_data"]["rows_skipped"] == 1
        assert call_kwargs["response_data"]["skipped_ids"] == ["d1"]

    def test_skip_content_hash_reflects_actual_payload(self) -> None:
        """Hash must be over the subset actually sent, not the full batch."""
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": ["d1"]}
        sink = _make_sink_with_collection(mock_collection, on_duplicate="skip")

        mock_ctx = MagicMock()
        rows = [
            {"doc_id": "d1", "text": "Existing", "topic": "t"},
            {"doc_id": "d2", "text": "New", "topic": "t"},
        ]
        skip_artifact = sink.write(rows, mock_ctx)

        # Write only d2 in overwrite mode — should produce the same hash
        mock_collection2 = MagicMock()
        sink2 = _make_sink_with_collection(mock_collection2)
        mock_ctx2 = MagicMock()
        overwrite_artifact = sink2.write([{"doc_id": "d2", "text": "New", "topic": "t"}], mock_ctx2)

        assert skip_artifact.artifact.content_hash == overwrite_artifact.artifact.content_hash


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
        # Error details must include exception info (#4)
        assert call_kwargs["error"]["type"] == "DuplicateDocumentError"
        assert "d1" in call_kwargs["error"]["message"]

    def test_duplicate_ids_stored_as_tuple(self) -> None:
        """DuplicateDocumentError.duplicate_ids must be immutable."""
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": ["d1"]}
        sink = _make_sink_with_collection(mock_collection, on_duplicate="error")

        mock_ctx = MagicMock()
        with pytest.raises(DuplicateDocumentError) as exc_info:
            sink.write([{"doc_id": "d1", "text": "A", "topic": "t"}], mock_ctx)

        assert isinstance(exc_info.value.duplicate_ids, tuple)


class TestChromaSinkAuditIntegrity:
    def test_audit_recording_failure_raises_audit_integrity_error(self) -> None:
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"
        mock_ctx.record_call.side_effect = RuntimeError("DB write failed")

        rows = [{"doc_id": "d1", "text": "Hello", "topic": "t"}]

        with pytest.raises(AuditIntegrityError, match="audit") as exc_info:
            sink.write(rows, mock_ctx)

        # The ChromaDB write still happened
        mock_collection.upsert.assert_called_once()
        # Exception chain preserved (#13)
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, RuntimeError)

    def test_error_path_audit_failure_raises_audit_integrity_error(self) -> None:
        """If error-path record_call also fails, AuditIntegrityError is raised."""
        import chromadb.errors

        mock_collection = MagicMock()
        mock_collection.upsert.side_effect = chromadb.errors.ChromaError("write failed")
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        mock_ctx.record_call.side_effect = RuntimeError("audit also broken")

        with pytest.raises(AuditIntegrityError, match="audit") as exc_info:
            sink.write([{"doc_id": "d1", "text": "A", "topic": "t"}], mock_ctx)

        # Exception chain preserved — audit_exc is the cause
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, RuntimeError)


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
        mock_client = MagicMock()
        sink._client = mock_client

        sink.close()

        assert sink._client is None
        assert sink._collection is None
        mock_client.clear_system_cache.assert_called_once()


class TestChromaSinkMetadataTypeValidation:
    """Metadata values must be str|int|float|bool|None — ChromaDB's constraint."""

    def test_valid_scalar_types_pass(self) -> None:
        """str, int, float, bool metadata values are accepted."""
        mock_collection = MagicMock()
        config = _make_config(
            field_mapping={
                "document_field": "text",
                "id_field": "doc_id",
                "metadata_fields": ["s", "i", "f", "b"],
            },
            schema={"mode": "flexible", "fields": ["doc_id: str", "text: str"]},
        )
        sink = ChromaSink(config)
        sink._collection = mock_collection

        mock_ctx = MagicMock()
        rows = [{"doc_id": "d1", "text": "hi", "s": "val", "i": 42, "f": 3.14, "b": True}]
        sink.write(rows, mock_ctx)

        mock_collection.upsert.assert_called_once()

    def test_none_metadata_value_passes(self) -> None:
        """None is a valid ChromaDB metadata value."""
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        rows = [{"doc_id": "d1", "text": "hi", "topic": None}]
        sink.write(rows, mock_ctx)

        mock_collection.upsert.assert_called_once()

    def test_invalid_type_filtered_and_audit_recorded(self) -> None:
        """Rows with non-scalar metadata are filtered out, not sent to ChromaDB."""
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        rows = [
            {"doc_id": "d1", "text": "good", "topic": "science"},
            {"doc_id": "d2", "text": "bad", "topic": {"nested": "dict"}},
            {"doc_id": "d3", "text": "good", "topic": "math"},
        ]
        result = sink.write(rows, mock_ctx)

        # Only valid rows sent to ChromaDB
        call_kwargs = mock_collection.upsert.call_args.kwargs
        assert call_kwargs["ids"] == ["d1", "d3"]
        assert call_kwargs["documents"] == ["good", "good"]

        # Audit trail records the rejection
        audit_kwargs = mock_ctx.record_call.call_args.kwargs
        response = audit_kwargs["response_data"]
        assert response["rows_written"] == 2
        assert response["rows_rejected_metadata"] == 1
        assert response["rejected_metadata_detail"][0]["document_id"] == "d2"
        assert "topic" in response["rejected_metadata_detail"][0]["invalid_fields"]

        assert result is not None

    def test_all_rows_rejected_returns_zero_write(self) -> None:
        """When ALL rows have bad metadata, return zero-write artifact."""
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        rows = [
            {"doc_id": "d1", "text": "bad", "topic": ["a", "list"]},
            {"doc_id": "d2", "text": "bad", "topic": {"nested": "dict"}},
        ]
        result = sink.write(rows, mock_ctx)

        # Nothing sent to ChromaDB
        mock_collection.upsert.assert_not_called()
        mock_collection.add.assert_not_called()

        # Audit trail records all rejections
        audit_kwargs = mock_ctx.record_call.call_args.kwargs
        response = audit_kwargs["response_data"]
        assert response["rows_written"] == 0
        assert response["rows_rejected_metadata"] == 2

        assert result.artifact.metadata["row_count"] == 0

    @pytest.mark.parametrize(
        "bad_value, expected_type_name",
        [
            ({"nested": "dict"}, "dict"),
            (["a", "list"], "list"),
            ((1, 2), "tuple"),
        ],
        ids=["dict", "list", "tuple"],
    )
    def test_rejection_detail_includes_type_name(self, bad_value: Any, expected_type_name: str) -> None:
        """Rejection detail records the actual type name for diagnosis."""
        mock_collection = MagicMock()
        sink = _make_sink_with_collection(mock_collection)

        mock_ctx = MagicMock()
        rows = [{"doc_id": "d1", "text": "hi", "topic": bad_value}]
        sink.write(rows, mock_ctx)

        audit_kwargs = mock_ctx.record_call.call_args.kwargs
        detail = audit_kwargs["response_data"]["rejected_metadata_detail"][0]
        assert detail["invalid_fields"]["topic"] == expected_type_name
        assert detail["document_id"] == "d1"

    def test_no_metadata_fields_skips_validation(self) -> None:
        """When metadata_fields is empty, no validation needed (metadatas=None)."""
        mock_collection = MagicMock()
        config = _make_config(
            field_mapping={"document_field": "text", "id_field": "doc_id", "metadata_fields": []},
        )
        sink = ChromaSink(config)
        sink._collection = mock_collection

        mock_ctx = MagicMock()
        rows = [{"doc_id": "d1", "text": "hi"}]
        sink.write(rows, mock_ctx)

        mock_collection.upsert.assert_called_once()
