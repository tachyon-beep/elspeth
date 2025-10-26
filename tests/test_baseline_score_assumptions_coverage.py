"""Coverage tests for ScoreAssumptionsBaselinePlugin to reach 80% coverage.

Focuses on uncovered lines:
- Line 51: Invalid on_error value
- Line 65: scipy_stats is None check
- Line 70: Criteria filtering
- Line 86-89: Baseline normality test exceptions
- Line 99-102: Variant normality test exceptions
- Line 111-114: Variance test exceptions
"""

from __future__ import annotations

import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.experiments.baseline.score_assumptions import ScoreAssumptionsBaselinePlugin


def test_invalid_on_error_raises():
    """Test that invalid on_error raises ValueError - line 51."""
    with pytest.raises(ValueError, match="on_error must be 'abort' or 'skip'"):
        ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, on_error="invalid")


def test_criteria_filtering():
    """Test criteria filtering - line 70."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, criteria=["accuracy"], min_samples=3)

    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7, "precision": 0.6}}},
            {"metrics": {"scores": {"accuracy": 0.8, "precision": 0.65}}},
            {"metrics": {"scores": {"accuracy": 0.75, "precision": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.72, "precision": 0.68}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8, "precision": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.85, "precision": 0.75}}},
            {"metrics": {"scores": {"accuracy": 0.82, "precision": 0.72}}},
            {"metrics": {"scores": {"accuracy": 0.88, "precision": 0.78}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Only accuracy should be in results (precision filtered)
    assert "accuracy" in result
    assert "precision" not in result


def test_insufficient_baseline_samples():
    """Test handling when baseline has insufficient samples - line 89."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, min_samples=3)

    # Only 2 baseline samples, 4 variant samples
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.8}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
            {"metrics": {"scores": {"accuracy": 0.82}}},
            {"metrics": {"scores": {"accuracy": 0.88}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Baseline should be None (insufficient samples)
    assert result["accuracy"]["baseline"] is None
    # Variant should have results (enough samples)
    assert result["accuracy"]["variant"] is not None


def test_insufficient_variant_samples():
    """Test handling when variant has insufficient samples - line 102."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, min_samples=3)

    # 4 baseline samples, only 2 variant samples
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.75}}},
            {"metrics": {"scores": {"accuracy": 0.72}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Baseline should have results (enough samples)
    assert result["accuracy"]["baseline"] is not None
    # Variant should be None (insufficient samples)
    assert result["accuracy"]["variant"] is None


def test_insufficient_samples_for_variance_test():
    """Test handling when samples insufficient for variance test - line 114."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, min_samples=3)  # min_samples >= 3

    # Only 1 sample each (insufficient for normality/variance tests)
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Should have no entry for accuracy (insufficient samples)
    # Or if present, all should be None
    if "accuracy" in result:
        assert result["accuracy"]["baseline"] is None
        assert result["accuracy"]["variant"] is None
        assert result["accuracy"]["variance"] is None
    else:
        # Empty result is also valid
        assert result == {}


def test_empty_results():
    """Test with completely empty results."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL)

    baseline = {"results": []}
    variant = {"results": []}

    result = plugin.compare(baseline, variant)
    assert result == {}


def test_normality_tests_with_minimal_data():
    """Test normality tests with exactly min_samples."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, min_samples=3, alpha=0.05)

    # Exactly 3 samples for baseline and variant
    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.71}}},
            {"metrics": {"scores": {"accuracy": 0.72}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.81}}},
            {"metrics": {"scores": {"accuracy": 0.82}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Should have all tests
    assert "accuracy" in result
    assert "baseline" in result["accuracy"]
    assert "variant" in result["accuracy"]
    assert "variance" in result["accuracy"]

    # Should have normality results
    assert "statistic" in result["accuracy"]["baseline"]
    assert "p_value" in result["accuracy"]["baseline"]
    assert "is_normal" in result["accuracy"]["baseline"]
    assert "samples" in result["accuracy"]["baseline"]


def test_variance_test_with_exactly_two_samples():
    """Test variance test with exactly 2 samples each - line 103."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, min_samples=2)

    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.8}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.75}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Variance test should be present (has 2+ samples each)
    assert result["accuracy"]["variance"] is not None
    assert "statistic" in result["accuracy"]["variance"]
    assert "p_value" in result["accuracy"]["variance"]


def test_no_common_criteria():
    """Test when baseline and variant have no common criteria."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL)

    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.75}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"precision": 0.8}}},
            {"metrics": {"scores": {"precision": 0.85}}},
            {"metrics": {"scores": {"precision": 0.82}}},
        ]
    }

    result = plugin.compare(baseline, variant)
    assert result == {}


def test_mixed_missing_scores():
    """Test with some records missing scores."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, min_samples=3)

    baseline = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.7}}},
            {"metrics": {"scores": {}}},  # Missing accuracy
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {}},  # Missing scores entirely
            {"metrics": {"scores": {"accuracy": 0.75}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"accuracy": 0.8}}},
            {"metrics": {"scores": {"accuracy": 0.85}}},
            {"metrics": {"scores": {"accuracy": 0.82}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Should still work with 3 valid baseline samples
    assert "accuracy" in result


def test_min_samples_enforced_to_minimum():
    """Test that min_samples is enforced to be at least 3."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, min_samples=1)
    assert plugin._min_samples == 3

    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, min_samples=0)
    assert plugin._min_samples == 3

    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, min_samples=-5)
    assert plugin._min_samples == 3


def test_on_error_abort_default():
    """Test that on_error defaults to abort."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL)
    assert plugin._on_error == "abort"


def test_on_error_skip():
    """Test on_error='skip' mode."""
    plugin = ScoreAssumptionsBaselinePlugin(security_level=SecurityLevel.OFFICIAL, on_error="skip")
    assert plugin._on_error == "skip"
