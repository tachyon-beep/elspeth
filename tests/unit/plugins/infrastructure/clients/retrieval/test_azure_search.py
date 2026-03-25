"""Tests for Azure AI Search provider."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from elspeth.plugins.infrastructure.clients.retrieval.azure_search import (
    AzureSearchProvider,
    AzureSearchProviderConfig,
)
from elspeth.plugins.infrastructure.clients.retrieval.base import RetrievalError
from elspeth.plugins.infrastructure.clients.retrieval.types import RetrievalChunk


class TestAzureSearchProviderConfig:
    def test_requires_https(self):
        with pytest.raises(ValueError, match="HTTPS"):
            AzureSearchProviderConfig(
                endpoint="http://test.search.windows.net",
                index="test",
                api_key="key",
            )

    def test_auth_mutual_exclusion(self):
        with pytest.raises(ValueError, match="only one"):
            AzureSearchProviderConfig(
                endpoint="https://test.search.windows.net",
                index="test",
                api_key="key",
                use_managed_identity=True,
            )

    def test_auth_required(self):
        with pytest.raises(ValueError, match="either"):
            AzureSearchProviderConfig(
                endpoint="https://test.search.windows.net",
                index="test",
            )

    def test_semantic_requires_config(self):
        with pytest.raises(ValueError, match="semantic_config"):
            AzureSearchProviderConfig(
                endpoint="https://test.search.windows.net",
                index="test",
                api_key="key",
                search_mode="semantic",
            )

    def test_index_name_validation(self):
        with pytest.raises(ValueError, match="alphanumeric"):
            AzureSearchProviderConfig(
                endpoint="https://test.search.windows.net",
                index="bad/path/../traversal",
                api_key="key",
            )

    def test_valid_index_names(self):
        for name in ["my-index", "index_v2", "MyIndex123"]:
            config = AzureSearchProviderConfig(
                endpoint="https://test.search.windows.net",
                index=name,
                api_key="key",
            )
            assert config.index == name


class TestAzureSearchProviderSearch:
    def _make_provider(self, search_mode="hybrid"):
        config = AzureSearchProviderConfig(
            endpoint="https://test.search.windows.net",
            index="test-index",
            api_key="test-key",
            search_mode=search_mode,
        )
        recorder = MagicMock()
        telemetry_emit = MagicMock()
        return AzureSearchProvider(
            config=config,
            recorder=recorder,
            run_id="run-1",
            telemetry_emit=telemetry_emit,
        )

    def test_returns_retrieval_chunks(self):
        provider = self._make_provider()
        mock_response = {
            "value": [
                {"@search.score": 5.0, "content": "Result 1", "id": "doc1"},
                {"@search.score": 3.0, "content": "Result 2", "id": "doc2"},
            ]
        }
        with patch.object(provider, "_execute_search", return_value=mock_response):
            chunks = provider.search(
                "test query",
                top_k=5,
                min_score=0.0,
                state_id="state-1",
                token_id="token-1",
            )
        assert len(chunks) == 2
        assert all(isinstance(c, RetrievalChunk) for c in chunks)
        assert chunks[0].score >= chunks[1].score

    def test_min_score_filtering(self):
        # Use keyword mode: range (0, 50). Score 30.0 -> 0.6, score 2.0 -> 0.04.
        provider = self._make_provider("keyword")
        mock_response = {
            "value": [
                {"@search.score": 30.0, "content": "High", "id": "doc1"},
                {"@search.score": 2.0, "content": "Low", "id": "doc2"},
            ]
        }
        with patch.object(provider, "_execute_search", return_value=mock_response):
            chunks = provider.search(
                "test",
                top_k=5,
                min_score=0.5,
                state_id="state-1",
                token_id=None,
            )
        assert len(chunks) == 1
        assert chunks[0].content == "High"

    def test_malformed_json_raises_retrieval_error(self):
        provider = self._make_provider()
        with patch.object(provider, "_execute_search", side_effect=RetrievalError("bad json", retryable=False)):
            with pytest.raises(RetrievalError) as exc_info:
                provider.search("test", top_k=5, min_score=0.0, state_id="s1", token_id=None)
            assert not exc_info.value.retryable

    def test_server_error_raises_retryable(self):
        provider = self._make_provider()
        with patch.object(
            provider,
            "_execute_search",
            side_effect=RetrievalError("server error", retryable=True, status_code=500),
        ):
            with pytest.raises(RetrievalError) as exc_info:
                provider.search("test", top_k=5, min_score=0.0, state_id="s1", token_id=None)
            assert exc_info.value.retryable
            assert exc_info.value.status_code == 500


class TestScoreNormalization:
    def _make_provider(self, search_mode="hybrid"):
        config = AzureSearchProviderConfig(
            endpoint="https://test.search.windows.net",
            index="test-index",
            api_key="test-key",
            search_mode=search_mode,
        )
        return AzureSearchProvider(
            config=config,
            recorder=MagicMock(),
            run_id="run-1",
            telemetry_emit=MagicMock(),
        )

    def test_keyword_mid_range(self):
        provider = self._make_provider("keyword")
        assert provider._normalize_score(25.0) == pytest.approx(0.5)

    def test_keyword_zero(self):
        provider = self._make_provider("keyword")
        assert provider._normalize_score(0.0) == 0.0

    def test_keyword_max(self):
        provider = self._make_provider("keyword")
        assert provider._normalize_score(50.0) == 1.0

    def test_keyword_exceeds_max_clamped(self):
        provider = self._make_provider("keyword")
        assert provider._normalize_score(200.0) == 1.0

    def test_negative_score_clamped_to_zero(self):
        provider = self._make_provider("keyword")
        assert provider._normalize_score(-5.0) == 0.0

    def test_vector_already_normalized(self):
        provider = self._make_provider("vector")
        assert provider._normalize_score(0.75) == pytest.approx(0.75)

    def test_semantic_range(self):
        config = AzureSearchProviderConfig(
            endpoint="https://test.search.windows.net",
            index="test-index",
            api_key="test-key",
            search_mode="semantic",
            semantic_config="my-semantic-config",
        )
        provider = AzureSearchProvider(
            config=config,
            recorder=MagicMock(),
            run_id="run-1",
            telemetry_emit=MagicMock(),
        )
        assert provider._normalize_score(2.0) == pytest.approx(0.5)

    def test_nan_score_raises_retrieval_error(self):
        provider = self._make_provider("keyword")
        with pytest.raises(RetrievalError, match="non-finite"):
            provider._normalize_score(float("nan"))

    def test_infinity_score_raises_retrieval_error(self):
        provider = self._make_provider("keyword")
        with pytest.raises(RetrievalError, match="non-finite"):
            provider._normalize_score(float("inf"))

    def test_negative_infinity_raises_retrieval_error(self):
        provider = self._make_provider("keyword")
        with pytest.raises(RetrievalError, match="non-finite"):
            provider._normalize_score(float("-inf"))


class TestBuildRequestBody:
    def _make_provider(self, search_mode="hybrid", **overrides):
        config_data = {
            "endpoint": "https://test.search.windows.net",
            "index": "test-index",
            "api_key": "test-key",
            "search_mode": search_mode,
        }
        config_data.update(overrides)
        if search_mode == "semantic":
            config_data.setdefault("semantic_config", "my-semantic-config")
        config = AzureSearchProviderConfig(**config_data)
        return AzureSearchProvider(
            config=config,
            recorder=MagicMock(),
            run_id="run-1",
            telemetry_emit=MagicMock(),
        )

    def test_keyword_body(self):
        provider = self._make_provider("keyword")
        body = provider._build_request_body("test query", top_k=5)
        assert body["search"] == "test query"
        assert body["top"] == 5
        assert "vectorQueries" not in body

    def test_vector_body(self):
        provider = self._make_provider("vector")
        body = provider._build_request_body("test query", top_k=3)
        assert "search" not in body
        assert body["vectorQueries"][0]["text"] == "test query"
        assert body["vectorQueries"][0]["k"] == 3

    def test_hybrid_body(self):
        provider = self._make_provider("hybrid")
        body = provider._build_request_body("test query", top_k=5)
        assert body["search"] == "test query"
        assert "vectorQueries" in body

    def test_semantic_body(self):
        provider = self._make_provider("semantic")
        body = provider._build_request_body("test query", top_k=5)
        assert body["queryType"] == "semantic"
        assert body["semanticConfiguration"] == "my-semantic-config"


class TestParseResponse:
    def _make_provider(self):
        config = AzureSearchProviderConfig(
            endpoint="https://test.search.windows.net",
            index="test-index",
            api_key="test-key",
        )
        return AzureSearchProvider(
            config=config,
            recorder=MagicMock(),
            run_id="run-1",
            telemetry_emit=MagicMock(),
        )

    def test_missing_value_key_raises(self):
        provider = self._make_provider()
        with pytest.raises(RetrievalError, match="missing 'value'"):
            provider._parse_response({}, min_score=0.0)

    def test_skips_items_without_score(self):
        provider = self._make_provider()
        response = {"value": [{"content": "text", "id": "doc1"}]}
        chunks, skipped = provider._parse_response(response, min_score=0.0)
        assert chunks == []
        assert len(skipped) == 1
        assert skipped[0]["reason"] == "missing_score"

    def test_skips_items_without_content(self):
        provider = self._make_provider()
        response = {"value": [{"@search.score": 5.0, "id": "doc1"}]}
        chunks, skipped = provider._parse_response(response, min_score=0.0)
        assert chunks == []
        assert len(skipped) == 1
        assert skipped[0]["reason"] == "missing_content"

    def test_skips_items_without_id(self):
        """Items with no id are skipped — no fabricated "unknown" source_id."""
        provider = self._make_provider()
        response = {
            "value": [
                {"@search.score": 5.0, "content": "text", "id": "doc1"},
                {"@search.score": 5.0, "content": "text", "@search.documentId": "doc2"},
                {"@search.score": 5.0, "content": "text"},  # no id at all
            ]
        }
        chunks, skipped = provider._parse_response(response, min_score=0.0)
        assert len(chunks) == 2
        assert {c.source_id for c in chunks} == {"doc1", "doc2"}
        assert len(skipped) == 1
        assert skipped[0]["reason"] == "missing_id"

    @pytest.mark.parametrize(
        "bad_score,desc",
        [
            ("high", "string"),
            (True, "bool_true"),
            (False, "bool_false"),
            ([1.0], "list"),
            ({"v": 1.0}, "dict"),
        ],
    )
    def test_non_numeric_score_skipped_at_tier3_boundary(self, bad_score, desc):
        """Tier 3 boundary: non-numeric @search.score must be skipped, not crash."""
        provider = self._make_provider()
        response = {
            "value": [
                {"@search.score": bad_score, "content": "text", "id": "doc1"},
                {"@search.score": 5.0, "content": "good", "id": "doc2"},
            ]
        }
        chunks, skipped = provider._parse_response(response, min_score=0.0)
        # Bad score item skipped; good item still returned
        assert len(chunks) == 1
        assert chunks[0].source_id == "doc2"
        assert any(s["reason"] == "invalid_score_type" for s in skipped)

    def test_results_sorted_by_descending_score(self):
        provider = self._make_provider()
        response = {
            "value": [
                {"@search.score": 1.0, "content": "low", "id": "d1"},
                {"@search.score": 40.0, "content": "high", "id": "d2"},
                {"@search.score": 10.0, "content": "mid", "id": "d3"},
            ]
        }
        chunks, _ = provider._parse_response(response, min_score=0.0)
        assert chunks[0].score >= chunks[1].score >= chunks[2].score


class TestAzureSearchProviderReadiness:
    """Tests for AzureSearchProvider.check_readiness()."""

    def _make_provider(self):
        config = AzureSearchProviderConfig(
            endpoint="https://test.search.windows.net",
            index="test-index",
            api_key="test-key",
        )
        return AzureSearchProvider(
            config=config,
            recorder=MagicMock(),
            run_id="run-1",
            telemetry_emit=MagicMock(),
        )

    def _mock_response(self, *, status_code=200, text="0"):
        resp = MagicMock()
        type(resp).status_code = PropertyMock(return_value=status_code)
        type(resp).text = PropertyMock(return_value=text)
        resp.raise_for_status = MagicMock()
        if status_code >= 400:
            import httpx

            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=MagicMock(),
                response=resp,
            )
        return resp

    def test_index_with_documents_is_ready(self) -> None:
        """Index exists and has documents."""
        from elspeth.contracts.probes import CollectionReadinessResult

        provider = self._make_provider()

        with patch("httpx.get", return_value=self._mock_response(text="42")):
            result = provider.check_readiness()

        assert isinstance(result, CollectionReadinessResult)
        assert result.reachable is True
        assert result.count == 42
        assert "42 documents" in result.message

    def test_empty_index_is_not_ready(self) -> None:
        """Index exists but is empty."""
        provider = self._make_provider()

        with patch("httpx.get", return_value=self._mock_response(text="0")):
            result = provider.check_readiness()

        assert result.reachable is True
        assert result.count == 0
        assert "empty" in result.message

    def test_index_not_found_404(self) -> None:
        """Index does not exist — 404 response."""
        provider = self._make_provider()

        with patch("httpx.get", return_value=self._mock_response(status_code=404)):
            result = provider.check_readiness()

        assert result.reachable is True
        assert result.count == 0
        assert "not found" in result.message.lower()

    def test_connection_error(self) -> None:
        """Azure Search is unreachable."""
        provider = self._make_provider()

        with patch("httpx.get", side_effect=ConnectionError("Connection refused")):
            result = provider.check_readiness()

        assert result.reachable is False
        assert result.count == 0
        assert "Connection refused" in result.message

    def test_auth_header_sent(self) -> None:
        """API key is included in the readiness probe request."""
        provider = self._make_provider()

        with patch("httpx.get", return_value=self._mock_response(text="10")) as mock_get:
            provider.check_readiness()

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs["headers"]["api-key"] == "test-key"

    def test_count_url_format(self) -> None:
        """Readiness probe uses the correct $count endpoint."""
        provider = self._make_provider()

        with patch("httpx.get", return_value=self._mock_response(text="5")) as mock_get:
            provider.check_readiness()

        url = mock_get.call_args.args[0]
        assert "/indexes/test-index/docs/$count" in url
        assert "api-version=2024-07-01" in url

    def test_non_integer_count_body(self) -> None:
        """Malformed $count response distinguishable from network failure."""
        provider = self._make_provider()

        with patch("httpx.get", return_value=self._mock_response(text="not-a-number")):
            result = provider.check_readiness()

        # Reachable (HTTP 200) but unparseable — distinct from unreachable
        assert result.reachable is True
        assert result.count == 0
        assert "non-integer" in result.message.lower()

    def test_server_error_during_probe(self) -> None:
        """HTTP 500 during readiness probe reports unreachable."""
        provider = self._make_provider()

        with patch("httpx.get", return_value=self._mock_response(status_code=500)):
            result = provider.check_readiness()

        assert result.reachable is False
        assert result.count == 0
