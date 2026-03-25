"""Tests for ChromaSink plugin lifecycle and write operations."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from elspeth.plugins.sinks.chroma_sink import ChromaSink


def _make_config() -> dict[str, Any]:
    return {
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
