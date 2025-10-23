"""Safety tests for edge cases and error conditions in ExperimentRunner."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from elspeth.core.experiments.runner import ExperimentRunner
from tests.conftest import SimpleLLM


def test_run_with_empty_dataframe() -> None:
    """Edge case: Empty DataFrame should return empty results without error."""
    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ field }}",
    )

    df = pd.DataFrame()  # Empty DataFrame

    result = runner.run(df)

    # Should complete successfully
    assert result["results"] == []
    assert result["failures"] == []
    assert result["metadata"]["rows"] == 0
    assert result["metadata"]["row_count"] == 0


def test_run_with_concurrent_execution() -> None:
    """Safety: Concurrent execution maintains result order and count."""
    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        concurrency_config={"max_workers": 3},
    )

    # Enough rows to trigger parallel execution
    df = pd.DataFrame([{"id": f"row{i}"} for i in range(20)])

    result = runner.run(df)

    # All rows processed
    assert len(result["results"]) == 20

    # Results maintain order
    result_ids = [r["row"]["id"] for r in result["results"]]
    expected_ids = [f"row{i}" for i in range(20)]
    assert result_ids == expected_ids


def test_run_with_failing_aggregator() -> None:
    """Safety: Aggregator exception should be handled gracefully or propagate clearly."""
    class BrokenAggregator:
        name = "broken"

        def finalize(self, results: list[dict[str, Any]]) -> dict[str, Any]:
            raise RuntimeError("Aggregator intentionally broken for testing")

    runner = ExperimentRunner(
        llm_client=SimpleLLM(),
        sinks=[],
        prompt_system="Test",
        prompt_template="Process {{ id }}",
        aggregator_plugins=[BrokenAggregator()],
    )

    df = pd.DataFrame([{"id": "test"}])

    # Current behavior: exception should propagate
    # (This documents current behavior; adjust based on actual implementation)
    with pytest.raises(RuntimeError, match="Aggregator intentionally broken"):
        runner.run(df)
