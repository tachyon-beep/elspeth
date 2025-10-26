"""Tests for score_stats aggregator to reach 80% coverage.

Focus on testing uncovered lines 54-61, 58-59, 96-158.
"""

from __future__ import annotations

import math

import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.experiments.aggregators.score_stats import ScoreStatsAggregator
from elspeth.plugins.experiments.baseline.score_delta import ScoreDeltaBaselinePlugin


def test_score_stats_empty_records():
    """Test ScoreStatsAggregator with empty records."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    result = aggregator.finalize([])

    assert result["criteria"] == {}
    assert result["overall"]["count"] == 0
    assert result["overall"]["missing"] == 0


def test_score_stats_no_scores():
    """Test ScoreStatsAggregator with records but no scores."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    records = [
        {"metrics": {}},
        {"metrics": None},
    ]
    result = aggregator.finalize(records)

    assert result["criteria"] == {}
    assert result["overall"]["count"] == 0


def test_score_stats_with_scores():
    """Test ScoreStatsAggregator with valid scores."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    records = [
        {"metrics": {"scores": {"accuracy": 0.8, "precision": 0.9}}},
        {"metrics": {"scores": {"accuracy": 0.9, "precision": 0.85}}},
        {"metrics": {"scores": {"accuracy": 0.85, "precision": 0.95}}},
    ]
    result = aggregator.finalize(records)

    assert "accuracy" in result["criteria"]
    assert "precision" in result["criteria"]
    assert result["criteria"]["accuracy"]["count"] == 3
    assert result["criteria"]["accuracy"]["missing"] == 0
    assert result["criteria"]["accuracy"]["mean"] > 0.8
    assert result["criteria"]["accuracy"]["std"] > 0


def test_score_stats_with_none_values():
    """Test ScoreStatsAggregator handles None score values (lines 57-59)."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    records = [
        {"metrics": {"scores": {"accuracy": None}}},
        {"metrics": {"scores": {"accuracy": 0.8}}},
    ]
    result = aggregator.finalize(records)

    assert result["criteria"]["accuracy"]["count"] == 1
    assert result["criteria"]["accuracy"]["missing"] == 1


def test_score_stats_with_nan_values():
    """Test ScoreStatsAggregator handles NaN score values (lines 57-59)."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    records = [
        {"metrics": {"scores": {"accuracy": math.nan}}},
        {"metrics": {"scores": {"accuracy": 0.8}}},
    ]
    result = aggregator.finalize(records)

    assert result["criteria"]["accuracy"]["count"] == 1
    assert result["criteria"]["accuracy"]["missing"] == 1


def test_score_stats_with_flags():
    """Test ScoreStatsAggregator with score flags (lines 61-66)."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    records = [
        {
            "metrics": {
                "scores": {"accuracy": 0.8},
                "score_flags": {"accuracy": True},
            }
        },
        {
            "metrics": {
                "scores": {"accuracy": 0.9},
                "score_flags": {"accuracy": True},
            }
        },
        {
            "metrics": {
                "scores": {"accuracy": 0.6},
                "score_flags": {"accuracy": False},
            }
        },
    ]
    result = aggregator.finalize(records)

    assert result["criteria"]["accuracy"]["passes"] == 2
    assert result["criteria"]["accuracy"]["pass_rate"] == 2 / 3


def test_score_stats_custom_fields():
    """Test ScoreStatsAggregator with custom source and flag fields."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True, source_field="custom_scores", flag_field="custom_flags")
    records = [
        {
            "metrics": {
                "custom_scores": {"metric1": 0.7},
                "custom_flags": {"metric1": True},
            }
        },
    ]
    result = aggregator.finalize(records)

    assert "metric1" in result["criteria"]
    assert result["criteria"]["metric1"]["passes"] == 1


def test_score_stats_custom_ddof():
    """Test ScoreStatsAggregator with custom ddof."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True, ddof=1)
    records = [
        {"metrics": {"scores": {"accuracy": 0.8}}},
        {"metrics": {"scores": {"accuracy": 0.9}}},
        {"metrics": {"scores": {"accuracy": 0.85}}},
    ]
    result = aggregator.finalize(records)

    # With ddof=1 and 3 values, std should be calculated differently than ddof=0
    assert "std" in result["criteria"]["accuracy"]
    assert result["criteria"]["accuracy"]["std"] > 0


def test_score_stats_single_value():
    """Test ScoreStatsAggregator with single value (lines 106-109)."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    records = [
        {"metrics": {"scores": {"accuracy": 0.8}}},
    ]
    result = aggregator.finalize(records)

    # With single value, std should be 0.0
    assert result["criteria"]["accuracy"]["count"] == 1
    assert result["criteria"]["accuracy"]["std"] == 0.0


def test_score_stats_overall_aggregation():
    """Test ScoreStatsAggregator overall aggregation across criteria."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    records = [
        {"metrics": {"scores": {"accuracy": 0.8, "precision": 0.9}}},
        {"metrics": {"scores": {"accuracy": 0.9, "precision": None}}},
    ]
    result = aggregator.finalize(records)

    # Overall should aggregate all values across all criteria
    assert result["overall"]["count"] == 3  # 2 accuracy + 1 precision
    assert result["overall"]["missing"] == 1  # 1 None precision


def test_score_stats_pass_rate_calculation():
    """Test ScoreStatsAggregator pass_rate calculation (lines 110-112)."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    records = [
        {
            "metrics": {
                "scores": {"accuracy": 0.8},
                "score_flags": {"accuracy": True},
            }
        },
        {
            "metrics": {
                "scores": {"accuracy": None},  # Missing value
                "score_flags": {"accuracy": False},
            }
        },
    ]
    result = aggregator.finalize(records)

    # Total is count + missing = 1 + 1 = 2
    # Passes is 1
    assert result["criteria"]["accuracy"]["pass_rate"] == 0.5


def test_score_stats_no_passes_no_total():
    """Test ScoreStatsAggregator when total is 0 (no pass_rate calculated)."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    records = []
    result = aggregator.finalize(records)

    # Overall should have no pass_rate if total is 0
    assert "pass_rate" not in result["overall"]


def test_score_stats_summarize_values_no_values():
    """Test _summarize_values with no values (lines 96-113)."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    summary = aggregator._summarize_values([], missing=2, passes=1)

    assert summary["count"] == 0
    assert summary["missing"] == 2
    assert summary["passes"] == 1
    assert summary["pass_rate"] == 0.5
    # No mean, median, etc. when count is 0
    assert "mean" not in summary


def test_score_stats_summarize_values_with_values():
    """Test _summarize_values with values (lines 96-113)."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    summary = aggregator._summarize_values([0.7, 0.8, 0.9], missing=1, passes=3)

    assert summary["count"] == 3
    assert summary["missing"] == 1
    assert summary["passes"] == 3
    assert summary["pass_rate"] == 0.75  # 3 passes / 4 total
    assert summary["mean"] == pytest.approx(0.8)
    assert summary["median"] == 0.8
    assert summary["min"] == 0.7
    assert summary["max"] == 0.9
    assert summary["std"] > 0


def test_score_stats_input_schema():
    """Test ScoreStatsAggregator input_schema method."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    assert aggregator.input_schema() is None


def test_score_delta_baseline_empty_stats():
    """Test ScoreDeltaBaselinePlugin with empty stats (lines 132-133)."""
    plugin = ScoreDeltaBaselinePlugin(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    result = plugin.compare({}, {})
    assert result == {}


def test_score_delta_baseline_no_aggregates():
    """Test ScoreDeltaBaselinePlugin with no aggregates (lines 148-151)."""
    plugin = ScoreDeltaBaselinePlugin(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    baseline = {"results": []}
    variant = {"results": []}
    result = plugin.compare(baseline, variant)
    assert result == {}


def test_score_delta_baseline_no_score_stats():
    """Test ScoreDeltaBaselinePlugin with no score_stats in aggregates (lines 152-154)."""
    plugin = ScoreDeltaBaselinePlugin(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    baseline = {"aggregates": {}}
    variant = {"aggregates": {}}
    result = plugin.compare(baseline, variant)
    assert result == {}


def test_score_delta_baseline_no_criteria():
    """Test ScoreDeltaBaselinePlugin with no criteria (lines 155-158)."""
    plugin = ScoreDeltaBaselinePlugin(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    baseline = {"aggregates": {"score_stats": {}}}
    variant = {"aggregates": {"score_stats": {}}}
    result = plugin.compare(baseline, variant)
    assert result == {}


def test_score_delta_baseline_valid_comparison():
    """Test ScoreDeltaBaselinePlugin with valid comparison (lines 129-145)."""
    plugin = ScoreDeltaBaselinePlugin(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    baseline = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.8, "count": 10},
                    "precision": {"mean": 0.75, "count": 10},
                }
            }
        }
    }
    variant = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.85, "count": 10},
                    "precision": {"mean": 0.80, "count": 10},
                }
            }
        }
    }
    result = plugin.compare(baseline, variant)

    assert "accuracy" in result
    assert "precision" in result
    assert result["accuracy"] == pytest.approx(0.05)
    assert result["precision"] == pytest.approx(0.05)


def test_score_delta_baseline_custom_metric():
    """Test ScoreDeltaBaselinePlugin with custom metric."""
    plugin = ScoreDeltaBaselinePlugin(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True, metric="median")
    baseline = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.8, "median": 0.75, "count": 10},
                }
            }
        }
    }
    variant = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.85, "median": 0.80, "count": 10},
                }
            }
        }
    }
    result = plugin.compare(baseline, variant)

    # Should use median, not mean
    assert result["accuracy"] == pytest.approx(0.05)  # 0.80 - 0.75


def test_score_delta_baseline_criteria_filter():
    """Test ScoreDeltaBaselinePlugin with criteria filter (lines 138-139)."""
    plugin = ScoreDeltaBaselinePlugin(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True, criteria=["accuracy"])
    baseline = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.8},
                    "precision": {"mean": 0.75},
                }
            }
        }
    }
    variant = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.85},
                    "precision": {"mean": 0.80},
                }
            }
        }
    }
    result = plugin.compare(baseline, variant)

    # Should only include accuracy, not precision
    assert "accuracy" in result
    assert "precision" not in result


def test_score_delta_baseline_missing_metric():
    """Test ScoreDeltaBaselinePlugin with missing metric in one variant (lines 140-143)."""
    plugin = ScoreDeltaBaselinePlugin(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    baseline = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.8},
                }
            }
        }
    }
    variant = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {},  # No mean
                }
            }
        }
    }
    result = plugin.compare(baseline, variant)

    # Should not include accuracy since variant has no mean
    assert result == {}


def test_score_delta_baseline_different_criteria_sets():
    """Test ScoreDeltaBaselinePlugin with different criteria in baseline vs variant."""
    plugin = ScoreDeltaBaselinePlugin(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    baseline = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.8},
                    "precision": {"mean": 0.75},
                }
            }
        }
    }
    variant = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.85},
                    "recall": {"mean": 0.70},
                }
            }
        }
    }
    result = plugin.compare(baseline, variant)

    # Should only include accuracy (intersection of both)
    assert "accuracy" in result
    assert "precision" not in result
    assert "recall" not in result


def test_score_stats_non_mapping_scores():
    """Test ScoreStatsAggregator handles non-mapping scores gracefully (line 54)."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    records = [
        {"metrics": {"scores": "not a mapping"}},
        {"metrics": {"scores": ["list", "not", "dict"]}},
        {"metrics": {"scores": {"accuracy": 0.8}}},
    ]
    result = aggregator.finalize(records)

    # Only the valid mapping should be processed
    assert result["criteria"]["accuracy"]["count"] == 1


def test_score_stats_non_mapping_flags():
    """Test ScoreStatsAggregator handles non-mapping flags gracefully (line 62)."""
    aggregator = ScoreStatsAggregator(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)
    records = [
        {
            "metrics": {
                "scores": {"accuracy": 0.8},
                "score_flags": "not a mapping",
            }
        },
        {
            "metrics": {
                "scores": {"accuracy": 0.9},
                "score_flags": {"accuracy": True},
            }
        },
    ]
    result = aggregator.finalize(records)

    # Only the valid flags should be processed
    assert result["criteria"]["accuracy"]["passes"] == 1
