"""ScoreRecommendationAggregator - Aggregation plugin."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Mapping

from elspeth.core.experiments.plugin_registry import register_aggregation_plugin
from elspeth.plugins.experiments.aggregators.score_stats import ScoreStatsAggregator

if TYPE_CHECKING:
    from elspeth.core.base.schema import DataFrameSchema

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "min_samples": {"type": "integer", "minimum": 0},
        "improvement_margin": {"type": "number"},
        "source_field": {"type": "string"},
        "flag_field": {"type": "string"},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class ScoreRecommendationAggregator:
    """Generate a lightweight recommendation based on score statistics."""

    name = "score_recommendation"

    def __init__(
        self,
        *,
        min_samples: int = 5,
        improvement_margin: float = 0.05,
        source_field: str = "scores",
        flag_field: str = "score_flags",
    ) -> None:
        self._min_samples = min_samples
        self._improvement_margin = improvement_margin
        self._stats = ScoreStatsAggregator(source_field=source_field, flag_field=flag_field)

    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        stats = self._stats.finalize(records)
        overall = stats.get("overall", {})
        criteria = stats.get("criteria", {})
        count = overall.get("count", 0)

        if count < self._min_samples:
            message = "Insufficient data for confident recommendation"
            best = None
        else:
            best = self._select_best(criteria)
            if not best:
                message = "No clear leader across criteria"
            else:
                message = self._build_message(best, criteria[best], overall)

        payload: dict[str, Any] = {
            "recommendation": message,
            "summary": overall,
        }
        if best:
            payload["best_criteria"] = best
            payload["best_stats"] = criteria[best]
        return payload

    def _select_best(self, criteria: Mapping[str, Mapping[str, Any]]) -> str | None:
        best_name = None
        best_mean = float("-inf")
        for name, summary in criteria.items():
            mean = summary.get("mean")
            if mean is None:
                continue
            if mean > best_mean:
                best_name = name
                best_mean = mean
        return best_name

    def _build_message(self, name: str, stats: Mapping[str, Any], overall: Mapping[str, Any]) -> str:
        mean = stats.get("mean")
        pass_rate = stats.get("pass_rate")
        overall_mean = overall.get("mean")

        clauses = [f"{name} leads with mean score {mean:.2f}" if mean is not None else f"{name} leads"]
        if pass_rate is not None:
            clauses.append(f"pass rate {pass_rate:.0%}")
        if overall_mean is not None and mean is not None:
            delta = mean - overall_mean
            if abs(delta) >= self._improvement_margin:
                direction = "above" if delta > 0 else "below"
                clauses.append(f"which is {abs(delta):.2f} {direction} overall average")
        return ", ".join(clauses)

    def input_schema(self) -> type["DataFrameSchema"] | None:
        """ScoreRecommendationAggregator does not require specific input columns."""
        return None


register_aggregation_plugin(
    "score_recommendation",
    lambda options, context: ScoreRecommendationAggregator(
        min_samples=int(options.get("min_samples", 5)),
        improvement_margin=float(options.get("improvement_margin", 0.05)),
        source_field=options.get("source_field", "scores"),
        flag_field=options.get("flag_field", "score_flags"),
    ),
    schema=_RECOMMENDATION_SCHEMA,
)


__all__ = ["ScoreRecommendationAggregator"]
