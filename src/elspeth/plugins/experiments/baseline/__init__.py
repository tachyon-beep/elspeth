"""Baseline comparison experiment plugins."""

from elspeth.plugins.experiments.baseline import (
    category_effects,
    criteria_effects,
    outlier_detection,
    referee_alignment,
    score_assumptions,
    score_bayesian,
    score_cliffs_delta,
    score_delta,
    score_distribution,
    score_flip_analysis,
    score_practical,
    score_significance,
)

__all__ = [
    "category_effects",
    "criteria_effects",
    "outlier_detection",
    "referee_alignment",
    "score_assumptions",
    "score_bayesian",
    "score_cliffs_delta",
    "score_delta",
    "score_distribution",
    "score_flip_analysis",
    "score_practical",
    "score_significance",
]
