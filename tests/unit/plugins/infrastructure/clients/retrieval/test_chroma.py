"""Tests for ChromaDB retrieval provider.

These tests use real ChromaDB ephemeral clients — no mocks needed.
ChromaDB's in-memory mode is fast enough for unit tests (~5ms per query).

Note on collection isolation: chromadb.Client() shares a global in-memory backend
across all instances in a process. Each test helper generates a unique collection
name to prevent cross-test interference.
"""

import uuid

import pytest

chromadb = pytest.importorskip("chromadb")

from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError  # noqa: E402
from elspeth.plugins.infrastructure.clients.retrieval.chroma import (  # noqa: E402
    ChromaSearchProvider,
    ChromaSearchProviderConfig,
)
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk  # noqa: E402


class TestChromaSearchProviderConfig:
    def test_minimal_valid_config(self):
        config = ChromaSearchProviderConfig(collection="test-docs")
        assert config.collection == "test-docs"
        assert config.mode == "ephemeral"

    def test_persistent_requires_path(self):
        with pytest.raises(ValueError, match="persist_directory"):
            ChromaSearchProviderConfig(collection="test", mode="persistent")

    def test_persistent_with_path(self):
        config = ChromaSearchProviderConfig(collection="test", mode="persistent", persist_directory="/tmp/chroma")
        assert config.persist_directory == "/tmp/chroma"

    def test_client_mode_requires_host(self):
        with pytest.raises(ValueError, match="host"):
            ChromaSearchProviderConfig(collection="test", mode="client")

    def test_client_mode_with_host(self):
        config = ChromaSearchProviderConfig(
            collection="test",
            mode="client",
            host="localhost",
            port=8000,
        )
        assert config.host == "localhost"

    def test_client_mode_requires_https_for_non_localhost(self):
        with pytest.raises(ValueError, match="ssl"):
            ChromaSearchProviderConfig(
                collection="test",
                mode="client",
                host="chroma.example.com",
                port=443,
                ssl=False,
            )

    def test_client_mode_allows_http_for_localhost(self):
        config = ChromaSearchProviderConfig(
            collection="test",
            mode="client",
            host="localhost",
            port=8000,
            ssl=False,
        )
        assert config.ssl is False

    def test_collection_name_validation(self):
        with pytest.raises(ValueError, match="alphanumeric"):
            ChromaSearchProviderConfig(collection="bad/name!")

    def test_valid_distance_functions(self):
        for fn in ("cosine", "l2", "ip"):
            config = ChromaSearchProviderConfig(
                collection="test",
                distance_function=fn,
            )
            assert config.distance_function == fn

    def test_path_traversal_rejected(self):
        with pytest.raises(ValueError, match="must not contain"):
            ChromaSearchProviderConfig(
                collection="test",
                mode="persistent",
                persist_directory="/tmp/../etc/chroma",
            )


class TestChromaSearchProvider:
    """Tests using real ephemeral ChromaDB — no mocks."""

    def _make_provider(self, documents=None, distance_function="cosine"):
        # Use unique collection name: chromadb.Client() shares a global in-memory
        # backend, so reusing names across tests causes collection state to bleed.
        unique_name = f"tc-{uuid.uuid4().hex[:12]}"
        config = ChromaSearchProviderConfig(
            collection=unique_name,
            mode="ephemeral",
            distance_function=distance_function,
        )
        provider = ChromaSearchProvider(config=config)

        if documents:
            collection = provider._collection
            # ChromaDB 1.x rejects empty metadata dicts — pass None when absent.
            metadatas = [d.get("metadata") or None for d in documents]
            collection.add(
                documents=[d["content"] for d in documents],
                ids=[d["id"] for d in documents],
                metadatas=metadatas,
            )

        return provider

    def test_search_returns_retrieval_chunks(self):
        provider = self._make_provider(
            documents=[
                {"id": "doc1", "content": "Python is a programming language"},
                {"id": "doc2", "content": "Java is a programming language"},
                {"id": "doc3", "content": "The weather is sunny today"},
            ]
        )
        chunks = provider.search(
            "programming languages",
            top_k=2,
            min_score=0.0,
            state_id="state-1",
            token_id="token-1",
        )
        assert len(chunks) <= 2
        assert all(isinstance(c, RetrievalChunk) for c in chunks)
        assert all(0.0 <= c.score <= 1.0 for c in chunks)

    def test_results_sorted_by_descending_score(self):
        provider = self._make_provider(documents=[{"id": f"doc{i}", "content": f"Document {i} about topic"} for i in range(5)])
        chunks = provider.search(
            "topic",
            top_k=5,
            min_score=0.0,
            state_id="state-1",
            token_id=None,
        )
        scores = [c.score for c in chunks]
        assert scores == sorted(scores, reverse=True)

    def test_min_score_filtering(self):
        provider = self._make_provider(
            documents=[
                {"id": "doc1", "content": "exact match for the query text"},
                {"id": "doc2", "content": "completely unrelated content about quantum physics"},
            ]
        )
        all_chunks = provider.search(
            "exact match for the query text",
            top_k=10,
            min_score=0.0,
            state_id="state-1",
            token_id=None,
        )
        high_chunks = provider.search(
            "exact match for the query text",
            top_k=10,
            min_score=0.9,
            state_id="state-1",
            token_id=None,
        )
        assert len(high_chunks) <= len(all_chunks)

    def test_top_k_limits_results(self):
        provider = self._make_provider(documents=[{"id": f"doc{i}", "content": f"Document about retrieval {i}"} for i in range(10)])
        chunks = provider.search(
            "retrieval",
            top_k=3,
            min_score=0.0,
            state_id="state-1",
            token_id=None,
        )
        assert len(chunks) <= 3

    def test_empty_collection_returns_empty(self):
        provider = self._make_provider(documents=[])
        chunks = provider.search(
            "anything",
            top_k=5,
            min_score=0.0,
            state_id="state-1",
            token_id=None,
        )
        assert chunks == []

    def test_source_id_matches_document_id(self):
        provider = self._make_provider(
            documents=[
                {"id": "my-doc-42", "content": "Test document content"},
            ]
        )
        chunks = provider.search(
            "test document",
            top_k=1,
            min_score=0.0,
            state_id="state-1",
            token_id=None,
        )
        assert len(chunks) == 1
        assert chunks[0].source_id == "my-doc-42"

    def test_metadata_preserved(self):
        provider = self._make_provider(
            documents=[
                {"id": "doc1", "content": "Test content", "metadata": {"page": 3, "section": "intro"}},
            ]
        )
        chunks = provider.search(
            "test content",
            top_k=1,
            min_score=0.0,
            state_id="state-1",
            token_id=None,
        )
        assert len(chunks) == 1
        assert chunks[0].metadata["page"] == 3
        assert chunks[0].metadata["section"] == "intro"

    def test_distance_function_mismatch_raises(self, tmp_path):
        """Uses PersistentClient so both providers share the same backing store."""
        config_cosine = ChromaSearchProviderConfig(
            collection="mismatch-test",
            mode="persistent",
            persist_directory=str(tmp_path),
            distance_function="cosine",
        )
        provider_cosine = ChromaSearchProvider(config=config_cosine)
        provider_cosine._collection.add(documents=["test"], ids=["doc1"])

        config_l2 = ChromaSearchProviderConfig(
            collection="mismatch-test",
            mode="persistent",
            persist_directory=str(tmp_path),
            distance_function="l2",
        )
        with pytest.raises(RetrievalError, match="distance_function"):
            ChromaSearchProvider(config=config_l2)

    def test_close_does_not_raise(self):
        provider = self._make_provider()
        provider.close()

    def test_is_retrieval_provider(self):
        from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalProvider

        provider = self._make_provider()
        assert isinstance(provider, RetrievalProvider)

    def test_fewer_docs_than_top_k(self):
        provider = self._make_provider(
            documents=[
                {"id": "doc1", "content": "First document"},
                {"id": "doc2", "content": "Second document"},
            ]
        )
        chunks = provider.search(
            "document",
            top_k=5,
            min_score=0.0,
            state_id="state-1",
            token_id=None,
        )
        assert len(chunks) <= 2

    def test_search_records_call(self):
        """Chroma search calls must be recorded in the audit trail."""
        from unittest.mock import MagicMock

        unique_name = f"ta-{uuid.uuid4().hex[:12]}"
        config = ChromaSearchProviderConfig(
            collection=unique_name,
            mode="ephemeral",
            distance_function="cosine",
        )
        mock_recorder = MagicMock()
        provider = ChromaSearchProvider(
            config=config,
            recorder=mock_recorder,
            run_id="run-1",
        )
        provider._collection.add(documents=["test doc"], ids=["doc1"])
        provider.search(
            "test",
            top_k=1,
            min_score=0.0,
            state_id="state-1",
            token_id="token-1",
        )
        mock_recorder.record_call.assert_called_once()


class TestChromaScoreNormalization:
    def _make_provider(self, distance_function):
        # Unique name per call — chromadb.Client() shares a global in-memory backend.
        unique_name = f"tsn-{uuid.uuid4().hex[:12]}"
        config = ChromaSearchProviderConfig(
            collection=unique_name,
            mode="ephemeral",
            distance_function=distance_function,
        )
        provider = ChromaSearchProvider(config=config)
        provider._collection.add(documents=["test document"], ids=["doc1"])
        return provider

    def test_cosine_scores_in_unit_range(self):
        provider = self._make_provider("cosine")
        chunks = provider.search(
            "test document",
            top_k=1,
            min_score=0.0,
            state_id="s1",
            token_id=None,
        )
        assert all(0.0 <= c.score <= 1.0 for c in chunks)

    def test_l2_scores_in_unit_range(self):
        provider = self._make_provider("l2")
        chunks = provider.search(
            "test document",
            top_k=1,
            min_score=0.0,
            state_id="s1",
            token_id=None,
        )
        assert all(0.0 <= c.score <= 1.0 for c in chunks)

    def test_ip_scores_in_unit_range(self):
        provider = self._make_provider("ip")
        chunks = provider.search(
            "test document",
            top_k=1,
            min_score=0.0,
            state_id="s1",
            token_id=None,
        )
        assert all(0.0 <= c.score <= 1.0 for c in chunks)


# =============================================================================
# Bug fix tests: chroma.py bug cluster
# =============================================================================


class TestCallTypeCorrectness:
    """Tests for elspeth-6b3dea5d77: CallType.SQL mislabels vector DB calls."""

    def test_audit_call_uses_vector_call_type(self):
        """Chroma search should record CallType.VECTOR, not CallType.SQL."""
        from unittest.mock import MagicMock

        from elspeth.contracts.enums import CallType

        unique_name = f"tct-{uuid.uuid4().hex[:12]}"
        config = ChromaSearchProviderConfig(
            collection=unique_name,
            mode="ephemeral",
            distance_function="cosine",
        )
        mock_recorder = MagicMock()
        provider = ChromaSearchProvider(
            config=config,
            recorder=mock_recorder,
            run_id="run-1",
        )
        provider._collection.add(documents=["test doc"], ids=["doc1"])
        provider.search(
            "test",
            top_k=1,
            min_score=0.0,
            state_id="state-1",
            token_id="token-1",
        )
        mock_recorder.record_call.assert_called_once()
        assert mock_recorder.record_call.call_args.kwargs["call_type"] == CallType.VECTOR


class TestTier3ResultBoundary:
    """Tests for elspeth-edd8710550: unguarded index on Tier 3 results dict."""

    def test_malformed_results_raises_retrieval_error(self):
        """If ChromaDB SDK returns unexpected structure, should get RetrievalError, not KeyError."""
        from unittest.mock import patch

        unique_name = f"t3r-{uuid.uuid4().hex[:12]}"
        config = ChromaSearchProviderConfig(
            collection=unique_name,
            mode="ephemeral",
        )
        provider = ChromaSearchProvider(config=config)
        provider._collection.add(documents=["test doc"], ids=["doc1"])

        # Simulate malformed SDK response — missing 'documents' key
        with (
            patch.object(provider._collection, "query", return_value={"ids": [["doc1"]]}),
            pytest.raises(RetrievalError),
        ):
            provider.search("test", top_k=1, min_score=0.0, state_id="s1", token_id=None)

    def test_none_inner_list_raises_retrieval_error(self):
        """If SDK returns None where inner list expected, should get RetrievalError."""
        from unittest.mock import patch

        unique_name = f"t3n-{uuid.uuid4().hex[:12]}"
        config = ChromaSearchProviderConfig(
            collection=unique_name,
            mode="ephemeral",
        )
        provider = ChromaSearchProvider(config=config)
        provider._collection.add(documents=["test doc"], ids=["doc1"])

        with (
            patch.object(
                provider._collection,
                "query",
                return_value={"ids": [["doc1"]], "documents": None, "distances": [[0.1]], "metadatas": [[{}]]},
            ),
            pytest.raises(RetrievalError),
        ):
            provider.search("test", top_k=1, min_score=0.0, state_id="s1", token_id=None)

    def test_none_distances_raises_retrieval_error(self):
        """If SDK returns None for distances inner list, should get RetrievalError."""
        from unittest.mock import patch

        unique_name = f"t3d-{uuid.uuid4().hex[:12]}"
        config = ChromaSearchProviderConfig(
            collection=unique_name,
            mode="ephemeral",
        )
        provider = ChromaSearchProvider(config=config)
        provider._collection.add(documents=["test doc"], ids=["doc1"])

        with (
            patch.object(
                provider._collection,
                "query",
                return_value={"ids": [["doc1"]], "documents": [["test doc"]], "distances": None, "metadatas": [[{}]]},
            ),
            pytest.raises(RetrievalError),
        ):
            provider.search("test", top_k=1, min_score=0.0, state_id="s1", token_id=None)


class TestNonFiniteDistanceHandling:
    """Tests for elspeth-69632ec27f: NaN distance from corrupt index."""

    def _make_provider(self):
        unique_name = f"tnf-{uuid.uuid4().hex[:12]}"
        config = ChromaSearchProviderConfig(
            collection=unique_name,
            mode="ephemeral",
            distance_function="cosine",
        )
        provider = ChromaSearchProvider(config=config)
        return provider

    def test_nan_distance_raises_retrieval_error(self):
        """NaN distance from corrupt index should raise RetrievalError, not fabricate score=1.0."""
        provider = self._make_provider()
        # NaN in cosine normalization: max(0.0, min(1.0, 1.0 - (NaN/2))) = 1.0
        # This silently fabricates a perfect score — data fabrication.
        with pytest.raises(RetrievalError, match="non-finite"):
            provider._normalize_distance(float("nan"))

    def test_inf_distance_raises_retrieval_error(self):
        """Infinite distance from corrupt index should raise RetrievalError."""
        with pytest.raises(RetrievalError, match="non-finite"):
            self._make_provider()._normalize_distance(float("inf"))

    def test_negative_inf_distance_raises_retrieval_error(self):
        """Negative infinite distance should raise RetrievalError."""
        with pytest.raises(RetrievalError, match="non-finite"):
            self._make_provider()._normalize_distance(float("-inf"))

    def test_valid_distance_normalizes_correctly(self):
        """Normal finite distances should still normalize correctly.

        Cosine: similarity = 1 - (distance / 2), so 0.5 → 0.75.
        """
        provider = self._make_provider()
        score = provider._normalize_distance(0.5)
        assert score == pytest.approx(0.75)


class TestDistanceTypeValidation:
    """Tests for elspeth-d4f0e7eed6: distance type not validated before arithmetic."""

    @pytest.mark.parametrize(
        "bad_distance,desc",
        [
            ("0.5", "string"),
            (True, "bool_true"),
            (False, "bool_false"),
            ([0.5], "list"),
            ({"d": 0.5}, "dict"),
        ],
    )
    def test_non_numeric_distance_crashes_on_corrupt_index(self, bad_distance, desc):
        """ChromaDB is our infrastructure — corrupt distances must crash, not skip.

        Unlike Tier 3 external APIs where individual bad items are quarantined,
        ChromaDB returning non-numeric distances indicates index corruption or
        SDK bug. A pipeline completing with silently missing retrieval chunks
        is worse than a crash (silent wrong result).
        """
        from unittest.mock import patch

        unique_name = f"tdt-{uuid.uuid4().hex[:12]}"
        config = ChromaSearchProviderConfig(
            collection=unique_name,
            mode="ephemeral",
        )
        provider = ChromaSearchProvider(config=config)
        provider._collection.add(documents=["doc a", "doc b"], ids=["doc1", "doc2"])

        with (
            patch.object(
                provider._collection,
                "query",
                return_value={
                    "ids": [["doc1", "doc2"]],
                    "documents": [["doc a", "doc b"]],
                    "distances": [[bad_distance, 0.3]],
                    "metadatas": [[{}, {}]],
                },
            ),
            pytest.raises(RetrievalError, match="non-numeric distance"),
        ):
            provider.search("test", top_k=2, min_score=0.0, state_id="s1", token_id=None)


class TestDocTypeValidation:
    """Tests for elspeth-aaa99db4be: doc type unchecked."""

    def test_non_string_doc_skipped(self):
        """Non-string document content from Tier 3 should not enter pipeline."""
        from unittest.mock import patch

        unique_name = f"tdv-{uuid.uuid4().hex[:12]}"
        config = ChromaSearchProviderConfig(
            collection=unique_name,
            mode="ephemeral",
        )
        provider = ChromaSearchProvider(config=config)
        provider._collection.add(documents=["real doc"], ids=["doc1"])

        # Simulate SDK returning non-string document (corrupt index)
        with patch.object(
            provider._collection,
            "query",
            return_value={
                "ids": [["doc1", "doc2"]],
                "documents": [[12345, "real doc"]],  # 12345 is non-string
                "distances": [[0.1, 0.2]],
                "metadatas": [[{}, {}]],
            },
        ):
            chunks = provider.search("test", top_k=2, min_score=0.0, state_id="s1", token_id=None)
            # Non-string doc should be skipped; only "real doc" should appear
            assert all(isinstance(c.content, str) for c in chunks)
            assert len(chunks) == 1
            assert chunks[0].content == "real doc"
