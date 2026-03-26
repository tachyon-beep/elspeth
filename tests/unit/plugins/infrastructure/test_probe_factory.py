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

        mock_client = MagicMock()
        mock_client.get_collection.side_effect = ConnectionError("refused")

        with patch("chromadb.PersistentClient", return_value=mock_client):
            result = probe.probe()

        assert result.reachable is False
        assert "ConnectionError" in result.message

    def test_client_construction_failure_reports_unreachable(self) -> None:
        """Infrastructure failure during client creation is 'unreachable', not a bug."""
        probe = ChromaCollectionProbe("test", {"mode": "persistent", "persist_directory": "/nonexistent/path"})

        with patch("chromadb.PersistentClient", side_effect=OSError("Permission denied")):
            result = probe.probe()

        assert result.reachable is False
        assert "OSError" in result.message

    def test_client_mode_uses_http_client(self) -> None:
        """Client mode should use HttpClient instead of PersistentClient."""
        probe = ChromaCollectionProbe("remote", {"mode": "client", "host": "chroma.local", "port": 8000, "ssl": False})

        mock_collection = MagicMock()
        mock_collection.count.return_value = 5

        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection

        with patch("chromadb.HttpClient", return_value=mock_client) as mock_http_cls:
            result = probe.probe()

        mock_http_cls.assert_called_once_with(host="chroma.local", port=8000, ssl=False)
        assert result.reachable is True
        assert result.count == 5


class TestChromaCollectionProbeCrashThrough:
    """Verify that programming errors crash through (are NOT caught)."""

    def test_type_error_crashes_through(self) -> None:
        """TypeError from bad config usage must not be caught."""
        probe = ChromaCollectionProbe("test", {"mode": "persistent", "persist_directory": "./data"})

        mock_client = MagicMock()
        mock_client.get_collection.side_effect = TypeError("bad argument type")

        with (
            patch("chromadb.PersistentClient", return_value=mock_client),
            pytest.raises(TypeError, match="bad argument type"),
        ):
            probe.probe()

    def test_attribute_error_crashes_through(self) -> None:
        """AttributeError from code bug must not be caught."""
        probe = ChromaCollectionProbe("test", {"mode": "persistent", "persist_directory": "./data"})

        mock_client = MagicMock()
        mock_client.get_collection.side_effect = AttributeError("no such attr")

        with (
            patch("chromadb.PersistentClient", return_value=mock_client),
            pytest.raises(AttributeError, match="no such attr"),
        ):
            probe.probe()

    def test_key_error_in_config_crashes_through(self) -> None:
        """KeyError from missing config key (e.g. missing persist_directory) must crash."""
        probe = ChromaCollectionProbe("test", {"mode": "persistent"})

        with pytest.raises(KeyError, match="persist_directory"):
            probe.probe()
