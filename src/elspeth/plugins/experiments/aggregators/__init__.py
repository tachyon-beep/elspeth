"""Aggregation experiment plugins."""

from elspeth.plugins.experiments.aggregators import (
    cost_summary,
    latency_summary,
    rationale_analysis,
    score_agreement,
    score_power,
    score_recommendation,
    score_stats,
    score_variant_ranking,
)

__all__ = [
    "cost_summary",
    "latency_summary",
    "rationale_analysis",
    "score_agreement",
    "score_power",
    "score_recommendation",
    "score_stats",
    "score_variant_ranking",
]
