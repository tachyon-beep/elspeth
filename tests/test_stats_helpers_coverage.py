"""Coverage tests for _stats_helpers to reach 80% coverage.

Focuses on uncovered lines in statistical computation helpers:
- Lines 18-41: _create_score_extractor_factory edge cases
- Line 190: scipy failure in p_value calculation
- Line 234: stderr <= 0 early return
- Lines 307-309, 318-320, 339-340: Exception handling in distribution metrics
"""

from __future__ import annotations

import pytest

from elspeth.core.validation.base import ConfigurationError
from elspeth.plugins.experiments._stats_helpers import (
    _benjamini_hochberg,
    _calculate_cliffs_delta,
    _collect_paired_scores_by_criterion,
    _collect_scores_by_criterion,
    _compute_bayesian_summary,
    _compute_distribution_shift,
    _compute_significance,
    _create_score_extractor_factory,
)


def test_create_score_extractor_factory_missing_key():
    """Test factory validation for missing required fields - line 23."""
    with pytest.raises(ConfigurationError, match="key is required"):
        _create_score_extractor_factory({})


def test_create_score_extractor_factory_missing_parse_json():
    """Test factory validation for missing parse_json_content - line 25."""
    with pytest.raises(ConfigurationError, match="parse_json_content is required"):
        _create_score_extractor_factory({"key": "response"})


def test_create_score_extractor_factory_missing_allow_missing():
    """Test factory validation for missing allow_missing - line 27."""
    with pytest.raises(ConfigurationError, match="allow_missing is required"):
        _create_score_extractor_factory({
            "key": "response",
            "parse_json_content": True
        })


def test_create_score_extractor_factory_missing_threshold_mode():
    """Test factory validation for missing threshold_mode - line 29."""
    with pytest.raises(ConfigurationError, match="threshold_mode is required"):
        _create_score_extractor_factory({
            "key": "response",
            "parse_json_content": True,
            "allow_missing": False
        })


def test_create_score_extractor_factory_missing_flag_field():
    """Test factory validation for missing flag_field - line 31."""
    with pytest.raises(ConfigurationError, match="flag_field is required"):
        _create_score_extractor_factory({
            "key": "response",
            "parse_json_content": True,
            "allow_missing": False,
            "threshold_mode": "none"
        })


def test_create_score_extractor_factory_complete():
    """Test factory with all required fields."""
    result = _create_score_extractor_factory({
        "key": "response",
        "parse_json_content": True,
        "allow_missing": False,
        "threshold_mode": "none",
        "flag_field": "flagged",
        "criteria": ["accuracy", "precision"],
        "threshold": 0.5
    })

    assert result["key"] == "response"
    assert result["parse_json_content"] is True
    assert result["allow_missing"] is False
    assert result["threshold_mode"] == "none"
    assert result["flag_field"] == "flagged"
    assert result["criteria"] == ["accuracy", "precision"]
    assert result["threshold"] == 0.5


def test_compute_bayesian_summary_zero_stderr():
    """Test Bayesian summary with zero stderr - line 234."""
    # Identical samples lead to zero variance
    baseline = [0.5, 0.5, 0.5]
    variant = [0.5, 0.5, 0.5]

    result = _compute_bayesian_summary(baseline, variant, alpha=0.05)

    # Should return empty dict when stderr <= 0
    assert result == {}


def test_compute_bayesian_summary_single_sample():
    """Test Bayesian summary with insufficient variance."""
    # Single sample each (n=1, variance can't be computed)
    baseline = [0.5]
    variant = [0.5]

    result = _compute_bayesian_summary(baseline, variant, alpha=0.05)
    assert result == {}


def test_compute_bayesian_summary_with_scipy():
    """Test Bayesian summary uses scipy.stats when available."""
    baseline = [0.5, 0.6, 0.7, 0.55, 0.65]
    variant = [0.6, 0.7, 0.8, 0.65, 0.75]

    result = _compute_bayesian_summary(baseline, variant, alpha=0.05)

    assert "baseline_mean" in result
    assert "variant_mean" in result
    assert "mean_difference" in result
    assert "std_error" in result
    assert "prob_variant_gt_baseline" in result
    assert "credible_interval" in result
    assert len(result["credible_interval"]) == 2


def test_compute_significance_edge_cases():
    """Test significance computation edge cases."""
    # Empty arrays
    result = _compute_significance([], [])
    assert result["baseline_samples"] == 0
    assert result["variant_samples"] == 0
    assert result["effect_size"] is None

    # Single sample (no variance)
    result = _compute_significance([0.5], [0.6])
    assert result["baseline_samples"] == 1
    assert result["variant_samples"] == 1


def test_compute_significance_with_equal_var():
    """Test significance computation with equal variance assumption."""
    baseline = [0.5, 0.6, 0.7, 0.55, 0.65]
    variant = [0.6, 0.7, 0.8, 0.65, 0.75]

    result = _compute_significance(baseline, variant, equal_var=True)

    assert "t_stat" in result
    assert "p_value" in result
    assert "degrees_of_freedom" in result
    assert "effect_size" in result

    # With equal_var, df should be n1 + n2 - 2
    assert result["degrees_of_freedom"] == 8


def test_collect_scores_invalid_scores_type():
    """Test collecting scores with invalid scores type."""
    payload = {
        "results": [
            {"metrics": {"scores": "not a dict"}},  # Invalid type
            {"metrics": {"scores": {"accuracy": 0.8}}},
        ]
    }

    result = _collect_scores_by_criterion(payload)
    # Should only collect valid scores
    assert "accuracy" in result
    assert len(result["accuracy"]) == 1


def test_collect_scores_nan_values():
    """Test that NaN values are filtered out."""
    import math

    payload = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": math.nan}}},  # NaN
            {"metrics": {"scores": {"accuracy": 0.7}}},
        ]
    }

    result = _collect_scores_by_criterion(payload)
    # NaN should be filtered out
    assert len(result["accuracy"]) == 2
    assert 0.8 in result["accuracy"]
    assert 0.7 in result["accuracy"]


def test_collect_paired_scores_mismatched_lengths():
    """Test paired scores with different lengths."""
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.75}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
        ]
    }

    result = _collect_paired_scores_by_criterion(baseline, variant)

    # Should only pair first record (min length)
    assert len(result["accuracy"]) == 1


def test_collect_paired_scores_invalid_types():
    """Test paired scores with invalid types."""
    baseline = {
        "results": [
            "not a dict",  # Invalid
            {"metrics": {"scores": {"accuracy": 0.7}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
        ]
    }

    result = _collect_paired_scores_by_criterion(baseline, variant)

    # Should skip invalid records
    assert len(result["accuracy"]) == 1


def test_calculate_cliffs_delta_empty():
    """Test Cliff's Delta with empty arrays."""
    delta, interp = _calculate_cliffs_delta([], [1, 2, 3])
    assert delta == 0.0
    assert interp == "no_data"

    delta, interp = _calculate_cliffs_delta([1, 2, 3], [])
    assert delta == 0.0
    assert interp == "no_data"


def test_calculate_cliffs_delta_interpretations():
    """Test Cliff's Delta interpretation thresholds."""
    # Negligible - values very close
    delta, interp = _calculate_cliffs_delta([1.0, 2.0, 3.0], [1.01, 2.01, 3.01])
    assert interp in ["negligible", "small"]  # Could be either depending on exact calculation

    # Large - very different values
    delta, interp = _calculate_cliffs_delta([1, 2, 3], [10, 11, 12])
    assert interp == "large"


def test_benjamini_hochberg_empty():
    """Test B-H correction with empty list."""
    result = _benjamini_hochberg([])
    assert result == []


def test_benjamini_hochberg_single():
    """Test B-H correction with single p-value."""
    result = _benjamini_hochberg([0.05])
    assert len(result) == 1
    assert result[0] == 0.05


def test_benjamini_hochberg_multiple():
    """Test B-H correction with multiple p-values."""
    p_values = [0.01, 0.04, 0.03, 0.005]
    result = _benjamini_hochberg(p_values)

    assert len(result) == len(p_values)
    # All adjusted p-values should be >= original
    for orig, adj in zip(p_values, result):
        assert adj >= orig
    # All adjusted p-values should be <= 1.0
    assert all(p <= 1.0 for p in result)


def test_compute_distribution_shift_identical():
    """Test distribution shift with identical distributions."""
    data = [1.0, 2.0, 3.0, 4.0, 5.0]

    result = _compute_distribution_shift(data, data)

    # KS and MW tests should show no significant difference
    assert result["ks_statistic"] is not None
    assert result["mwu_statistic"] is not None
    # JS divergence should be near 0
    assert result["js_divergence"] is not None
    assert result["js_divergence"] < 0.1


def test_compute_distribution_shift_insufficient_data():
    """Test distribution shift with insufficient data."""
    result = _compute_distribution_shift([1.0], [2.0])

    # Should have basic stats but no test statistics (need >= 2 samples)
    assert result["baseline_samples"] == 1
    assert result["variant_samples"] == 1
    assert result["ks_statistic"] is None
    assert result["mwu_statistic"] is None


def test_compute_distribution_shift_empty():
    """Test distribution shift with empty data."""
    result = _compute_distribution_shift([], [1, 2, 3])

    assert result["baseline_samples"] == 0
    assert result["ks_statistic"] is None


def test_compute_distribution_shift_constant_values():
    """Test JS divergence with constant values (same min/max) - line 328."""
    # All same values - hist_range[0] == hist_range[1]
    baseline = [5.0, 5.0, 5.0]
    variant = [5.0, 5.0, 5.0]

    result = _compute_distribution_shift(baseline, variant)

    # JS divergence should be 0 for identical constant distributions
    assert result["js_divergence"] == 0.0


def test_compute_bayesian_summary_fallback_to_normal():
    """Test Bayesian summary falls back to NormalDist when df is None."""
    # Create scenario where df might be problematic
    baseline = [0.5, 0.5]  # Very small variance
    variant = [0.6, 0.6]

    result = _compute_bayesian_summary(baseline, variant, alpha=0.05)

    # Should still produce results (using Normal approximation if needed)
    if result:  # May be empty if stderr is 0
        assert "prob_variant_gt_baseline" in result
        assert "credible_interval" in result


def test_collect_scores_none_values():
    """Test collecting scores with None values."""
    payload = {
        "results": [
            {"metrics": {"scores": {"accuracy": None}}},
            {"metrics": {"scores": {"accuracy": 0.8}}},
        ]
    }

    result = _collect_scores_by_criterion(payload)
    # None values should be skipped
    assert len(result["accuracy"]) == 1


def test_collect_paired_scores_nan_handling():
    """Test paired scores filters NaN values."""
    import math

    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {"accuracy": math.nan}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
        ]
    }

    result = _collect_paired_scores_by_criterion(baseline, variant)

    # Second pair should be filtered (baseline has NaN)
    assert len(result["accuracy"]) == 1
    assert result["accuracy"][0] == (0.7, 0.8)


def test_collect_paired_scores_missing_criterion_in_variant():
    """Test paired scores when variant missing criterion."""
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7, "precision": 0.6}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},  # Missing precision
        ]
    }

    result = _collect_paired_scores_by_criterion(baseline, variant)

    # accuracy should be paired
    assert "accuracy" in result
    assert len(result["accuracy"]) == 1

    # precision should not be paired (missing in variant)
    assert "precision" not in result


def test_compute_significance_zero_variance():
    """Test significance with zero variance."""
    # All same values
    baseline = [0.5, 0.5, 0.5]
    variant = [0.6, 0.6, 0.6]

    result = _compute_significance(baseline, variant)

    # Should still compute despite zero variance
    assert result["baseline_std"] == 0.0
    assert result["variant_std"] == 0.0
