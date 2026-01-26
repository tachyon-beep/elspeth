"""Load testing and profiling for Azure Multi-Query LLM transform.

This module tests the transform under realistic load conditions to:
1. Verify correct behavior with many rows
2. Profile CPU and memory usage
3. Identify bottlenecks
4. Test parallel vs sequential execution
5. Verify rate limit handling
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import Mock, patch

import pytest

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


def make_mock_llm_response(score: int, rationale: str, delay_ms: float = 0) -> Mock:
    """Create a mock LLM response with optional artificial delay."""
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)

    content = json.dumps({"score": score, "rationale": rationale})

    mock_usage = Mock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5

    mock_message = Mock()
    mock_message.content = content

    mock_choice = Mock()
    mock_choice.message = mock_message

    mock_response = Mock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o"
    mock_response.usage = mock_usage
    mock_response.model_dump = Mock(return_value={"model": "gpt-4o"})

    return mock_response


class TestLoadScenarios:
    """Test plugin under various load scenarios."""

    @pytest.mark.slow
    def test_many_rows_parallel_execution(self) -> None:
        """Process 100 rows with 4 parallel queries each (400 total queries)."""
        row_count = 100
        queries_per_row = 4  # 2 case studies x 2 criteria

        call_count = [0]

        def make_response(**kwargs: Any) -> Mock:
            """Simulate LLM response with 50ms latency."""
            call_count[0] += 1
            # Simulate realistic API latency
            return make_mock_llm_response(
                score=85 + (call_count[0] % 10),
                rationale=f"Response {call_count[0]}",
                delay_ms=50,
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = make_response
            mock_azure_class.return_value = mock_client

            # Use pool_size=4 for parallel execution
            transform = AzureMultiQueryLLMTransform(make_config(pool_size=4))
            transform.on_start(make_plugin_context())
            ctx = make_plugin_context(state_id="batch-load-test")

            # Generate test rows
            rows = []
            for i in range(row_count):
                rows.append(
                    {
                        "cs1_bg": f"patient_{i}_bg",
                        "cs1_sym": f"patient_{i}_sym",
                        "cs1_hist": f"patient_{i}_hist",
                        "cs2_bg": f"patient_{i}_cs2_bg",
                        "cs2_sym": f"patient_{i}_cs2_sym",
                        "cs2_hist": f"patient_{i}_cs2_hist",
                    }
                )

            start_time = time.time()
            result = transform.process(rows, ctx)
            elapsed = time.time() - start_time

            # Verify results
            assert result.status == "success"
            assert result.is_multi_row
            assert result.rows is not None
            assert len(result.rows) == row_count

            # All rows should have output fields
            for row in result.rows:
                assert "cs1_diagnosis_score" in row
                assert "cs1_treatment_score" in row
                assert "cs2_diagnosis_score" in row
                assert "cs2_treatment_score" in row

            # Verify all queries executed
            assert call_count[0] == row_count * queries_per_row

            # With pool_size=4 and 50ms per query, 400 queries should take much less than 20s
            # (Sequential would be 400 * 0.05 = 20s, parallel should be ~5-6s)
            # This is a loose upper bound to avoid flakiness
            assert elapsed < 15, f"Parallel execution took too long: {elapsed:.2f}s"

            print("\nLoad test stats:")
            print(f"  Rows processed: {row_count}")
            print(f"  Queries per row: {queries_per_row}")
            print(f"  Total queries: {call_count[0]}")
            print(f"  Elapsed time: {elapsed:.2f}s")
            print(f"  Queries/second: {call_count[0] / elapsed:.2f}")

    @pytest.mark.slow
    def test_sequential_vs_parallel_performance(self) -> None:
        """Compare sequential vs parallel execution performance."""
        row_count = 10  # Smaller dataset for comparison
        queries_per_row = 4

        def run_test(pool_size: int | None) -> tuple[float, int]:
            """Run test with given pool_size, return (elapsed_time, total_calls)."""
            call_count = [0]

            def make_response(**kwargs: Any) -> Mock:
                call_count[0] += 1
                return make_mock_llm_response(
                    score=85,
                    rationale=f"Response {call_count[0]}",
                    delay_ms=50,
                )

            with patch("openai.AzureOpenAI") as mock_azure_class:
                mock_client = Mock()
                mock_client.chat.completions.create.side_effect = make_response
                mock_azure_class.return_value = mock_client

                if pool_size is not None:
                    config = make_config(pool_size=pool_size)
                else:
                    # Sequential execution (no pool)
                    config = make_config()
                    del config["pool_size"]

                transform = AzureMultiQueryLLMTransform(config)
                transform.on_start(make_plugin_context())
                ctx = make_plugin_context()

                rows = []
                for i in range(row_count):
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

                start_time = time.time()
                result = transform.process(rows, ctx)
                elapsed = time.time() - start_time

                assert result.status == "success"
                assert result.is_multi_row
                assert result.rows is not None
                assert len(result.rows) == row_count

                return elapsed, call_count[0]

        # Test both modes
        sequential_time, sequential_calls = run_test(pool_size=None)
        parallel_time, parallel_calls = run_test(pool_size=4)

        # Both should execute same number of queries
        assert sequential_calls == parallel_calls == row_count * queries_per_row

        # Parallel should be faster (with 4 workers and 50ms delay, expect ~4x speedup)
        # Use conservative threshold to avoid flakiness
        speedup = sequential_time / parallel_time
        assert speedup > 1.5, f"Expected parallel to be faster, got speedup of {speedup:.2f}x"

        print("\nSequential vs Parallel comparison:")
        print(f"  Sequential time: {sequential_time:.2f}s")
        print(f"  Parallel time (pool_size=4): {parallel_time:.2f}s")
        print(f"  Speedup: {speedup:.2f}x")

    @pytest.mark.slow
    def test_memory_usage_with_large_batch(self) -> None:
        """Verify plugin doesn't accumulate excessive memory with large batches."""
        import gc

        try:
            import psutil
        except ImportError:
            pytest.skip("psutil not installed - skipping memory test")

        process = psutil.Process()

        row_count = 200
        call_count = [0]

        def make_response(**kwargs: Any) -> Mock:
            call_count[0] += 1
            # Return small responses (shouldn't accumulate much memory)
            return make_mock_llm_response(
                score=85,
                rationale="Short response",
                delay_ms=10,
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = make_response
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config(pool_size=4))
            transform.on_start(make_plugin_context())

            # Measure baseline memory
            gc.collect()
            baseline_mb = process.memory_info().rss / 1024 / 1024

            # Process batch
            rows = []
            for i in range(row_count):
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

            ctx = make_plugin_context(state_id="batch-memory-test")
            result = transform.process(rows, ctx)

            assert result.status == "success"

            # Measure after processing
            gc.collect()
            after_mb = process.memory_info().rss / 1024 / 1024

            memory_increase_mb = after_mb - baseline_mb

            # Should not leak excessive memory (conservative threshold)
            # With 200 rows x 4 queries = 800 results, expect < 100MB increase
            assert memory_increase_mb < 100, f"Memory increased by {memory_increase_mb:.2f} MB (baseline: {baseline_mb:.2f} MB)"

            print("\nMemory usage:")
            print(f"  Baseline: {baseline_mb:.2f} MB")
            print(f"  After {row_count} rows: {after_mb:.2f} MB")
            print(f"  Increase: {memory_increase_mb:.2f} MB")

    def test_rate_limit_error_handling(self) -> None:
        """Verify plugin handles rate limit errors correctly."""
        from elspeth.plugins.clients.llm import RateLimitError

        call_count = [0]

        def make_response(**kwargs: Any) -> Mock:
            """Simulate rate limit on every 3rd call."""
            call_count[0] += 1
            if call_count[0] % 3 == 0:
                raise Exception("Rate limit exceeded")
            return make_mock_llm_response(score=85, rationale="OK")

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = make_response
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config())

            # Mock the LLM client to raise RateLimitError
            with patch.object(transform, "_get_llm_client") as mock_get_client:
                mock_llm_client = Mock()

                # Counter for tracking which call we're on
                llm_call_count = [0]

                def mock_chat_completion(**kwargs: Any) -> Mock:
                    llm_call_count[0] += 1
                    if llm_call_count[0] % 3 == 0:
                        raise RateLimitError("Rate limit exceeded")
                    return Mock(
                        content=json.dumps({"score": 85, "rationale": "OK"}),
                        usage={"prompt_tokens": 10, "completion_tokens": 5},
                        model="gpt-4o",
                    )

                mock_llm_client.chat_completion.side_effect = mock_chat_completion
                mock_get_client.return_value = mock_llm_client

                ctx = make_plugin_context()

                row = {
                    "cs1_bg": "data",
                    "cs1_sym": "data",
                    "cs1_hist": "data",
                    "cs2_bg": "data",
                    "cs2_sym": "data",
                    "cs2_hist": "data",
                }

                # Process will fail because one of the 4 queries hits rate limit
                result = transform.process(row, ctx)

                # All-or-nothing: entire row should fail
                assert result.status == "error"
                assert result.reason is not None
                assert "query_failed" in result.reason["reason"]

    def test_client_caching_behavior(self) -> None:
        """Verify LLM client caching works correctly."""
        call_count = [0]

        def make_response(**kwargs: Any) -> Mock:
            call_count[0] += 1
            return make_mock_llm_response(score=85, rationale=f"Response {call_count[0]}")

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = make_response
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config())
            transform.on_start(make_plugin_context())

            # Track how many times we create underlying AzureOpenAI client
            azure_client_creations = mock_azure_class.call_count

            # Process multiple rows with same state_id
            ctx = make_plugin_context(state_id="shared-state")

            for i in range(3):
                row = {
                    "cs1_bg": f"data_{i}",
                    "cs1_sym": f"data_{i}",
                    "cs1_hist": f"data_{i}",
                    "cs2_bg": f"data_{i}",
                    "cs2_sym": f"data_{i}",
                    "cs2_hist": f"data_{i}",
                }
                result = transform.process(row, ctx)
                assert result.status == "success"

            # Should only create ONE underlying AzureOpenAI client
            final_creations = mock_azure_class.call_count
            assert final_creations == azure_client_creations + 1, "Should reuse underlying Azure client"

            # All queries should have executed (3 rows x 4 queries = 12)
            assert call_count[0] == 12


class TestRowAtomicity:
    """Tests for row atomicity guarantees under failure conditions."""

    def test_row_atomicity_under_capacity_errors(self) -> None:
        """Verify NO partial rows are emitted when capacity errors occur mid-row.

        CRITICAL PROPERTY: A row must have ALL queries complete before being emitted.
        If any query fails (including capacity errors), the ENTIRE row must be marked
        as failed, not partially processed.
        """
        from elspeth.plugins.clients.llm import RateLimitError

        # Simulate 10% of queries hitting capacity errors
        call_count = [0]
        FAILURE_RATE = 0.1  # 10% of queries fail

        def make_response(**kwargs: Any) -> Mock:
            """Simulate capacity errors for 10% of queries."""
            call_count[0] += 1
            # Deterministic failure pattern: every 10th query fails
            if call_count[0] % 10 == 0:
                raise Exception("Rate limit exceeded")
            return make_mock_llm_response(
                score=85 + call_count[0],
                rationale=f"Response {call_count[0]}",
                delay_ms=10,
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = make_response
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config(pool_size=4))

            # Mock the LLM client to raise RateLimitError for failed queries
            with patch.object(transform, "_get_llm_client") as mock_get_client:
                llm_call_count = [0]

                def mock_chat_completion(**kwargs: Any) -> Mock:
                    llm_call_count[0] += 1
                    if llm_call_count[0] % 10 == 0:
                        raise RateLimitError("Rate limit exceeded")
                    return Mock(
                        content=json.dumps({"score": 85 + llm_call_count[0], "rationale": f"R{llm_call_count[0]}"}),
                        usage={"prompt_tokens": 10, "completion_tokens": 5},
                        model="gpt-4o",
                    )

                mock_llm_client = Mock()
                mock_llm_client.chat_completion.side_effect = mock_chat_completion
                mock_get_client.return_value = mock_llm_client

                transform.on_start(make_plugin_context())
                ctx = make_plugin_context(state_id="atomicity-test")

                # Process 50 rows (200 total queries, ~60 will fail)
                rows = []
                for i in range(50):
                    rows.append(
                        {
                            "row_id": i,  # Track which row this is
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
                assert len(result.rows) == 50  # All 50 rows returned (success or error)

                # Verify atomicity: Each row has EITHER all 4 output fields OR an error marker
                successful_rows = 0
                failed_rows = 0

                for row in result.rows:
                    # Check if row has error marker
                    if "_error" in row:
                        failed_rows += 1
                        # CRITICAL: Failed rows must NOT have partial output fields
                        assert "cs1_diagnosis_score" not in row, f"Row {row['row_id']} has PARTIAL data (error + cs1_diagnosis_score)"
                        assert "cs1_treatment_score" not in row, f"Row {row['row_id']} has PARTIAL data (error + cs1_treatment_score)"
                        assert "cs2_diagnosis_score" not in row, f"Row {row['row_id']} has PARTIAL data (error + cs2_diagnosis_score)"
                        assert "cs2_treatment_score" not in row, f"Row {row['row_id']} has PARTIAL data (error + cs2_treatment_score)"
                        # Original input fields should be preserved
                        assert row["row_id"] is not None
                        assert row["cs1_bg"] is not None
                    else:
                        successful_rows += 1
                        # CRITICAL: Successful rows must have ALL 4 output fields
                        assert "cs1_diagnosis_score" in row, f"Row {row['row_id']} missing cs1_diagnosis_score"
                        assert "cs1_treatment_score" in row, f"Row {row['row_id']} missing cs1_treatment_score"
                        assert "cs2_diagnosis_score" in row, f"Row {row['row_id']} missing cs2_diagnosis_score"
                        assert "cs2_treatment_score" in row, f"Row {row['row_id']} missing cs2_treatment_score"
                        # All 4 scores should be present and valid
                        assert isinstance(row["cs1_diagnosis_score"], int)
                        assert isinstance(row["cs1_treatment_score"], int)
                        assert isinstance(row["cs2_diagnosis_score"], int)
                        assert isinstance(row["cs2_treatment_score"], int)
                        # Original input fields should be preserved
                        assert row["row_id"] is not None
                        assert row["cs1_bg"] is not None

                # Should have both successes and failures (due to 30% failure rate)
                assert successful_rows > 0, "Expected some successful rows"
                assert failed_rows > 0, "Expected some failed rows due to capacity errors"

                print("\nRow atomicity verification:")
                print("  Total rows: 50")
                print(f"  Successful rows: {successful_rows}")
                print(f"  Failed rows: {failed_rows}")
                print(f"  Total queries attempted: {llm_call_count[0]}")
                print(f"  Expected failures (~30%): {int(llm_call_count[0] * FAILURE_RATE)}")
                print("  ✅ NO PARTIAL ROWS DETECTED")

    def test_row_atomicity_high_failure_rate(self) -> None:
        """Verify row atomicity with 80% failure rate (extreme stress test)."""
        from elspeth.plugins.clients.llm import RateLimitError

        llm_call_count = [0]

        def mock_chat_completion(**kwargs: Any) -> Mock:
            """Simulate 80% failure rate."""
            llm_call_count[0] += 1
            # Only calls ending in 0 or 5 succeed (20%)
            if llm_call_count[0] % 5 not in [0, 5]:
                raise RateLimitError("Rate limit exceeded")
            return Mock(
                content=json.dumps({"score": 85, "rationale": "OK"}),
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                model="gpt-4o",
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config(pool_size=4))

            with patch.object(transform, "_get_llm_client") as mock_get_client:
                mock_llm_client = Mock()
                mock_llm_client.chat_completion.side_effect = mock_chat_completion
                mock_get_client.return_value = mock_llm_client

                transform.on_start(make_plugin_context())
                ctx = make_plugin_context(state_id="high-failure-test")

                # Process 20 rows (80 queries, ~64 will fail)
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

                # With 80% failure rate, most rows should fail (each row needs 4 successful queries)
                successful_rows = 0
                failed_rows = 0

                for row in result.rows:
                    if "_error" in row:
                        failed_rows += 1
                        # Verify NO partial output
                        assert "cs1_diagnosis_score" not in row
                        assert "cs1_treatment_score" not in row
                        assert "cs2_diagnosis_score" not in row
                        assert "cs2_treatment_score" not in row
                    else:
                        successful_rows += 1
                        # Verify ALL outputs present
                        assert "cs1_diagnosis_score" in row
                        assert "cs1_treatment_score" in row
                        assert "cs2_diagnosis_score" in row
                        assert "cs2_treatment_score" in row

                # With 80% failure rate, most rows should fail
                assert failed_rows > successful_rows, "Expected more failures than successes with 80% failure rate"

                print("\nHigh failure rate atomicity test:")
                print(f"  Successful rows: {successful_rows}")
                print(f"  Failed rows: {failed_rows}")
                print("  ✅ NO PARTIAL ROWS EVEN AT 80% FAILURE RATE")

    def test_concurrent_row_processing_atomicity(self) -> None:
        """Verify row atomicity when multiple rows processed concurrently with failures.

        This tests the edge case where:
        - Multiple rows are being processed simultaneously
        - Some queries succeed, some fail
        - ThreadPoolExecutor returns results out of order
        - Plugin must still maintain per-row atomicity
        """
        from elspeth.plugins.clients.llm import RateLimitError

        llm_call_count = [0]

        def mock_chat_completion(**kwargs: Any) -> Mock:
            """Simulate failures in a pattern that affects different rows."""
            llm_call_count[0] += 1
            # Fail every 7th query (staggered pattern across rows)
            if llm_call_count[0] % 7 == 0:
                raise RateLimitError("Rate limit exceeded")
            return Mock(
                content=json.dumps({"score": 85, "rationale": "OK"}),
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                model="gpt-4o",
            )

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_azure_class.return_value = mock_client

            # Use pool_size=8 for maximum concurrency
            transform = AzureMultiQueryLLMTransform(make_config(pool_size=8))

            with patch.object(transform, "_get_llm_client") as mock_get_client:
                mock_llm_client = Mock()
                mock_llm_client.chat_completion.side_effect = mock_chat_completion
                mock_get_client.return_value = mock_llm_client

                transform.on_start(make_plugin_context())
                ctx = make_plugin_context(state_id="concurrent-test")

                # Process 30 rows with high concurrency
                rows = []
                for i in range(30):
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
                assert len(result.rows) == 30

                # Verify atomicity for all rows
                for row in result.rows:
                    has_error = "_error" in row
                    has_cs1_diag = "cs1_diagnosis_score" in row
                    has_cs1_treat = "cs1_treatment_score" in row
                    has_cs2_diag = "cs2_diagnosis_score" in row
                    has_cs2_treat = "cs2_treatment_score" in row

                    # Count how many output fields are present
                    output_field_count = sum([has_cs1_diag, has_cs1_treat, has_cs2_diag, has_cs2_treat])

                    if has_error:
                        # Failed row: MUST have 0 output fields
                        assert output_field_count == 0, f"Row {row['row_id']} has error + {output_field_count} output fields (expected 0)"
                    else:
                        # Successful row: MUST have ALL 4 output fields
                        assert output_field_count == 4, f"Row {row['row_id']} has {output_field_count} output fields (expected 4)"

                print("\nConcurrent processing atomicity test:")
                print(f"  Total queries: {llm_call_count[0]}")
                print("  Pool size: 8 (high concurrency)")
                print("  ✅ ALL ROWS ATOMIC (0 or 4 output fields, never 1-3)")


class TestProfilingInstrumentation:
    """Tests for profiling and performance monitoring."""

    def test_query_timing_distribution(self) -> None:
        """Measure timing distribution of individual queries."""
        import statistics

        call_count = [0]
        query_times: list[float] = []

        def make_response(**kwargs: Any) -> Mock:
            """Simulate variable query latency."""
            call_count[0] += 1
            # Vary latency: 20-80ms
            import random

            delay = random.uniform(20, 80)
            start = time.time()
            response = make_mock_llm_response(score=85, rationale="OK", delay_ms=delay)
            query_times.append((time.time() - start) * 1000)
            return response

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = make_response
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config(pool_size=4))
            transform.on_start(make_plugin_context())

            # Process 20 rows
            rows = []
            for i in range(20):
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

            ctx = make_plugin_context()
            result = transform.process(rows, ctx)

            assert result.status == "success"
            assert len(query_times) == 80  # 20 rows x 4 queries

            # Analyze distribution
            mean_ms = statistics.mean(query_times)
            median_ms = statistics.median(query_times)
            p95_ms = sorted(query_times)[int(len(query_times) * 0.95)]
            p99_ms = sorted(query_times)[int(len(query_times) * 0.99)]

            print("\nQuery timing distribution:")
            print(f"  Mean: {mean_ms:.2f}ms")
            print(f"  Median: {median_ms:.2f}ms")
            print(f"  P95: {p95_ms:.2f}ms")
            print(f"  P99: {p99_ms:.2f}ms")

            # Sanity checks (should match our simulated 20-80ms range)
            assert 20 <= mean_ms <= 80
            assert 20 <= median_ms <= 80

    def test_batch_processing_overhead(self) -> None:
        """Measure overhead of batch processing logic."""

        def make_response(**kwargs: Any) -> Mock:
            # Instant responses to isolate batch processing overhead
            return make_mock_llm_response(score=85, rationale="OK", delay_ms=0)

        with patch("openai.AzureOpenAI") as mock_azure_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = make_response
            mock_azure_class.return_value = mock_client

            transform = AzureMultiQueryLLMTransform(make_config(pool_size=4))
            transform.on_start(make_plugin_context())

            # Process 100 rows
            rows = []
            for i in range(100):
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

            ctx = make_plugin_context()

            start_time = time.time()
            result = transform.process(rows, ctx)
            elapsed = time.time() - start_time

            assert result.status == "success"
            assert result.is_multi_row
            assert len(result.rows) == 100

            # With instant LLM responses, overhead should be minimal
            # 100 rows x 4 queries = 400 queries, batch overhead should be < 1s
            assert elapsed < 1.0, f"Batch overhead too high: {elapsed:.2f}s"

            print("\nBatch processing overhead:")
            print("  100 rows x 4 queries = 400 queries")
            print(f"  Total time: {elapsed:.3f}s")
            print(f"  Overhead per query: {elapsed / 400 * 1000:.3f}ms")
