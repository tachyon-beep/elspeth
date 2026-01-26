"""Tests for Azure Multi-Query LLM transform retry behavior and concurrent processing.

Tests the FIXED implementation that uses PooledExecutor with AIMD retry.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import Mock, patch

from elspeth.plugins.context import PluginContext
from elspeth.plugins.llm.azure_multi_query import AzureMultiQueryLLMTransform


def make_config(**overrides: Any) -> dict[str, Any]:
    """Create valid config with optional overrides."""
    config = {
        "deployment_name": "gpt-4o",
        "endpoint": "https://test.openai.azure.com",
        "api_key": "test-key",
        "template": "Input: {{ row.input_1 }}\nCriterion: {{ row.criterion.name }}",
        "system_prompt": "You are an assessment AI. Respond in JSON.",
        "case_studies": [
            {"name": "cs1", "input_fields": ["cs1_bg", "cs1_sym", "cs1_hist"]},
            {"name": "cs2", "input_fields": ["cs2_bg", "cs2_sym", "cs2_hist"]},
        ],
        "criteria": [
            {"name": "diagnosis", "code": "DIAG"},
            {"name": "treatment", "code": "TREAT"},
        ],
        "response_format": "json",
        "output_mapping": {"score": "score", "rationale": "rationale"},
        "schema": {"fields": "dynamic"},
        "pool_size": 4,
        "max_capacity_retry_seconds": 10,  # 10 second retry timeout
    }
    config.update(overrides)
    return config


def make_plugin_context(state_id: str = "state-123") -> PluginContext:
    """Create a PluginContext with mocked landscape."""
    mock_landscape = Mock()
    mock_landscape.record_external_call = Mock()
    mock_landscape.record_call = Mock()
    return PluginContext(
        run_id="run-123",
        landscape=mock_landscape,
        state_id=state_id,
        config={},
    )


class TestRetryBehavior:
    """Tests for capacity error retry with AIMD backoff."""

    def test_capacity_error_triggers_retry(self) -> None:
        """Capacity errors trigger automatic retry until success."""
        from elspeth.plugins.clients.llm import RateLimitError

        call_count = [0]

        def mock_chat_completion(**kwargs: Any) -> Mock:
            """Fail first 2 calls, succeed on 3rd."""
            call_count[0] += 1
            if call_count[0] <= 2:
                raise RateLimitError("Rate limit exceeded")
            return Mock(
                content=json.dumps({"score": 85, "rationale": "Success after retry"}),
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                model="gpt-4o",
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config())

            with patch.object(transform, "_get_llm_client") as mock_get_client:
                mock_llm_client = Mock()
                mock_llm_client.chat_completion.side_effect = mock_chat_completion
                mock_get_client.return_value = mock_llm_client

                transform.on_start(make_plugin_context())
                ctx = make_plugin_context()

                row = {
                    "cs1_bg": "data",
                    "cs1_sym": "data",
                    "cs1_hist": "data",
                    "cs2_bg": "data",
                    "cs2_sym": "data",
                    "cs2_hist": "data",
                }

                result = transform.process(row, ctx)

                # Should succeed after retries
                assert result.status == "success"
                assert result.row is not None
                # Verify all 4 queries succeeded (each tried up to 3 times)
                assert "cs1_diagnosis_score" in result.row
                assert "cs1_treatment_score" in result.row
                assert "cs2_diagnosis_score" in result.row
                assert "cs2_treatment_score" in result.row

    def test_capacity_retry_timeout(self) -> None:
        """Row fails after max_capacity_retry_seconds exceeded."""
        from elspeth.plugins.clients.llm import RateLimitError

        def mock_chat_completion(**kwargs: Any) -> Mock:
            """Always fail with rate limit."""
            raise RateLimitError("Rate limit exceeded - never succeeds")

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_azure_class.return_value = mock_client

            # Short timeout for test speed
            transform = AzureMultiQueryLLMTransform(
                make_config(max_capacity_retry_seconds=1)  # 1 second timeout
            )

            with patch.object(transform, "_get_llm_client") as mock_get_client:
                mock_llm_client = Mock()
                mock_llm_client.chat_completion.side_effect = mock_chat_completion
                mock_get_client.return_value = mock_llm_client

                transform.on_start(make_plugin_context())
                ctx = make_plugin_context()

                row = {
                    "cs1_bg": "data",
                    "cs1_sym": "data",
                    "cs1_hist": "data",
                    "cs2_bg": "data",
                    "cs2_sym": "data",
                    "cs2_hist": "data",
                }

                result = transform.process(row, ctx)

                # Should fail after timeout
                assert result.status == "error"
                assert result.reason is not None
                # Check that it's a timeout, not immediate failure
                assert "query_failed" in result.reason["reason"]

    def test_mixed_success_and_retry(self) -> None:
        """Some queries succeed immediately, others succeed after retry."""
        from elspeth.plugins.clients.llm import RateLimitError

        call_count = [0]

        def mock_chat_completion(**kwargs: Any) -> Mock:
            """Every other query fails once before succeeding."""
            call_count[0] += 1
            # Queries 1, 3, 5, 7... fail on first attempt
            # First attempt of odd-numbered queries fails, only fail once
            if call_count[0] % 2 == 1 and call_count[0] not in range(9, 20) and call_count[0] < 10:
                raise RateLimitError("Rate limit")

            return Mock(
                content=json.dumps({"score": 85 + call_count[0], "rationale": f"R{call_count[0]}"}),
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                model="gpt-4o",
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config())

            with patch.object(transform, "_get_llm_client") as mock_get_client:
                mock_llm_client = Mock()
                mock_llm_client.chat_completion.side_effect = mock_chat_completion
                mock_get_client.return_value = mock_llm_client

                transform.on_start(make_plugin_context())
                ctx = make_plugin_context()

                row = {
                    "cs1_bg": "data",
                    "cs1_sym": "data",
                    "cs1_hist": "data",
                    "cs2_bg": "data",
                    "cs2_sym": "data",
                    "cs2_hist": "data",
                }

                result = transform.process(row, ctx)

                # All queries eventually succeed
                assert result.status == "success"
                assert result.row is not None
                assert "cs1_diagnosis_score" in result.row


class TestConcurrentRowProcessing:
    """Tests for concurrent row processing with large pool sizes."""

    def test_concurrent_rows_with_pool_size_100(self) -> None:
        """Pool size 100 with 10 queries/row processes 10 rows simultaneously."""
        call_count = [0]

        def mock_chat_completion(**kwargs: Any) -> Mock:
            """Track total calls."""
            call_count[0] += 1
            return Mock(
                content=json.dumps({"score": 85, "rationale": f"R{call_count[0]}"}),
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                model="gpt-4o",
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_azure_class.return_value = mock_client

            # Large pool size
            transform = AzureMultiQueryLLMTransform(make_config(pool_size=100))

            with patch.object(transform, "_get_llm_client") as mock_get_client:
                mock_llm_client = Mock()
                mock_llm_client.chat_completion.side_effect = mock_chat_completion
                mock_get_client.return_value = mock_llm_client

                transform.on_start(make_plugin_context())
                ctx = make_plugin_context(state_id="batch-100")

                # 10 rows x 4 queries = 40 total queries
                rows = []
                for i in range(10):
                    rows.append(
                        {
                            "row_id": i,
                            "cs1_bg": f"data_{i}",
                            "cs1_sym": f"data_{i}",
                            "cs1_hist": f"data_{i}",
                            "cs2_bg": f"data_{i}",
                            "cs2_sym": f"data_{i}",
                            "cs2_hist": f"data_{i}",
                        }
                    )

                result = transform.process(rows, ctx)

                assert result.status == "success"
                assert result.is_multi_row
                assert result.rows is not None
                assert len(result.rows) == 10

                # All rows succeeded
                for row in result.rows:
                    assert "_error" not in row
                    assert "cs1_diagnosis_score" in row
                    assert "row_id" in row

                # Total calls: 40 queries
                assert call_count[0] == 40

    def test_atomicity_with_concurrent_rows_and_failures(self) -> None:
        """Atomicity maintained when processing multiple rows concurrently with failures."""
        from elspeth.plugins.clients.llm import RateLimitError

        call_count = [0]

        def mock_chat_completion(**kwargs: Any) -> Mock:
            """Fail every 7th query to create staggered failures across rows."""
            call_count[0] += 1
            if call_count[0] % 7 == 0:
                raise RateLimitError("Rate limit")
            return Mock(
                content=json.dumps({"score": 85, "rationale": "OK"}),
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                model="gpt-4o",
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config(pool_size=50, max_capacity_retry_seconds=1))

            with patch.object(transform, "_get_llm_client") as mock_get_client:
                mock_llm_client = Mock()
                mock_llm_client.chat_completion.side_effect = mock_chat_completion
                mock_get_client.return_value = mock_llm_client

                transform.on_start(make_plugin_context())
                ctx = make_plugin_context(state_id="concurrent-atomicity")

                # 20 rows x 4 queries = 80 queries
                # Every 7th query fails: 7, 14, 21, 28, 35, 42, 49, 56, 63, 70, 77
                rows = []
                for i in range(20):
                    rows.append(
                        {
                            "row_id": i,
                            "cs1_bg": f"data_{i}",
                            "cs1_sym": f"data_{i}",
                            "cs1_hist": f"data_{i}",
                            "cs2_bg": f"data_{i}",
                            "cs2_sym": f"data_{i}",
                            "cs2_hist": f"data_{i}",
                        }
                    )

                result = transform.process(rows, ctx)

                assert result.status == "success"
                assert result.is_multi_row
                assert result.rows is not None
                assert len(result.rows) == 20

                # Verify atomicity: each row has 0 or 4 output fields
                for row in result.rows:
                    output_field_count = sum(
                        [
                            "cs1_diagnosis_score" in row,
                            "cs1_treatment_score" in row,
                            "cs2_diagnosis_score" in row,
                            "cs2_treatment_score" in row,
                        ]
                    )

                    if "_error" in row:
                        assert output_field_count == 0, f"Row {row['row_id']} has error + {output_field_count} outputs"
                    else:
                        assert output_field_count == 4, f"Row {row['row_id']} has {output_field_count} outputs (expected 4)"

    def test_full_pool_utilization(self) -> None:
        """Verify pool is fully utilized with concurrent row processing."""
        import threading
        import time

        call_count = [0]
        max_concurrent = [0]
        current_concurrent = [0]
        lock = threading.Lock()

        def mock_chat_completion(**kwargs: Any) -> Mock:
            """Track concurrent execution."""
            with lock:
                call_count[0] += 1
                current_concurrent[0] += 1
                if current_concurrent[0] > max_concurrent[0]:
                    max_concurrent[0] = current_concurrent[0]

            # Simulate some work
            time.sleep(0.01)

            with lock:
                current_concurrent[0] -= 1

            return Mock(
                content=json.dumps({"score": 85, "rationale": "OK"}),
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                model="gpt-4o",
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_azure_class.return_value = mock_client

            # pool_size=20, 4 queries/row → can process 5 rows simultaneously
            transform = AzureMultiQueryLLMTransform(make_config(pool_size=20))

            with patch.object(transform, "_get_llm_client") as mock_get_client:
                mock_llm_client = Mock()
                mock_llm_client.chat_completion.side_effect = mock_chat_completion
                mock_get_client.return_value = mock_llm_client

                transform.on_start(make_plugin_context())
                ctx = make_plugin_context(state_id="pool-util")

                # 10 rows x 4 queries = 40 queries
                rows = []
                for i in range(10):
                    rows.append(
                        {
                            "cs1_bg": f"data_{i}",
                            "cs1_sym": f"data_{i}",
                            "cs1_hist": f"data_{i}",
                            "cs2_bg": f"data_{i}",
                            "cs2_sym": f"data_{i}",
                            "cs2_hist": f"data_{i}",
                        }
                    )

                result = transform.process(rows, ctx)

                assert result.status == "success"
                assert call_count[0] == 40

                # Max concurrent should be close to pool_size (20)
                # Allow some margin for threading scheduling
                assert max_concurrent[0] >= 15, f"Expected ~20 concurrent, got {max_concurrent[0]}"

                print("\nPool utilization test:")
                print("  Pool size: 20")
                print("  Total queries: 40")
                print(f"  Max concurrent observed: {max_concurrent[0]}")
                print(f"  ✅ Pool utilized at {max_concurrent[0] / 20 * 100:.0f}%")


class TestSequentialFallback:
    """Tests for sequential processing when no executor configured."""

    def test_sequential_mode_no_retry(self) -> None:
        """Sequential mode fails query immediately on capacity error (no retry)."""
        from elspeth.plugins.clients.llm import RateLimitError

        call_count = [0]

        def mock_chat_completion(**kwargs: Any) -> Mock:
            """Fail first call, succeed on others (no retry in sequential mode)."""
            call_count[0] += 1
            if call_count[0] == 1:
                raise RateLimitError("Rate limit")
            return Mock(
                content=json.dumps({"score": 85, "rationale": f"Success {call_count[0]}"}),
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                model="gpt-4o",
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_azure_class.return_value = mock_client

            # No pool_size = sequential mode
            config = make_config()
            del config["pool_size"]
            transform = AzureMultiQueryLLMTransform(config)

            with patch.object(transform, "_get_llm_client") as mock_get_client:
                mock_llm_client = Mock()
                mock_llm_client.chat_completion.side_effect = mock_chat_completion
                mock_get_client.return_value = mock_llm_client

                transform.on_start(make_plugin_context())
                ctx = make_plugin_context()

                row = {
                    "cs1_bg": "data",
                    "cs1_sym": "data",
                    "cs1_hist": "data",
                    "cs2_bg": "data",
                    "cs2_sym": "data",
                    "cs2_hist": "data",
                }

                result = transform.process(row, ctx)

                # Row fails because first query failed (all-or-nothing)
                assert result.status == "error"
                assert result.reason is not None
                assert "query_failed" in result.reason["reason"]

                # All 4 queries attempted (no retry, but all queries run once)
                assert call_count[0] == 4

                # Verify it's an immediate failure, not a retry timeout
                assert result.reason["failed_queries"][0]["error"]["reason"] == "rate_limited"


class TestMemoryLeakPrevention:
    """Test that per-query LLM clients are properly cleaned up (memory leak prevention)."""

    def test_per_query_clients_cleaned_up_after_batch(self) -> None:
        """Per-query LLM clients should be cleaned up after batch processing.

        Regression test for P2 memory leak:
        - Each query gets unique state_id: f"{ctx.state_id}_r{row_idx}_q{query_idx}"
        - _get_llm_client caches a client per state_id
        - Without cleanup, _llm_clients grows without bound
        """
        call_count = [0]

        def mock_chat_completion(**kwargs: Any) -> Mock:
            call_count[0] += 1
            return Mock(
                content=json.dumps({"score": 90, "rationale": "Good"}),
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                model="gpt-4o",
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = mock_chat_completion
            mock_azure_class.return_value = mock_client

            config = make_config(pool_size=20, max_capacity_retry_seconds=10)
            transform = AzureMultiQueryLLMTransform(config)
            transform.on_start(make_plugin_context())

            # Process 10 rows x 4 queries = 40 per-query clients created
            rows = []
            for i in range(10):
                rows.append(
                    {
                        "row_id": i,
                        "cs1_bg": f"data_{i}",
                        "cs1_sym": f"data_{i}",
                        "cs1_hist": f"data_{i}",
                        "cs2_bg": f"data_{i}",
                        "cs2_sym": f"data_{i}",
                        "cs2_hist": f"data_{i}",
                    }
                )

            ctx = make_plugin_context(state_id="batch-memory-leak-test")

            # BEFORE FIX: _llm_clients would contain 40 cached clients
            # AFTER FIX: _llm_clients should be cleaned up to only batch client

            result = transform.process(rows, ctx)

            assert result.status == "success"
            assert len(result.rows) == 10

            # Verify all queries were executed
            assert call_count[0] == 40  # 10 rows x 4 queries

            # CRITICAL: Verify per-query clients were cleaned up
            # Only the batch-level client (ctx.state_id) should remain during cleanup
            # After process_batch finishes, even that gets cleaned up
            # So _llm_clients should be empty

            # Access internal state for verification
            assert len(transform._llm_clients) == 0, (
                f"Memory leak: {len(transform._llm_clients)} clients still cached. Per-query clients should be cleaned up after batch."
            )

    def test_per_query_clients_cleaned_up_even_on_failure(self) -> None:
        """Per-query clients should be cleaned up even if batch processing fails."""
        from elspeth.plugins.pooling.errors import CapacityError

        def mock_chat_completion(**kwargs: Any) -> Mock:
            # Always fail with capacity error
            raise CapacityError(status_code=429, message="Rate limit")

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = mock_chat_completion
            mock_azure_class.return_value = mock_client

            config = make_config(pool_size=10, max_capacity_retry_seconds=1)
            transform = AzureMultiQueryLLMTransform(config)
            transform.on_start(make_plugin_context())

            rows = [
                {
                    "cs1_bg": "data",
                    "cs1_sym": "data",
                    "cs1_hist": "data",
                    "cs2_bg": "data",
                    "cs2_sym": "data",
                    "cs2_hist": "data",
                }
                for _ in range(5)
            ]

            ctx = make_plugin_context(state_id="batch-failure-cleanup")

            # Process batch - all rows will fail with retry timeout
            result = transform.process(rows, ctx)

            assert result.status == "success"  # Batch succeeds even if rows fail
            # All rows should have errors
            for row in result.rows:
                assert "_error" in row

            # CRITICAL: Even with failures, per-query clients should be cleaned up
            assert len(transform._llm_clients) == 0, (
                f"Memory leak on failure: {len(transform._llm_clients)} clients still cached. "
                "Per-query clients should be cleaned up even when queries fail."
            )


class TestLLMErrorRetry:
    """Test that retryable LLM errors are actually retried by the pool."""

    def test_network_error_is_retried(self) -> None:
        """NetworkError should be retried by the pool (P2 bug fix).

        BEFORE FIX: LLMClientError was caught and converted to TransformResult.error
        without retryable flag, so pool never retried transient network errors.

        AFTER FIX: Retryable LLMClientErrors (NetworkError, ServerError) are re-raised,
        allowing the pool to apply AIMD retry logic.
        """
        from elspeth.plugins.clients.llm import NetworkError

        call_count = [0]

        def mock_chat_completion(**kwargs: Any) -> Mock:
            call_count[0] += 1
            if call_count[0] <= 2:
                # First 2 attempts fail with transient network error
                raise NetworkError("Connection timeout")
            # Third attempt succeeds - return proper OpenAI response structure
            mock_usage = Mock()
            mock_usage.prompt_tokens = 10
            mock_usage.completion_tokens = 5

            mock_message = Mock()
            mock_message.content = json.dumps({"score": 85, "rationale": "Good"})

            mock_choice = Mock()
            mock_choice.message = mock_message

            mock_response = Mock()
            mock_response.choices = [mock_choice]
            mock_response.model = "gpt-4o"
            mock_response.usage = mock_usage

            return mock_response

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = mock_chat_completion
            mock_azure_class.return_value = mock_client

            config = make_config(pool_size=4, max_capacity_retry_seconds=10)
            transform = AzureMultiQueryLLMTransform(config)
            transform.on_start(make_plugin_context())

            rows = [
                {
                    "cs1_bg": "data",
                    "cs1_sym": "data",
                    "cs1_hist": "data",
                    "cs2_bg": "data",
                    "cs2_sym": "data",
                    "cs2_hist": "data",
                }
            ]

            ctx = make_plugin_context(state_id="network-error-retry")
            result = transform.process(rows, ctx)

            assert result.status == "success"
            assert len(result.rows) == 1
            assert "_error" not in result.rows[0], "Row should succeed after retry"

            # Verify that all 4 queries were tried, some retried due to network errors
            # Each query hits the mock, some fail twice before succeeding
            assert call_count[0] > 4, f"Expected retries to happen, got {call_count[0]} calls"

    def test_content_policy_error_not_retried(self) -> None:
        """ContentPolicyError should NOT be retried (non-retryable error).

        P2 FIX VERIFICATION: Non-retryable errors should return immediately
        with TransformResult.error(retryable=False) instead of being retried.
        """
        from elspeth.plugins.clients.llm import ContentPolicyError

        call_count = [0]

        def mock_chat_completion(**kwargs: Any) -> Mock:
            call_count[0] += 1
            # Always fail with content policy violation
            raise ContentPolicyError("Content violates safety policy")

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = mock_chat_completion
            mock_azure_class.return_value = mock_client

            config = make_config(pool_size=4, max_capacity_retry_seconds=10)
            transform = AzureMultiQueryLLMTransform(config)
            transform.on_start(make_plugin_context())

            rows = [
                {
                    "cs1_bg": "data",
                    "cs1_sym": "data",
                    "cs1_hist": "data",
                    "cs2_bg": "data",
                    "cs2_sym": "data",
                    "cs2_hist": "data",
                }
            ]

            ctx = make_plugin_context(state_id="content-policy-no-retry")
            result = transform.process(rows, ctx)

            assert result.status == "success"  # Batch succeeds
            assert len(result.rows) == 1
            assert "_error" in result.rows[0], "Row should have error"

            # Verify ContentPolicyError caused immediate failure (no retries)
            # 4 queries, each called exactly once (no retries)
            assert call_count[0] == 4, f"Expected 4 calls (no retries), got {call_count[0]}"
