"""Tests for Priority 2 metric plugins: outlier detection, score flips, category effects, criteria effects."""

from __future__ import annotations

import pytest

from elspeth.plugins.experiments.baseline.category_effects import CategoryEffectsAggregator
from elspeth.plugins.experiments.baseline.criteria_effects import CriteriaEffectsBaselinePlugin
from elspeth.plugins.experiments.baseline.outlier_detection import OutlierDetectionAggregator
from elspeth.plugins.experiments.baseline.score_flip_analysis import ScoreFlipAnalysisAggregator

# =====================================================================
# Outlier Detection Tests
# =====================================================================


def test_outlier_detection_finds_top_outliers() -> None:
    """Test that outlier detection identifies rows with largest deltas."""
    plugin = OutlierDetectionAggregator(top_n=3)

    baseline = {
        "results": [
            {"row": {"id": 1}, "metrics": {"scores": {"quality": 4.5}}},
            {"row": {"id": 2}, "metrics": {"scores": {"quality": 3.0}}},
            {"row": {"id": 3}, "metrics": {"scores": {"quality": 2.5}}},
            {"row": {"id": 4}, "metrics": {"scores": {"quality": 4.0}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"id": 1}, "metrics": {"scores": {"quality": 4.6}}},  # delta 0.1
            {"row": {"id": 2}, "metrics": {"scores": {"quality": 1.0}}},  # delta 2.0
            {"row": {"id": 3}, "metrics": {"scores": {"quality": 5.0}}},  # delta 2.5
            {"row": {"id": 4}, "metrics": {"scores": {"quality": 3.8}}},  # delta 0.2
        ]
    }

    result = plugin.compare(baseline, variant)

    assert result["total_outliers_found"] == 4
    assert result["requested_top_n"] == 3
    assert len(result["top_outliers"]) == 3

    # Check that outliers are sorted by delta descending
    assert result["top_outliers"][0]["id"] == 3
    assert result["top_outliers"][0]["delta"] == 2.5
    assert result["top_outliers"][1]["id"] == 2
    assert result["top_outliers"][1]["delta"] == 2.0
    assert result["top_outliers"][2]["id"] == 4
    assert result["top_outliers"][2]["delta"] == 0.2


def test_outlier_detection_with_min_delta() -> None:
    """Test that min_delta filters out small differences."""
    plugin = OutlierDetectionAggregator(top_n=10, min_delta=1.0)

    baseline = {
        "results": [
            {"row": {"id": 1}, "metrics": {"scores": {"quality": 4.0}}},
            {"row": {"id": 2}, "metrics": {"scores": {"quality": 3.0}}},
            {"row": {"id": 3}, "metrics": {"scores": {"quality": 2.0}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"id": 1}, "metrics": {"scores": {"quality": 4.5}}},  # delta 0.5 (filtered)
            {"row": {"id": 2}, "metrics": {"scores": {"quality": 1.0}}},  # delta 2.0 (included)
            {"row": {"id": 3}, "metrics": {"scores": {"quality": 3.5}}},  # delta 1.5 (included)
        ]
    }

    result = plugin.compare(baseline, variant)

    assert result["total_outliers_found"] == 2
    assert len(result["top_outliers"]) == 2
    assert all(o["delta"] >= 1.0 for o in result["top_outliers"])


def test_outlier_detection_with_criteria_filter() -> None:
    """Test that criteria filtering works for outlier detection."""
    plugin = OutlierDetectionAggregator(top_n=10, criteria=["quality"])

    baseline = {
        "results": [
            {
                "row": {"id": 1},
                "metrics": {"scores": {"quality": 4.0, "safety": 5.0}},
            }
        ]
    }

    variant = {
        "results": [
            {
                "row": {"id": 1},
                "metrics": {"scores": {"quality": 2.0, "safety": 1.0}},
            }
        ]
    }

    result = plugin.compare(baseline, variant)

    # Should only use quality scores (delta 2.0), not safety (delta 4.0)
    assert len(result["top_outliers"]) == 1
    assert result["top_outliers"][0]["baseline_mean"] == 4.0
    assert result["top_outliers"][0]["variant_mean"] == 2.0
    assert "quality" in result["top_outliers"][0]["baseline_scores"]
    assert "safety" not in result["top_outliers"][0]["baseline_scores"]


def test_outlier_detection_with_direction() -> None:
    """Test that outlier direction (higher/lower) is reported correctly."""
    plugin = OutlierDetectionAggregator(top_n=10)

    baseline = {
        "results": [
            {"row": {"id": 1}, "metrics": {"scores": {"quality": 3.0}}},
            {"row": {"id": 2}, "metrics": {"scores": {"quality": 3.0}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"id": 1}, "metrics": {"scores": {"quality": 5.0}}},
            {"row": {"id": 2}, "metrics": {"scores": {"quality": 1.0}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    higher = [o for o in result["top_outliers"] if o["direction"] == "higher"]
    lower = [o for o in result["top_outliers"] if o["direction"] == "lower"]

    assert len(higher) == 1
    assert higher[0]["id"] == 1
    assert len(lower) == 1
    assert lower[0]["id"] == 2


def test_outlier_detection_empty_results() -> None:
    """Test that outlier detection handles empty results gracefully."""
    plugin = OutlierDetectionAggregator(top_n=10)

    baseline = {"results": []}
    variant = {"results": []}

    result = plugin.compare(baseline, variant)

    assert result == {}


def test_outlier_detection_no_common_ids() -> None:
    """Test that outlier detection handles disjoint ID sets."""
    plugin = OutlierDetectionAggregator(top_n=10)

    baseline = {"results": [{"row": {"id": 1}, "metrics": {"scores": {"quality": 4.0}}}]}

    variant = {"results": [{"row": {"id": 2}, "metrics": {"scores": {"quality": 4.0}}}]}

    result = plugin.compare(baseline, variant)

    assert result == {}


def test_outlier_detection_on_error_skip() -> None:
    """Test that on_error=skip suppresses exceptions."""
    plugin = OutlierDetectionAggregator(top_n=10, on_error="skip")

    # Malformed payload
    baseline = {"results": [{"row": None}]}
    variant = {"results": [{"row": None}]}

    result = plugin.compare(baseline, variant)

    # Should not raise, return empty
    assert result == {}


# =====================================================================
# Score Flip Analysis Tests
# =====================================================================


def test_score_flip_analysis_fail_to_pass() -> None:
    """Test detection of fail→pass transitions."""
    plugin = ScoreFlipAnalysisAggregator(fail_threshold=2.0, pass_threshold=3.0)

    baseline = {
        "results": [
            {"metrics": {"scores": {"quality": 1.0}}},
            {"metrics": {"scores": {"quality": 2.0}}},
            {"metrics": {"scores": {"quality": 4.0}}},
        ]
    }

    variant = {
        "results": [
            {"metrics": {"scores": {"quality": 4.0}}},  # 1→4: fail→pass
            {"metrics": {"scores": {"quality": 3.5}}},  # 2→3.5: fail→pass
            {"metrics": {"scores": {"quality": 4.2}}},  # 4→4.2: no flip
        ]
    }

    result = plugin.compare(baseline, variant)

    assert result["fail_to_pass_count"] == 2
    assert result["pass_to_fail_count"] == 0
    assert result["net_flip_impact"] == 2
    assert len(result["examples"]["fail_to_pass"]) == 2


def test_score_flip_analysis_pass_to_fail() -> None:
    """Test detection of pass→fail transitions."""
    plugin = ScoreFlipAnalysisAggregator(fail_threshold=2.0, pass_threshold=3.0)

    baseline = {
        "results": [
            {"metrics": {"scores": {"quality": 4.0}}},
            {"metrics": {"scores": {"quality": 5.0}}},
        ]
    }

    variant = {
        "results": [
            {"metrics": {"scores": {"quality": 1.0}}},  # 4→1: pass→fail
            {"metrics": {"scores": {"quality": 2.0}}},  # 5→2: pass→fail
        ]
    }

    result = plugin.compare(baseline, variant)

    assert result["fail_to_pass_count"] == 0
    assert result["pass_to_fail_count"] == 2
    assert result["net_flip_impact"] == -2
    assert len(result["examples"]["pass_to_fail"]) == 2


def test_score_flip_analysis_major_changes() -> None:
    """Test detection of major score drops and gains."""
    plugin = ScoreFlipAnalysisAggregator(major_change=2.0)

    baseline = {
        "results": [
            {"metrics": {"scores": {"quality": 5.0}}},
            {"metrics": {"scores": {"quality": 2.0}}},
            {"metrics": {"scores": {"quality": 3.0}}},
        ]
    }

    variant = {
        "results": [
            {"metrics": {"scores": {"quality": 2.5}}},  # 5→2.5: drop 2.5 (major drop)
            {"metrics": {"scores": {"quality": 4.5}}},  # 2→4.5: gain 2.5 (major gain)
            {"metrics": {"scores": {"quality": 3.1}}},  # 3→3.1: no major change
        ]
    }

    result = plugin.compare(baseline, variant)

    assert result["major_drops_count"] == 1
    assert result["major_gains_count"] == 1
    assert len(result["examples"]["major_drops"]) == 1
    assert len(result["examples"]["major_gains"]) == 1


def test_score_flip_analysis_per_criterion() -> None:
    """Test that per-criterion breakdown is computed."""
    plugin = ScoreFlipAnalysisAggregator()

    baseline = {
        "results": [
            {"metrics": {"scores": {"quality": 2.0, "safety": 4.0}}},
            {"metrics": {"scores": {"quality": 4.0, "safety": 2.0}}},
        ]
    }

    variant = {
        "results": [
            {"metrics": {"scores": {"quality": 4.0, "safety": 2.0}}},
            {"metrics": {"scores": {"quality": 2.0, "safety": 4.0}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    assert "criteria" in result
    assert "quality" in result["criteria"]
    assert "safety" in result["criteria"]

    # Quality: one fail→pass, one pass→fail
    assert result["criteria"]["quality"]["fail_to_pass_count"] == 1
    assert result["criteria"]["quality"]["pass_to_fail_count"] == 1
    assert result["criteria"]["quality"]["net_flip_impact"] == 0

    # Safety: one pass→fail, one fail→pass
    assert result["criteria"]["safety"]["fail_to_pass_count"] == 1
    assert result["criteria"]["safety"]["pass_to_fail_count"] == 1


def test_score_flip_analysis_criteria_filter() -> None:
    """Test that criteria filtering applies to flip analysis."""
    plugin = ScoreFlipAnalysisAggregator(criteria=["quality"])

    baseline = {"results": [{"metrics": {"scores": {"quality": 2.0, "safety": 2.0}}}]}

    variant = {"results": [{"metrics": {"scores": {"quality": 4.0, "safety": 4.0}}}]}

    result = plugin.compare(baseline, variant)

    # Only quality flips should count
    assert result["fail_to_pass_count"] == 1
    assert "quality" in result["criteria"]
    assert "safety" not in result["criteria"]


def test_score_flip_analysis_empty_results() -> None:
    """Test that flip analysis handles empty results."""
    plugin = ScoreFlipAnalysisAggregator()

    baseline = {"results": []}
    variant = {"results": []}

    result = plugin.compare(baseline, variant)

    assert result == {}


def test_score_flip_analysis_on_error_skip() -> None:
    """Test that on_error=skip suppresses exceptions."""
    plugin = ScoreFlipAnalysisAggregator(on_error="skip")

    # Malformed payload
    baseline = {"results": [{"metrics": None}]}
    variant = {"results": [{"metrics": None}]}

    result = plugin.compare(baseline, variant)

    assert result == {}


# =====================================================================
# Category Effects Tests
# =====================================================================


def test_category_effects_discovers_categories() -> None:
    """Test that category effects discovers categories from baseline."""
    plugin = CategoryEffectsAggregator(category_field="document_type")

    baseline = {
        "results": [
            {"row": {"document_type": "legal"}, "metrics": {"scores": {"quality": 3.0}}},
            {"row": {"document_type": "technical"}, "metrics": {"scores": {"quality": 4.0}}},
            {"row": {"document_type": "legal"}, "metrics": {"scores": {"quality": 3.5}}},
            {"row": {"document_type": "technical"}, "metrics": {"scores": {"quality": 4.2}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"document_type": "legal"}, "metrics": {"scores": {"quality": 4.0}}},
            {"row": {"document_type": "technical"}, "metrics": {"scores": {"quality": 5.0}}},
            {"row": {"document_type": "legal"}, "metrics": {"scores": {"quality": 4.5}}},
            {"row": {"document_type": "technical"}, "metrics": {"scores": {"quality": 5.2}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    assert result["total_categories"] == 2
    assert "category_impacts" in result
    assert "legal" in result["category_impacts"]
    assert "technical" in result["category_impacts"]


def test_category_effects_computes_statistics() -> None:
    """Test that category effects computes correct statistics."""
    plugin = CategoryEffectsAggregator(category_field="category", min_samples=2)

    baseline = {
        "results": [
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 2.0}}},
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 3.0}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 4.0}}},
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 5.0}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    cat_a = result["category_impacts"]["A"]
    assert cat_a["baseline_mean"] == 2.5
    assert cat_a["variant_mean"] == 4.5
    assert cat_a["delta"] == 2.0
    assert cat_a["effect_size"] is not None
    assert cat_a["baseline_samples"] == 2
    assert cat_a["variant_samples"] == 2


def test_category_effects_ranks_by_effect_size() -> None:
    """Test that categories are ranked by absolute effect size or delta."""
    plugin = CategoryEffectsAggregator(top_n=2)

    baseline = {
        "results": [
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 3.0}}},
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 3.1}}},
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 2.9}}},
            {"row": {"category": "B"}, "metrics": {"scores": {"quality": 3.0}}},
            {"row": {"category": "B"}, "metrics": {"scores": {"quality": 3.1}}},
            {"row": {"category": "B"}, "metrics": {"scores": {"quality": 2.9}}},
            {"row": {"category": "C"}, "metrics": {"scores": {"quality": 3.0}}},
            {"row": {"category": "C"}, "metrics": {"scores": {"quality": 3.1}}},
            {"row": {"category": "C"}, "metrics": {"scores": {"quality": 2.9}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 5.0}}},  # +2.0
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 5.1}}},
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 4.9}}},
            {"row": {"category": "B"}, "metrics": {"scores": {"quality": 5.5}}},  # +2.5
            {"row": {"category": "B"}, "metrics": {"scores": {"quality": 5.6}}},
            {"row": {"category": "B"}, "metrics": {"scores": {"quality": 5.4}}},
            {"row": {"category": "C"}, "metrics": {"scores": {"quality": 3.2}}},  # +0.2
            {"row": {"category": "C"}, "metrics": {"scores": {"quality": 3.3}}},
            {"row": {"category": "C"}, "metrics": {"scores": {"quality": 3.1}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    most_affected = result["most_affected"]
    least_affected = result["least_affected"]

    assert len(most_affected) == 2
    # Check that most affected have larger absolute deltas than least affected
    most_deltas = [abs(item["delta"]) for item in most_affected]
    least_deltas = [abs(item["delta"]) for item in least_affected]

    assert len(most_deltas) > 0
    assert len(least_deltas) > 0
    # Most affected should have larger changes
    assert min(most_deltas) >= max(least_deltas)


def test_category_effects_min_samples() -> None:
    """Test that min_samples filters out small categories."""
    plugin = CategoryEffectsAggregator(min_samples=3)

    baseline = {
        "results": [
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 3.0}}},
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 3.0}}},
            {"row": {"category": "B"}, "metrics": {"scores": {"quality": 3.0}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 5.0}}},
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 5.0}}},
            {"row": {"category": "B"}, "metrics": {"scores": {"quality": 5.0}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Category A has 2 samples (< 3), B has 1 sample (< 3), neither should be included
    assert result == {}


def test_category_effects_criteria_filter() -> None:
    """Test that criteria filtering works for category effects."""
    plugin = CategoryEffectsAggregator(criteria=["quality"])

    baseline = {
        "results": [
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 2.0, "safety": 5.0}}},
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 3.0, "safety": 5.0}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 4.0, "safety": 1.0}}},
            {"row": {"category": "A"}, "metrics": {"scores": {"quality": 5.0, "safety": 1.0}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Should compute based only on quality scores (mean 2.5→4.5)
    cat_a = result["category_impacts"]["A"]
    assert cat_a["baseline_mean"] == 2.5
    assert cat_a["variant_mean"] == 4.5


def test_category_effects_empty_results() -> None:
    """Test that category effects handles empty results."""
    plugin = CategoryEffectsAggregator()

    baseline = {"results": []}
    variant = {"results": []}

    result = plugin.compare(baseline, variant)

    assert result == {}


def test_category_effects_on_error_skip() -> None:
    """Test that on_error=skip suppresses exceptions."""
    plugin = CategoryEffectsAggregator(on_error="skip")

    # Malformed payload
    baseline = {"results": [{"row": None}]}
    variant = {"results": [{"row": None}]}

    result = plugin.compare(baseline, variant)

    assert result == {}


# =====================================================================
# Criteria Effects Tests
# =====================================================================


def test_criteria_effects_per_criterion_stats() -> None:
    """Test that criteria effects computes per-criterion statistics."""
    plugin = CriteriaEffectsBaselinePlugin()

    baseline = {
        "results": [
            {"metrics": {"scores": {"quality": 2.0, "safety": 4.0}}},
            {"metrics": {"scores": {"quality": 3.0, "safety": 5.0}}},
        ]
    }

    variant = {
        "results": [
            {"metrics": {"scores": {"quality": 4.0, "safety": 3.0}}},
            {"metrics": {"scores": {"quality": 5.0, "safety": 2.0}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    assert "quality" in result
    assert "safety" in result

    # Quality: 2.5 → 4.5 (delta +2.0)
    assert result["quality"]["baseline_mean"] == 2.5
    assert result["quality"]["variant_mean"] == 4.5
    assert result["quality"]["delta"] == 2.0
    assert result["quality"]["effect_size"] is not None

    # Safety: 4.5 → 2.5 (delta -2.0)
    assert result["safety"]["baseline_mean"] == 4.5
    assert result["safety"]["variant_mean"] == 2.5
    assert result["safety"]["delta"] == -2.0
    assert result["safety"]["effect_size"] is not None


def test_criteria_effects_mann_whitney_u() -> None:
    """Test that Mann-Whitney U test p-values are computed."""
    plugin = CriteriaEffectsBaselinePlugin()

    baseline = {
        "results": [
            {"metrics": {"scores": {"quality": 2.0}}},
            {"metrics": {"scores": {"quality": 2.1}}},
            {"metrics": {"scores": {"quality": 2.2}}},
            {"metrics": {"scores": {"quality": 2.0}}},
            {"metrics": {"scores": {"quality": 2.1}}},
            {"metrics": {"scores": {"quality": 2.2}}},
            {"metrics": {"scores": {"quality": 2.0}}},
            {"metrics": {"scores": {"quality": 2.1}}},
        ]
    }

    variant = {
        "results": [
            {"metrics": {"scores": {"quality": 5.0}}},
            {"metrics": {"scores": {"quality": 5.1}}},
            {"metrics": {"scores": {"quality": 5.2}}},
            {"metrics": {"scores": {"quality": 5.0}}},
            {"metrics": {"scores": {"quality": 5.1}}},
            {"metrics": {"scores": {"quality": 5.2}}},
            {"metrics": {"scores": {"quality": 5.0}}},
            {"metrics": {"scores": {"quality": 5.1}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    assert "quality" in result
    assert result["quality"]["p_value"] is not None
    # With large sample and clear separation, should be significant
    assert result["quality"]["significant"] is True


def test_criteria_effects_significance_flag() -> None:
    """Test that significance flag is computed based on alpha threshold."""
    plugin = CriteriaEffectsBaselinePlugin(alpha=0.05)

    baseline = {
        "results": [
            {"metrics": {"scores": {"quality": 3.0}}},
            {"metrics": {"scores": {"quality": 3.1}}},
            {"metrics": {"scores": {"quality": 2.9}}},
        ]
    }

    variant = {
        "results": [
            {"metrics": {"scores": {"quality": 3.0}}},
            {"metrics": {"scores": {"quality": 3.1}}},
            {"metrics": {"scores": {"quality": 2.9}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    assert "quality" in result
    # With identical distributions, should not be significant
    if result["quality"]["p_value"] is not None:
        # p_value should be high (close to 1.0) for identical distributions
        assert result["quality"]["p_value"] > 0.05
        assert result["quality"]["significant"] is False


def test_criteria_effects_criteria_filter() -> None:
    """Test that criteria filtering works."""
    plugin = CriteriaEffectsBaselinePlugin(criteria=["quality"])

    baseline = {
        "results": [
            {"metrics": {"scores": {"quality": 2.0, "safety": 2.0}}},
            {"metrics": {"scores": {"quality": 3.0, "safety": 3.0}}},
        ]
    }

    variant = {
        "results": [
            {"metrics": {"scores": {"quality": 4.0, "safety": 4.0}}},
            {"metrics": {"scores": {"quality": 5.0, "safety": 5.0}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    assert "quality" in result
    assert "safety" not in result


def test_criteria_effects_min_samples() -> None:
    """Test that min_samples filters criteria with insufficient data."""
    plugin = CriteriaEffectsBaselinePlugin(min_samples=3)

    baseline = {
        "results": [
            {"metrics": {"scores": {"quality": 2.0}}},
            {"metrics": {"scores": {"quality": 3.0}}},
        ]
    }

    variant = {
        "results": [
            {"metrics": {"scores": {"quality": 4.0}}},
            {"metrics": {"scores": {"quality": 5.0}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Only 2 samples, min_samples=3, should not be included
    assert result == {}


def test_criteria_effects_sample_counts() -> None:
    """Test that sample counts are reported correctly."""
    plugin = CriteriaEffectsBaselinePlugin()

    baseline = {
        "results": [
            {"metrics": {"scores": {"quality": 2.0}}},
            {"metrics": {"scores": {"quality": 3.0}}},
            {"metrics": {"scores": {"quality": 3.5}}},
        ]
    }

    variant = {
        "results": [
            {"metrics": {"scores": {"quality": 4.0}}},
            {"metrics": {"scores": {"quality": 5.0}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    assert result["quality"]["n_baseline"] == 3
    assert result["quality"]["n_variant"] == 2


def test_criteria_effects_empty_results() -> None:
    """Test that criteria effects handles empty results."""
    plugin = CriteriaEffectsBaselinePlugin()

    baseline = {"results": []}
    variant = {"results": []}

    result = plugin.compare(baseline, variant)

    assert result == {}


def test_criteria_effects_on_error_skip() -> None:
    """Test that on_error=skip suppresses exceptions."""
    plugin = CriteriaEffectsBaselinePlugin(on_error="skip")

    # Malformed payload
    baseline = {"results": [{"metrics": None}]}
    variant = {"results": [{"metrics": None}]}

    result = plugin.compare(baseline, variant)

    assert result == {}


# =====================================================================
# Schema Validation Tests
# =====================================================================


def test_outlier_detection_invalid_on_error() -> None:
    """Test that invalid on_error value raises ValueError."""
    with pytest.raises(ValueError, match="on_error must be 'abort' or 'skip'"):
        OutlierDetectionAggregator(on_error="invalid")


def test_score_flip_analysis_invalid_on_error() -> None:
    """Test that invalid on_error value raises ValueError."""
    with pytest.raises(ValueError, match="on_error must be 'abort' or 'skip'"):
        ScoreFlipAnalysisAggregator(on_error="invalid")


def test_category_effects_invalid_on_error() -> None:
    """Test that invalid on_error value raises ValueError."""
    with pytest.raises(ValueError, match="on_error must be 'abort' or 'skip'"):
        CategoryEffectsAggregator(on_error="invalid")


def test_criteria_effects_invalid_on_error() -> None:
    """Test that invalid on_error value raises ValueError."""
    with pytest.raises(ValueError, match="on_error must be 'abort' or 'skip'"):
        CriteriaEffectsBaselinePlugin(on_error="invalid")
