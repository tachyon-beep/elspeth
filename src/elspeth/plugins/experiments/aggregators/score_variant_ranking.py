"""ScoreVariantRankingAggregator - Aggregation plugin."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Mapping

import numpy as np

from elspeth.core.experiments.plugin_registry import register_aggregation_plugin

if TYPE_CHECKING:
    from elspeth.core.base.schema import DataFrameSchema

logger = logging.getLogger(__name__)


class ScoreVariantRankingAggregator:
    """Compute a simple composite ranking score for an experiment."""

    name = "score_variant_ranking"

    def __init__(self, *, threshold: float = 0.7, weight_mean: float = 1.0, weight_pass: float = 1.0) -> None:
        self._threshold = float(threshold)
        self._weight_mean = float(weight_mean)
        self._weight_pass = float(weight_pass)

    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        values = []
        pass_count = 0
        for record in records:
            metrics = record.get("metrics") or {}
            # Prefer aggregated "score" field, fallback to mean of per-criteria
            base_value = metrics.get("score")
            if base_value is None and isinstance(metrics.get("scores"), Mapping):
                scores_map = metrics["scores"]
                try:
                    numbers = [float(v) for v in scores_map.values()]
                except (TypeError, ValueError):
                    numbers = []
                if numbers:
                    base_value = float(np.mean(numbers))
            if base_value is None:
                continue
            try:
                number = float(base_value)
            except (TypeError, ValueError):
                continue
            if math.isnan(number):
                continue
            values.append(number)
            if number >= self._threshold:
                pass_count += 1
        if not values:
            return {}
        arr = np.asarray(values, dtype=float)
        mean = float(arr.mean())
        median = float(np.median(arr))
        score = self._weight_mean * mean + self._weight_pass * (pass_count / len(values))
        return {
            "samples": len(values),
            "mean": mean,
            "median": median,
            "min": float(arr.min()),
            "max": float(arr.max()),
            "threshold": self._threshold,
            "pass_rate": pass_count / len(values),
            "composite_score": score,
        }

    def input_schema(self) -> type["DataFrameSchema"] | None:
        """ScoreVariantRankingAggregator does not require specific input columns."""
        return None


register_aggregation_plugin(
    "score_variant_ranking",
    lambda options, context: ScoreVariantRankingAggregator(
        threshold=float(options.get("threshold", 0.7)),
        weight_mean=float(options.get("weight_mean", 1.0)),
        weight_pass=float(options.get("weight_pass", 1.0)),
    ),
    schema={
        "type": "object",
        "properties": {
            "threshold": {"type": "number"},
            "weight_mean": {"type": "number"},
            "weight_pass": {"type": "number"},
        },
        "additionalProperties": True,
    },
)


__all__ = ["ScoreVariantRankingAggregator"]
