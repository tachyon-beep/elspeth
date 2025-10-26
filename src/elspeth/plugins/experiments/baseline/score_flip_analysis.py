"""ScoreFlipAnalysisAggregator - Aggregation plugin."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.plugin_registry import register_baseline_plugin
from elspeth.plugins.experiments._stats_helpers import (
    _collect_paired_scores_by_criterion,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

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


class ScoreFlipAnalysisAggregator(BasePlugin):
    """Analyze score direction changes (flips) between baseline and variant.

    Identifies fail→pass transitions, pass→fail transitions, major score drops,
    and major score gains. Useful for understanding where the variant changed
    scoring patterns most dramatically.

    Typical use cases: regression detection, improvement tracking, edge case analysis.
    """

    name = "score_flip_analysis"

    def __init__(
        self,
        *,
        criteria: list[str] | None = None,
        pass_threshold: float = 3.0,
        fail_threshold: float = 2.0,
        major_change: float = 2.0,
        on_error: str = "abort",
    ) -> None:
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # ADR-002-B: Immutable policy
            allow_downgrade=True  # ADR-002-B: Immutable policy
        )
        self._criteria = set(criteria) if criteria else None
        self._pass_threshold = float(pass_threshold)
        self._fail_threshold = float(fail_threshold)
        self._major_change = float(major_change)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("score_flip_analysis skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        # Get paired scores by criterion
        pairs = _collect_paired_scores_by_criterion(baseline, variant)

        if not pairs:
            return {}

        # Apply criteria filter
        if self._criteria is not None:
            pairs = {name: scores for name, scores in pairs.items() if name in self._criteria}

        if not pairs:
            return {}

        # Aggregate flips across all criteria
        flips: dict[str, list[tuple[float, float]]] = {
            "fail_to_pass": [],
            "pass_to_fail": [],
            "major_drops": [],
            "major_gains": [],
        }

        all_pairs: list[tuple[float, float]] = []
        for criterion_pairs in pairs.values():
            all_pairs.extend(criterion_pairs)

        for baseline_score, variant_score in all_pairs:
            delta = variant_score - baseline_score

            # Fail → Pass
            if baseline_score <= self._fail_threshold and variant_score >= self._pass_threshold:
                flips["fail_to_pass"].append((baseline_score, variant_score))

            # Pass → Fail
            elif baseline_score >= self._pass_threshold and variant_score <= self._fail_threshold:
                flips["pass_to_fail"].append((baseline_score, variant_score))

            # Major drops
            if delta <= -self._major_change:
                flips["major_drops"].append((baseline_score, variant_score))

            # Major gains
            elif delta >= self._major_change:
                flips["major_gains"].append((baseline_score, variant_score))

        # Per-criterion breakdown
        criteria_results: dict[str, Any] = {}
        for crit_name, criterion_pairs in pairs.items():
            crit_flips = {
                "fail_to_pass_count": 0,
                "pass_to_fail_count": 0,
                "major_drops_count": 0,
                "major_gains_count": 0,
            }

            for baseline_score, variant_score in criterion_pairs:
                delta = variant_score - baseline_score

                if baseline_score <= self._fail_threshold and variant_score >= self._pass_threshold:
                    crit_flips["fail_to_pass_count"] += 1

                if baseline_score >= self._pass_threshold and variant_score <= self._fail_threshold:
                    crit_flips["pass_to_fail_count"] += 1

                if delta <= -self._major_change:
                    crit_flips["major_drops_count"] += 1

                if delta >= self._major_change:
                    crit_flips["major_gains_count"] += 1

            crit_flips["net_flip_impact"] = crit_flips["fail_to_pass_count"] - crit_flips["pass_to_fail_count"]
            criteria_results[crit_name] = crit_flips

        # Overall results
        return {
            "fail_to_pass_count": len(flips["fail_to_pass"]),
            "pass_to_fail_count": len(flips["pass_to_fail"]),
            "major_drops_count": len(flips["major_drops"]),
            "major_gains_count": len(flips["major_gains"]),
            "net_flip_impact": len(flips["fail_to_pass"]) - len(flips["pass_to_fail"]),
            "examples": {k: [(round(b, 2), round(v, 2)) for b, v in pairs[:5]] for k, pairs in flips.items()},
            "criteria": criteria_results,
        }


def _create_score_flip_analysis(options: dict[str, Any], context: PluginContext) -> ScoreFlipAnalysisAggregator:
    """Create score_flip_analysis baseline plugin with smart security defaults."""
    return ScoreFlipAnalysisAggregator(
        criteria=options.get("criteria"),
        pass_threshold=float(options.get("pass_threshold", 3.0)),
        fail_threshold=float(options.get("fail_threshold", 2.0)),
        major_change=float(options.get("major_change", 2.0)),
        on_error=options.get("on_error", "abort"),
    )


register_baseline_plugin(
    "score_flip_analysis",
    _create_score_flip_analysis,
    schema=_SCORE_FLIP_SCHEMA,
)


_CATEGORY_SCHEMA = {
    "type": "object",
    "properties": {
        "category_field": {"type": "string"},
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 1},
        "top_n": {"type": "integer", "minimum": 1},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


__all__ = ["ScoreFlipAnalysisAggregator"]
