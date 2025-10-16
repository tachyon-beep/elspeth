"""Experiment plugin implementations used by default."""

# Import all plugin modules to trigger registration
from elspeth.plugins.experiments import (
    early_stop,  # noqa: F401
    prompt_variants,  # noqa: F401
    validation,  # noqa: F401
)
from elspeth.plugins.experiments.aggregators import (  # noqa: F401
    cost_summary,
    latency_summary,
    rationale_analysis,
    score_agreement,
    score_power,
    score_recommendation,
    score_stats,
    score_variant_ranking,
)
from elspeth.plugins.experiments.baseline import (  # noqa: F401
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
from elspeth.plugins.experiments.row import score_extractor  # noqa: F401

__all__ = [
    "early_stop",
    "prompt_variants",
    "validation",
    # Aggregators
    "cost_summary",
    "latency_summary",
    "rationale_analysis",
    "score_agreement",
    "score_power",
    "score_recommendation",
    "score_stats",
    "score_variant_ranking",
    # Baselines
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
    # Row plugins
    "score_extractor",
]
