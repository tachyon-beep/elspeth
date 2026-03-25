"""Tests for collection probe factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from elspeth.contracts.probes import CollectionProbe
from elspeth.core.dependency_config import CollectionProbeConfig
from elspeth.plugins.infrastructure.probe_factory import ChromaCollectionProbe, build_collection_probes


class TestBuildCollectionProbes:
    def test_builds_chroma_probe(self) -> None:
        configs = [
            CollectionProbeConfig(
                collection="test",
                provider="chroma",
                provider_config={"mode": "persistent", "persist_directory": "./data"},
            )
        ]
        probes = build_collection_probes(configs)
        assert len(probes) == 1
        assert isinstance(probes[0], CollectionProbe)
        assert probes[0].collection_name == "test"

    def test_empty_configs_returns_empty(self) -> None:
        assert build_collection_probes([]) == []

    def test_unknown_provider_raises(self) -> None:
        configs = [
            CollectionProbeConfig(
                collection="test",
                provider="unknown_provider",
                provider_config={},
            )
        ]
        with pytest.raises(ValueError, match="unknown_provider"):
            build_collection_probes(configs)

    def test_multiple_probes(self) -> None:
        configs = [
            CollectionProbeConfig(
                collection="a",
                provider="chroma",
                provider_config={"mode": "persistent", "persist_directory": "./a"},
            ),
            CollectionProbeConfig(
                collection="b",
                provider="chroma",
                provider_config={"mode": "persistent", "persist_directory": "./b"},
            ),
        ]
        probes = build_collection_probes(configs)
        assert len(probes) == 2
        assert probes[0].collection_name == "a"
        assert probes[1].collection_name == "b"


class TestChromaCollectionProbeBehavior:
    """Behavioral tests for ChromaCollectionProbe.probe() with mocked ChromaDB."""

    def test_collection_found_with_documents(self) -> None:
        probe = ChromaCollectionProbe("science", {"mode": "persistent", "persist_directory": "./data"})

        mock_collection = MagicMock()
        mock_collection.count.return_value = 42

        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection

        with patch("chromadb.PersistentClient", return_value=mock_client):
            result = probe.probe()

        assert result.reachable is True
        assert result.count == 42
        assert "42 documents" in result.message

    def test_collection_found_but_empty(self) -> None:
        probe = ChromaCollectionProbe("empty", {"mode": "persistent", "persist_directory": "./data"})

        mock_collection = MagicMock()
        mock_collection.count.return_value = 0

        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection

        with patch("chromadb.PersistentClient", return_value=mock_client):
            result = probe.probe()

        assert result.reachable is True
        assert result.count == 0
        assert "empty" in result.message

    def test_collection_not_found(self) -> None:
        import chromadb.errors

        probe = ChromaCollectionProbe("missing", {"mode": "persistent", "persist_directory": "./data"})

        mock_client = MagicMock()
        mock_client.get_collection.side_effect = chromadb.errors.NotFoundError("not found")

        with patch("chromadb.PersistentClient", return_value=mock_client):
            result = probe.probe()

        assert result.reachable is True
        assert result.count == 0
        assert "not found" in result.message

    def test_auth_error_reports_unreachable(self) -> None:
        """Auth errors must NOT report reachable=True (review finding #2)."""
        import chromadb.errors

        probe = ChromaCollectionProbe("secret", {"mode": "persistent", "persist_directory": "./data"})

        mock_client = MagicMock()
        mock_client.get_collection.side_effect = chromadb.errors.AuthorizationError("forbidden")

        with patch("chromadb.PersistentClient", return_value=mock_client):
            result = probe.probe()

        # Auth error falls through to outer handler → reachable=False
        assert result.reachable is False
        assert "AuthorizationError" in result.message

    def test_connection_failure_reports_unreachable(self) -> None:
        probe = ChromaCollectionProbe("test", {"mode": "persistent", "persist_directory": "./data"})

        with patch("chromadb.PersistentClient", side_effect=ConnectionError("refused")):
            result = probe.probe()

        assert result.reachable is False
        assert "ConnectionError" in result.message
