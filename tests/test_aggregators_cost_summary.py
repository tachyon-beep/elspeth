"""Tests for cost_summary aggregator to reach 80% coverage.

Focus on testing uncovered lines 40, 69-70, 75-76, 81-82, 89-172, 189.
"""

from __future__ import annotations

import math

import pytest

from elspeth.core.base.types import SecurityLevel

from elspeth.plugins.experiments.aggregators.cost_summary import CostSummaryAggregator
from elspeth.plugins.experiments.aggregators.latency_summary import LatencySummaryAggregator


def test_cost_summary_invalid_on_error():
    """Test CostSummaryAggregator raises on invalid on_error value (line 40)."""
    with pytest.raises(ValueError, match="on_error must be 'abort' or 'skip'"):
        CostSummaryAggregator(on_error="invalid")


def test_cost_summary_empty_records():
    """Test CostSummaryAggregator with empty records."""
    aggregator = CostSummaryAggregator()
    result = aggregator.finalize([])
    assert result == {}


def test_cost_summary_no_metrics():
    """Test CostSummaryAggregator with records but no metrics."""
    aggregator = CostSummaryAggregator()
    records = [
        {"prompt": "test1"},
        {"prompt": "test2"},
    ]
    result = aggregator.finalize(records)
    assert result["total_requests"] == 2
    assert result["requests_with_cost"] == 0


def test_cost_summary_with_all_metrics():
    """Test CostSummaryAggregator with complete cost metrics."""
    aggregator = CostSummaryAggregator()
    records = [
        {
            "metrics": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "cost": 0.05,
            }
        },
        {
            "metrics": {
                "prompt_tokens": 200,
                "completion_tokens": 100,
                "cost": 0.10,
            }
        },
        {
            "metrics": {
                "prompt_tokens": 150,
                "completion_tokens": 75,
                "cost": 0.075,
            }
        },
    ]
    result = aggregator.finalize(records)

    assert result["total_requests"] == 3
    assert result["requests_with_cost"] == 3
    assert result["prompt_tokens"]["total"] == 450
    assert result["prompt_tokens"]["min"] == 100
    assert result["prompt_tokens"]["max"] == 200
    assert result["completion_tokens"]["total"] == 225
    assert result["completion_tokens"]["min"] == 50
    assert result["completion_tokens"]["max"] == 100
    assert result["cost"]["total"] == 0.225
    assert result["cost"]["min"] == 0.05
    assert result["cost"]["max"] == 0.10


def test_cost_summary_invalid_prompt_tokens():
    """Test CostSummaryAggregator handles invalid prompt_tokens (lines 69-70)."""
    aggregator = CostSummaryAggregator()
    records = [
        {"metrics": {"prompt_tokens": "invalid"}},
        {"metrics": {"prompt_tokens": None}},
        {"metrics": {"prompt_tokens": 100}},
    ]
    result = aggregator.finalize(records)

    # Only the valid one should be counted
    assert result["prompt_tokens"]["total"] == 100
    assert result["prompt_tokens"]["min"] == 100
    assert result["prompt_tokens"]["max"] == 100


def test_cost_summary_invalid_completion_tokens():
    """Test CostSummaryAggregator handles invalid completion_tokens (lines 75-76)."""
    aggregator = CostSummaryAggregator()
    records = [
        {"metrics": {"completion_tokens": "invalid"}},
        {"metrics": {"completion_tokens": None}},
        {"metrics": {"completion_tokens": 50}},
    ]
    result = aggregator.finalize(records)

    # Only the valid one should be counted
    assert result["completion_tokens"]["total"] == 50
    assert result["completion_tokens"]["min"] == 50
    assert result["completion_tokens"]["max"] == 50


def test_cost_summary_invalid_cost():
    """Test CostSummaryAggregator handles invalid cost (lines 81-82)."""
    aggregator = CostSummaryAggregator()
    records = [
        {"metrics": {"cost": "invalid"}},
        {"metrics": {"cost": None}},
        {"metrics": {"cost": 0.05}},
    ]
    result = aggregator.finalize(records)

    # Only the valid one should be counted
    assert result["cost"]["total"] == 0.05
    assert result["cost"]["min"] == 0.05
    assert result["cost"]["max"] == 0.05


def test_cost_summary_partial_metrics():
    """Test CostSummaryAggregator with partial metrics across records."""
    aggregator = CostSummaryAggregator()
    records = [
        {"metrics": {"prompt_tokens": 100}},
        {"metrics": {"completion_tokens": 50}},
        {"metrics": {"cost": 0.05}},
        {"metrics": {"prompt_tokens": 200, "cost": 0.10}},
    ]
    result = aggregator.finalize(records)

    assert result["total_requests"] == 4
    assert result["requests_with_cost"] == 2
    assert result["prompt_tokens"]["total"] == 300
    assert result["completion_tokens"]["total"] == 50
    assert result["cost"]["total"] == pytest.approx(0.15)


def test_cost_summary_none_metrics():
    """Test CostSummaryAggregator with None metrics field."""
    aggregator = CostSummaryAggregator()
    records = [
        {"metrics": None},
        {"metrics": {}},
    ]
    result = aggregator.finalize(records)

    assert result["total_requests"] == 2
    assert result["requests_with_cost"] == 0


def test_cost_summary_zero_costs():
    """Test CostSummaryAggregator with zero costs."""
    aggregator = CostSummaryAggregator()
    records = [
        {"metrics": {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}},
    ]
    result = aggregator.finalize(records)

    assert result["prompt_tokens"]["total"] == 0
    assert result["completion_tokens"]["total"] == 0
    assert result["cost"]["total"] == 0.0


def test_latency_summary_invalid_on_error():
    """Test LatencySummaryAggregator raises on invalid on_error value (line 134)."""
    with pytest.raises(ValueError, match="on_error must be 'abort' or 'skip'"):
        LatencySummaryAggregator(on_error="invalid")


def test_latency_summary_empty_records():
    """Test LatencySummaryAggregator with empty records (line 147-148)."""
    aggregator = LatencySummaryAggregator()
    result = aggregator.finalize([])
    assert result == {}


def test_latency_summary_no_latency_data():
    """Test LatencySummaryAggregator with no latency data (lines 164-168)."""
    aggregator = LatencySummaryAggregator()
    records = [
        {"metrics": {}},
        {"metrics": None},
    ]
    result = aggregator.finalize(records)

    assert result["total_requests"] == 2
    assert result["requests_with_latency"] == 0


def test_latency_summary_with_valid_latency():
    """Test LatencySummaryAggregator with valid latency data (lines 170-185)."""
    aggregator = LatencySummaryAggregator()
    records = [
        {"metrics": {"latency_seconds": 1.5}},
        {"metrics": {"latency_seconds": 2.0}},
        {"metrics": {"latency_seconds": 1.2}},
        {"metrics": {"latency_seconds": 3.0}},
    ]
    result = aggregator.finalize(records)

    assert result["total_requests"] == 4
    assert result["requests_with_latency"] == 4
    assert "latency_seconds" in result
    assert result["latency_seconds"]["min"] == 1.2
    assert result["latency_seconds"]["max"] == 3.0
    assert result["latency_seconds"]["mean"] > 0
    assert result["latency_seconds"]["median"] > 0
    assert result["latency_seconds"]["std"] >= 0
    assert result["latency_seconds"]["p50"] > 0
    assert result["latency_seconds"]["p95"] > 0
    assert result["latency_seconds"]["p99"] > 0


def test_latency_summary_invalid_latency():
    """Test LatencySummaryAggregator handles invalid latency values (lines 156-162)."""
    aggregator = LatencySummaryAggregator()
    records = [
        {"metrics": {"latency_seconds": "invalid"}},
        {"metrics": {"latency_seconds": None}},
        {"metrics": {"latency_seconds": math.nan}},
        {"metrics": {"latency_seconds": -1.0}},  # Negative should be filtered
        {"metrics": {"latency_seconds": 1.5}},  # Only this one is valid
    ]
    result = aggregator.finalize(records)

    assert result["total_requests"] == 5
    assert result["requests_with_latency"] == 1
    assert result["latency_seconds"]["min"] == 1.5
    assert result["latency_seconds"]["max"] == 1.5


def test_latency_summary_single_value():
    """Test LatencySummaryAggregator with single value (std computation line 178)."""
    aggregator = LatencySummaryAggregator()
    records = [
        {"metrics": {"latency_seconds": 1.5}},
    ]
    result = aggregator.finalize(records)

    assert result["requests_with_latency"] == 1
    # With single value, std should be 0.0
    assert result["latency_seconds"]["std"] == 0.0


def test_latency_summary_multiple_values_std():
    """Test LatencySummaryAggregator std computation with multiple values (line 178)."""
    aggregator = LatencySummaryAggregator()
    records = [
        {"metrics": {"latency_seconds": 1.0}},
        {"metrics": {"latency_seconds": 2.0}},
        {"metrics": {"latency_seconds": 3.0}},
    ]
    result = aggregator.finalize(records)

    # With multiple values, std should be > 0
    assert result["latency_seconds"]["std"] > 0


def test_cost_summary_input_schema():
    """Test that CostSummaryAggregator returns None for input_schema."""
    aggregator = CostSummaryAggregator()
    assert aggregator.input_schema() is None


def test_latency_summary_input_schema():
    """Test that LatencySummaryAggregator returns None for input_schema (line 189)."""
    aggregator = LatencySummaryAggregator()
    assert aggregator.input_schema() is None


def test_cost_summary_on_error_skip():
    """Test CostSummaryAggregator with on_error='skip'."""
    aggregator = CostSummaryAggregator(on_error="skip")
    # Normal operation should work
    result = aggregator.finalize([{"metrics": {"cost": 0.05}}])
    assert result["requests_with_cost"] == 1


def test_latency_summary_on_error_skip():
    """Test LatencySummaryAggregator with on_error='skip'."""
    aggregator = LatencySummaryAggregator(on_error="skip")
    # Normal operation should work
    result = aggregator.finalize([{"metrics": {"latency_seconds": 1.5}}])
    assert result["requests_with_latency"] == 1


def test_cost_summary_mixed_valid_invalid():
    """Test CostSummaryAggregator with mix of valid and invalid data."""
    aggregator = CostSummaryAggregator()
    records = [
        {"metrics": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.05}},
        {"metrics": {"prompt_tokens": "bad", "completion_tokens": None, "cost": "invalid"}},
        {"metrics": None},
        {},
        {"metrics": {"prompt_tokens": 200, "completion_tokens": 100, "cost": 0.10}},
    ]
    result = aggregator.finalize(records)

    assert result["total_requests"] == 5
    assert result["requests_with_cost"] == 2
    assert result["prompt_tokens"]["total"] == 300
    assert result["completion_tokens"]["total"] == 150
    assert result["cost"]["total"] == pytest.approx(0.15)


def test_latency_summary_percentiles():
    """Test LatencySummaryAggregator calculates correct percentiles."""
    aggregator = LatencySummaryAggregator()
    # Create a predictable distribution
    records = [{"metrics": {"latency_seconds": float(i)}} for i in range(1, 101)]
    result = aggregator.finalize(records)

    assert result["requests_with_latency"] == 100
    # Verify percentiles are in expected ranges
    assert 40 < result["latency_seconds"]["p50"] < 60
    assert 85 < result["latency_seconds"]["p95"] < 100
    assert 90 < result["latency_seconds"]["p99"] <= 100
