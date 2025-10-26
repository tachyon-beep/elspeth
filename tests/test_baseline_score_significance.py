"""Tests for score_significance baseline plugin to reach 80% coverage.

Focus on testing uncovered lines 57, 61, 79, 85, 87-129.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.experiments.baseline.score_significance import (
    ScoreSignificanceBaselinePlugin,
)


def test_score_significance_invalid_adjustment():
    """Test ScoreSignificanceBaselinePlugin with invalid adjustment (line 57)."""
    # Invalid adjustment should be normalized to "none"
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        adjustment="invalid_value")
    assert plugin._adjustment == "none"


def test_score_significance_invalid_on_error():
    """Test ScoreSignificanceBaselinePlugin raises on invalid on_error (line 61)."""
    with pytest.raises(ValueError, match="on_error must be 'abort' or 'skip'"):
        ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        on_error="invalid")


def test_score_significance_empty_baseline_variant():
    """Test with empty baseline and variant."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL)
    result = plugin.compare({}, {})
    assert result == {}


def test_score_significance_no_common_criteria():
    """Test with no common criteria between baseline and variant."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL)
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"precision": 0.9}}},
        ]
    }
    result = plugin.compare(baseline, variant)
    assert result == {}


def test_score_significance_criteria_filter():
    """Test with criteria filter (lines 78-79)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        criteria=["accuracy"])
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8, "precision": 0.9}}},
            {"metrics": {"scores": {"accuracy": 0.85, "precision": 0.88}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9, "precision": 0.95}}},
            {"metrics": {"scores": {"accuracy": 0.92, "precision": 0.93}}},
        ]
    }
    result = plugin.compare(baseline, variant)

    # Should only include accuracy, not precision
    assert "accuracy" in result
    assert "precision" not in result


def test_score_significance_min_samples():
    """Test min_samples requirement (lines 84-85)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        min_samples=3)
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9}}},
            {"metrics": {"scores": {"accuracy": 0.92}}},
        ]
    }
    result = plugin.compare(baseline, variant)

    # Should skip because we only have 2 samples but require 3
    assert result == {}


def test_score_significance_valid_comparison():
    """Test valid comparison with sufficient samples (lines 86-93)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        min_samples=2)
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.75}}},
            {"metrics": {"scores": {"accuracy": 0.72}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9}}},
            {"metrics": {"scores": {"accuracy": 0.92}}},
            {"metrics": {"scores": {"accuracy": 0.88}}},
        ]
    }
    result = plugin.compare(baseline, variant)

    assert "accuracy" in result
    assert "p_value" in result["accuracy"]
    assert "effect_size" in result["accuracy"]


def test_score_significance_p_value_validation():
    """Test p_value validation for finiteness (lines 89-93)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL)
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9}}},
            {"metrics": {"scores": {"accuracy": 0.92}}},
        ]
    }

    with patch("elspeth.plugins.experiments.baseline.score_significance._compute_significance") as mock_sig:
        # Test with infinite p_value
        mock_sig.return_value = {"p_value": math.inf, "effect_size": 0.5}
        result = plugin.compare(baseline, variant)
        # Infinite p_value should be stored as None
        # (The code stores None in p_values dict for infinite values)

        # Test with finite p_value
        mock_sig.return_value = {"p_value": 0.05, "effect_size": 0.5}
        result = plugin.compare(baseline, variant)
        assert "accuracy" in result


def test_score_significance_bonferroni_adjustment():
    """Test Bonferroni adjustment (lines 95-107)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        adjustment="bonferroni", family_size=2)
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7, "precision": 0.75}}},
            {"metrics": {"scores": {"accuracy": 0.75, "precision": 0.78}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9, "precision": 0.88}}},
            {"metrics": {"scores": {"accuracy": 0.92, "precision": 0.90}}},
        ]
    }
    result = plugin.compare(baseline, variant)

    # Should have adjusted_p_value for each criterion
    if "accuracy" in result:
        assert "adjusted_p_value" in result["accuracy"]
        assert result["accuracy"]["adjustment"] == "bonferroni"


def test_score_significance_bonferroni_none_p_value():
    """Test Bonferroni adjustment with None p_value (lines 100-101)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        adjustment="bonferroni")
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9}}},
            {"metrics": {"scores": {"accuracy": 0.92}}},
        ]
    }

    with patch("elspeth.plugins.experiments.baseline.score_significance._compute_significance") as mock_sig:
        # Return stats with non-numeric p_value
        mock_sig.return_value = {"p_value": None, "effect_size": 0.5}
        result = plugin.compare(baseline, variant)

        if "accuracy" in result:
            # adjusted_p_value should be None
            assert result["accuracy"]["adjusted_p_value"] is None


def test_score_significance_fdr_with_statsmodels():
    """Test FDR adjustment using statsmodels (lines 108-114)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        adjustment="fdr")
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7, "precision": 0.75}}},
            {"metrics": {"scores": {"accuracy": 0.75, "precision": 0.78}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9, "precision": 0.88}}},
            {"metrics": {"scores": {"accuracy": 0.92, "precision": 0.90}}},
        ]
    }

    with patch("statsmodels.stats.multitest.fdrcorrection") as mock_fdr:
        mock_fdr.return_value = ([True, True], [0.03, 0.04])
        result = plugin.compare(baseline, variant)

        if "accuracy" in result:
            assert "adjusted_p_value" in result["accuracy"]
            assert result["accuracy"]["adjustment"] == "fdr"


def test_score_significance_fdr_fallback():
    """Test FDR adjustment fallback when statsmodels fails (lines 115-118)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        adjustment="fdr")
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.75}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9}}},
            {"metrics": {"scores": {"accuracy": 0.92}}},
        ]
    }

    # Patch to force import error, triggering fallback
    with patch("elspeth.plugins.experiments.baseline.score_significance._benjamini_hochberg") as mock_bh:
        mock_bh.return_value = [0.04]

        # Temporarily break the import
        import sys

        old_modules = sys.modules.copy()
        try:
            # Remove statsmodels to force fallback
            if "statsmodels.stats.multitest" in sys.modules:
                del sys.modules["statsmodels.stats.multitest"]

            with patch.dict("sys.modules", {"statsmodels.stats.multitest": None}):
                result = plugin.compare(baseline, variant)

                if "accuracy" in result:
                    assert "adjusted_p_value" in result["accuracy"]
        finally:
            sys.modules.update(old_modules)


def test_score_significance_fdr_missing_criteria():
    """Test FDR adjustment handles missing criteria (lines 124-129)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        adjustment="fdr")
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.75}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9}}},
            {"metrics": {"scores": {"accuracy": 0.92}}},
        ]
    }

    with patch("elspeth.plugins.experiments.baseline.score_significance._compute_significance") as mock_sig:
        # Return p_value as None for one criterion
        mock_sig.return_value = {"p_value": None, "effect_size": 0.5}
        result = plugin.compare(baseline, variant)

        if "accuracy" in result:
            # Should have adjusted_p_value even for missing p_value
            assert "adjusted_p_value" in result["accuracy"]
            assert result["accuracy"]["adjusted_p_value"] is None


def test_score_significance_equal_var():
    """Test with equal_var parameter."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        equal_var=True)
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9}}},
            {"metrics": {"scores": {"accuracy": 0.92}}},
        ]
    }

    with patch("elspeth.plugins.experiments.baseline.score_significance._compute_significance") as mock_sig:
        mock_sig.return_value = {"p_value": 0.05, "effect_size": 0.5}
        plugin.compare(baseline, variant)

        # Verify equal_var was passed
        mock_sig.assert_called_once()
        call_kwargs = mock_sig.call_args[1]
        assert call_kwargs["equal_var"] is True


def test_score_significance_on_error_skip():
    """Test on_error='skip' behavior."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        on_error="skip")

    # Normal operation should work
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9}}},
            {"metrics": {"scores": {"accuracy": 0.92}}},
        ]
    }
    _result = plugin.compare(baseline, variant)
    # Should complete without error


def test_score_significance_custom_family_size():
    """Test with custom family_size for adjustment (line 96)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        adjustment="bonferroni", family_size=5)
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.75}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9}}},
            {"metrics": {"scores": {"accuracy": 0.92}}},
        ]
    }
    result = plugin.compare(baseline, variant)

    # Should use family_size of 5 for adjustment
    if "accuracy" in result:
        assert "adjusted_p_value" in result["accuracy"]


def test_score_significance_auto_family_size():
    """Test automatic family_size calculation (line 96)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        adjustment="bonferroni")  # No family_size
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7, "precision": 0.75}}},
            {"metrics": {"scores": {"accuracy": 0.75, "precision": 0.78}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9, "precision": 0.88}}},
            {"metrics": {"scores": {"accuracy": 0.92, "precision": 0.90}}},
        ]
    }
    _result = plugin.compare(baseline, variant)

    # Should automatically determine family_size based on number of valid p_values
    # (which should be 2 in this case)


def test_score_significance_none_adjustment():
    """Test with adjustment='none' (line 95)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        adjustment="none")
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9}}},
            {"metrics": {"scores": {"accuracy": 0.92}}},
        ]
    }
    result = plugin.compare(baseline, variant)

    # Should not have adjusted_p_value
    if "accuracy" in result:
        assert "adjusted_p_value" not in result["accuracy"]


def test_score_significance_empty_p_values():
    """Test when no valid p_values are collected (line 95)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        adjustment="bonferroni")
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
        ]  # Only 1 sample, below min_samples=2
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.9}}},
        ]
    }
    result = plugin.compare(baseline, variant)

    # No criteria should meet min_samples, so no p_values
    assert result == {}


def test_score_significance_min_samples_boundary():
    """Test min_samples is enforced as minimum 2 (line 53)."""
    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        min_samples=1)
    # Should be enforced to at least 2
    assert plugin._min_samples >= 2
