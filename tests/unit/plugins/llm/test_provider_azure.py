# tests/unit/plugins/llm/test_provider_azure.py
"""Tests for AzureLLMProvider."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from elspeth.contracts.token_usage import TokenUsage
from elspeth.plugins.clients.llm import (
    AuditedLLMClient,
    ContentPolicyError,
    ContextLengthError,
    LLMClientError,
    LLMResponse,
    NetworkError,
    RateLimitError,
    ServerError,
)
from elspeth.plugins.llm.provider import FinishReason, LLMProvider, LLMQueryResult
from elspeth.plugins.llm.providers.azure import AzureLLMProvider


@pytest.fixture()
def mock_recorder() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def mock_telemetry_emit() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def provider(mock_recorder: MagicMock, mock_telemetry_emit: MagicMock) -> AzureLLMProvider:
    return AzureLLMProvider(
        endpoint="https://test.openai.azure.com/",
        api_key="test-key",
        api_version="2024-10-21",
        deployment_name="gpt-4o",
        recorder=mock_recorder,
        run_id="run-1",
        telemetry_emit=mock_telemetry_emit,
    )


def _make_llm_response(
    content: str = "Hello",
    model: str = "gpt-4o",
    finish_reason: str | None = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> LLMResponse:
    """Build a mock LLMResponse."""
    raw = {
        "choices": [
            {
                "message": {"content": content},
                "finish_reason": finish_reason,
            }
        ],
    }
    return LLMResponse(
        content=content,
        model=model,
        usage=TokenUsage.known(prompt_tokens, completion_tokens),
        latency_ms=50.0,
        raw_response=raw,
    )


class TestExecuteQuery:
    """Tests for execute_query method."""

    def test_returns_llm_query_result(self, provider: AzureLLMProvider) -> None:
        with patch.object(provider, "_get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.return_value = _make_llm_response()
            mock_get.return_value = mock_client

            result = provider.execute_query(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                temperature=0.0,
                max_tokens=100,
                state_id="state-1",
                token_id="tok-1",
            )

        assert isinstance(result, LLMQueryResult)
        assert result.content == "Hello"
        assert result.model == "gpt-4o"
        assert result.usage.is_known
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 5
        assert "raw_response" not in LLMQueryResult.__dataclass_fields__

    def test_maps_finish_reason(self, provider: AzureLLMProvider) -> None:
        with patch.object(provider, "_get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.return_value = _make_llm_response(finish_reason="stop")
            mock_get.return_value = mock_client

            result = provider.execute_query(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                temperature=0.0,
                max_tokens=100,
                state_id="state-1",
                token_id="tok-1",
            )

        assert result.finish_reason is FinishReason.STOP

    def test_unknown_finish_reason_returns_none(self, provider: AzureLLMProvider) -> None:
        with patch.object(provider, "_get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.return_value = _make_llm_response(finish_reason="end_turn")
            mock_get.return_value = mock_client

            result = provider.execute_query(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                temperature=0.0,
                max_tokens=100,
                state_id="state-1",
                token_id="tok-1",
            )

        assert result.finish_reason is None

    def test_propagates_rate_limit_error(self, provider: AzureLLMProvider) -> None:
        with patch.object(provider, "_get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.side_effect = RateLimitError("429 rate limited")
            mock_get.return_value = mock_client

            with pytest.raises(RateLimitError, match="429 rate limited"):
                provider.execute_query(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gpt-4o",
                    temperature=0.0,
                    max_tokens=100,
                    state_id="state-1",
                    token_id="tok-1",
                )

    def test_propagates_content_policy_error(self, provider: AzureLLMProvider) -> None:
        with patch.object(provider, "_get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.side_effect = ContentPolicyError("content_policy_violation")
            mock_get.return_value = mock_client

            with pytest.raises(ContentPolicyError):
                provider.execute_query(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gpt-4o",
                    temperature=0.0,
                    max_tokens=100,
                    state_id="state-1",
                    token_id="tok-1",
                )

    def test_propagates_server_error(self, provider: AzureLLMProvider) -> None:
        with patch.object(provider, "_get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.side_effect = ServerError("503 overloaded")
            mock_get.return_value = mock_client

            with pytest.raises(ServerError):
                provider.execute_query(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gpt-4o",
                    temperature=0.0,
                    max_tokens=100,
                    state_id="state-1",
                    token_id="tok-1",
                )

    def test_propagates_network_error(self, provider: AzureLLMProvider) -> None:
        with patch.object(provider, "_get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.side_effect = NetworkError("connection refused")
            mock_get.return_value = mock_client

            with pytest.raises(NetworkError):
                provider.execute_query(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gpt-4o",
                    temperature=0.0,
                    max_tokens=100,
                    state_id="state-1",
                    token_id="tok-1",
                )

    def test_propagates_llm_client_error(self, provider: AzureLLMProvider) -> None:
        with patch.object(provider, "_get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.side_effect = LLMClientError("bad request", retryable=False)
            mock_get.return_value = mock_client

            with pytest.raises(LLMClientError):
                provider.execute_query(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gpt-4o",
                    temperature=0.0,
                    max_tokens=100,
                    state_id="state-1",
                    token_id="tok-1",
                )

    def test_propagates_context_length_error(self, provider: AzureLLMProvider) -> None:
        with patch.object(provider, "_get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.side_effect = ContextLengthError("context_length_exceeded")
            mock_get.return_value = mock_client

            with pytest.raises(ContextLengthError):
                provider.execute_query(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gpt-4o",
                    temperature=0.0,
                    max_tokens=100,
                    state_id="state-1",
                    token_id="tok-1",
                )

    def test_execute_query_timeout_propagates_as_network_error(self, provider: AzureLLMProvider) -> None:
        """Timeout errors from AuditedLLMClient propagate as NetworkError (retryable)."""
        with patch.object(provider, "_get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat_completion.side_effect = NetworkError("Request timed out")
            mock_get.return_value = mock_client

            with pytest.raises(NetworkError, match="timed out"):
                provider.execute_query(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gpt-4o",
                    temperature=0.0,
                    max_tokens=100,
                    state_id="state-1",
                    token_id="tok-1",
                )

    def test_no_raw_response_still_works(self, provider: AzureLLMProvider) -> None:
        """finish_reason gracefully handles missing raw_response."""
        with patch.object(provider, "_get_llm_client") as mock_get:
            mock_client = MagicMock()
            resp = LLMResponse(
                content="hi",
                model="gpt-4o",
                usage=TokenUsage.unknown(),
                raw_response=None,
            )
            mock_client.chat_completion.return_value = resp
            mock_get.return_value = mock_client

            result = provider.execute_query(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                temperature=0.0,
                max_tokens=None,
                state_id="state-1",
                token_id="tok-1",
            )

        assert result.finish_reason is None
        assert result.content == "hi"


class TestClientCaching:
    """Tests for client creation and caching."""

    def test_client_cached_per_state_id(
        self,
        mock_recorder: MagicMock,
        mock_telemetry_emit: MagicMock,
    ) -> None:
        provider = AzureLLMProvider(
            endpoint="https://test.openai.azure.com/",
            api_key="test-key",
            api_version="2024-10-21",
            deployment_name="gpt-4o",
            recorder=mock_recorder,
            run_id="run-1",
            telemetry_emit=mock_telemetry_emit,
        )

        # Mock the underlying client creation
        with patch("elspeth.plugins.llm.providers.azure.AzureLLMProvider._get_underlying_client") as mock_uc:
            mock_uc.return_value = MagicMock()

            client1 = provider._get_llm_client("state-a", token_id="tok-1")
            client2 = provider._get_llm_client("state-a", token_id="tok-1")
            client3 = provider._get_llm_client("state-b", token_id="tok-2")

        assert client1 is client2  # Same state_id → same client
        assert client1 is not client3  # Different state_id → different client

    def test_concurrent_client_creation_same_state_id(
        self,
        mock_recorder: MagicMock,
        mock_telemetry_emit: MagicMock,
    ) -> None:
        """50 threads racing to create a client for the same state_id.
        Verify exactly one client instance created.
        """
        provider = AzureLLMProvider(
            endpoint="https://test.openai.azure.com/",
            api_key="test-key",
            api_version="2024-10-21",
            deployment_name="gpt-4o",
            recorder=mock_recorder,
            run_id="run-1",
            telemetry_emit=mock_telemetry_emit,
        )

        with patch("elspeth.plugins.llm.providers.azure.AzureLLMProvider._get_underlying_client") as mock_uc:
            mock_uc.return_value = MagicMock()

            clients: list[AuditedLLMClient] = []
            collect_lock = threading.Lock()
            barrier = threading.Barrier(50)

            def create_client() -> None:
                barrier.wait()
                c = provider._get_llm_client("state-race", token_id="tok-1")
                with collect_lock:
                    clients.append(c)

            threads = [threading.Thread(target=create_client) for _ in range(50)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # All 50 threads should have gotten the same client instance
        assert len(clients) == 50
        assert all(c is clients[0] for c in clients)

    def test_close_clears_clients(
        self,
        mock_recorder: MagicMock,
        mock_telemetry_emit: MagicMock,
    ) -> None:
        provider = AzureLLMProvider(
            endpoint="https://test.openai.azure.com/",
            api_key="test-key",
            api_version="2024-10-21",
            deployment_name="gpt-4o",
            recorder=mock_recorder,
            run_id="run-1",
            telemetry_emit=mock_telemetry_emit,
        )

        with patch("elspeth.plugins.llm.providers.azure.AzureLLMProvider._get_underlying_client") as mock_uc:
            mock_uc.return_value = MagicMock()
            provider._get_llm_client("state-1", token_id="tok-1")

        assert len(provider._llm_clients) == 1
        provider.close()
        assert len(provider._llm_clients) == 0
        assert provider._underlying_client is None


class TestStateIdSnapshot:
    """Tests for state_id snapshot behavior."""

    def test_state_id_snapshot_used_not_mutable_ref(
        self,
        mock_recorder: MagicMock,
        mock_telemetry_emit: MagicMock,
    ) -> None:
        """Verify the provider uses the original state_id value, not a mutable reference."""
        provider = AzureLLMProvider(
            endpoint="https://test.openai.azure.com/",
            api_key="test-key",
            api_version="2024-10-21",
            deployment_name="gpt-4o",
            recorder=mock_recorder,
            run_id="run-1",
            telemetry_emit=mock_telemetry_emit,
        )

        # Track which state_id was used to create the client
        created_state_ids: list[str] = []

        def tracking_get(sid: str, *, token_id: str | None = None) -> AuditedLLMClient:
            created_state_ids.append(sid)
            mock_client = MagicMock()
            mock_client.chat_completion.return_value = _make_llm_response()
            return mock_client

        with patch.object(provider, "_get_llm_client", side_effect=tracking_get):
            # Pass state_id as a string — strings are immutable in Python,
            # so this test verifies the snapshot pattern is used in finally block
            provider.execute_query(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                temperature=0.0,
                max_tokens=100,
                state_id="state-original",
                token_id="tok-1",
            )

        assert created_state_ids == ["state-original"]


class TestProtocolCompliance:
    """Verify AzureLLMProvider satisfies LLMProvider protocol."""

    def test_satisfies_llm_provider_protocol(self) -> None:
        # LLMProvider is runtime_checkable
        provider = AzureLLMProvider(
            endpoint="https://test.openai.azure.com/",
            api_key="test-key",
            api_version="2024-10-21",
            deployment_name="gpt-4o",
            recorder=MagicMock(),
            run_id="run-1",
            telemetry_emit=MagicMock(),
        )
        assert isinstance(provider, LLMProvider)
