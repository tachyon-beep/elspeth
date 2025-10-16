"""OutlierDetectionAggregator - Aggregation plugin."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Mapping

import numpy as np

from elspeth.core.experiments.plugin_registry import register_baseline_plugin

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_OUTLIER_SCHEMA = {
    "type": "object",
    "properties": {
        "top_n": {"type": "integer", "minimum": 1},
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_delta": {"type": "number", "minimum": 0},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class OutlierDetectionAggregator:
    """Identify rows with largest score disagreements between baseline and variant.

    This plugin finds cases where experiments disagree most, helping identify
    problematic inputs or edge cases. Computes per-row score deltas, sorts by
    magnitude, and returns configurable top N outliers with full details.

    Useful for: finding problematic test cases, edge case identification,
    quality assurance reviews.
    """

    name = "outlier_detection"

    def __init__(
        self,
        *,
        top_n: int = 10,
        criteria: list[str] | None = None,
        min_delta: float = 0.0,
        on_error: str = "abort",
    ) -> None:
        self._top_n = max(int(top_n), 1)
        self._criteria = set(criteria) if criteria else None
        self._min_delta = float(min_delta)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("outlier_detection skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        baseline_results = baseline.get("results", []) or []
        variant_results = variant.get("results", []) or []

        # Create ID mapping for paired comparison
        baseline_by_id: dict[Any, dict[str, Any]] = {}
        variant_by_id: dict[Any, dict[str, Any]] = {}

        for result in baseline_results:
            row = result.get("row") or {}
            row_id = row.get("id")
            if row_id is not None:
                baseline_by_id[row_id] = result

        for result in variant_results:
            row = result.get("row") or {}
            row_id = row.get("id")
            if row_id is not None:
                variant_by_id[row_id] = result

        common_ids = set(baseline_by_id.keys()) & set(variant_by_id.keys())
        if not common_ids:
            return {}

        # Compute outliers
        outliers: list[dict[str, Any]] = []

        for row_id in common_ids:
            b_result = baseline_by_id[row_id]
            v_result = variant_by_id[row_id]

            b_scores = self._extract_scores(b_result)
            v_scores = self._extract_scores(v_result)

            if not b_scores or not v_scores:
                continue

            # Compute mean delta across criteria
            b_mean = float(np.mean(list(b_scores.values())))
            v_mean = float(np.mean(list(v_scores.values())))
            delta = abs(v_mean - b_mean)

            if delta < self._min_delta:
                continue

            outliers.append(
                {
                    "id": row_id,
                    "baseline_mean": round(b_mean, 2),
                    "variant_mean": round(v_mean, 2),
                    "delta": round(delta, 2),
                    "direction": "higher" if v_mean > b_mean else "lower",
                    "baseline_scores": {k: round(v, 2) for k, v in b_scores.items()},
                    "variant_scores": {k: round(v, 2) for k, v in v_scores.items()},
                }
            )

        # Sort by delta magnitude (descending) and return top N
        outliers.sort(key=lambda x: x["delta"], reverse=True)
        top_outliers = outliers[: self._top_n]

        return {
            "top_outliers": top_outliers,
            "total_outliers_found": len(outliers),
            "requested_top_n": self._top_n,
        }

    def _extract_scores(self, result: dict[str, Any]) -> dict[str, float]:
        """Extract scores from result, filtering by criteria if specified."""
        metrics = result.get("metrics") or {}
        scores = metrics.get("scores") or {}

        if not isinstance(scores, Mapping):
            return {}

        extracted: dict[str, float] = {}
        for name, value in scores.items():
            if self._criteria and name not in self._criteria:
                continue
            try:
                num = float(value)
                if not math.isnan(num):
                    extracted[name] = num
            except (TypeError, ValueError):
                continue

        return extracted


register_baseline_plugin(
    "outlier_detection",
    lambda options, context: OutlierDetectionAggregator(
        top_n=int(options.get("top_n", 10)),
        criteria=options.get("criteria"),
        min_delta=float(options.get("min_delta", 0.0)),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_OUTLIER_SCHEMA,
)


_SCORE_FLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "pass_threshold": {"type": "number"},
        "fail_threshold": {"type": "number"},
        "major_change": {"type": "number", "minimum": 0},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


__all__ = ["OutlierDetectionAggregator"]
