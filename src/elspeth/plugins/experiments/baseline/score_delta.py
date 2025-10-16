"""ScoreDeltaBaselinePlugin - Baseline comparison plugin."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Mapping

from elspeth.core.experiments.plugin_registry import register_baseline_plugin

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_DELTA_SCHEMA = {
    "type": "object",
    "properties": {
        "metric": {"type": "string"},
        "criteria": {"type": "array", "items": {"type": "string"}},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class ScoreDeltaBaselinePlugin:
    """Compare score statistics between baseline and variant."""

    name = "score_delta"

    def __init__(self, *, metric: str = "mean", criteria: list[str] | None = None) -> None:
        self._metric = metric
        self._criteria = set(criteria) if criteria else None

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        base_stats = self._extract_stats(baseline)
        var_stats = self._extract_stats(variant)
        if not base_stats or not var_stats:
            return {}

        diffs: dict[str, Any] = {}
        keys = set(base_stats.keys()) & set(var_stats.keys())
        for crit in sorted(keys):
            if self._criteria and crit not in self._criteria:
                continue
            base_metric = base_stats[crit].get(self._metric)
            var_metric = var_stats[crit].get(self._metric)
            if base_metric is None or var_metric is None:
                continue
            diffs[crit] = var_metric - base_metric
        return diffs

    @staticmethod
    def _extract_stats(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        aggregates = payload.get("aggregates") if isinstance(payload, Mapping) else None
        if not isinstance(aggregates, Mapping):
            return {}
        stats = aggregates.get("score_stats")
        if not isinstance(stats, Mapping):
            return {}
        criteria = stats.get("criteria")
        if not isinstance(criteria, Mapping):
            return {}
        return dict(criteria)


register_baseline_plugin(
    "score_delta",
    lambda options, context: ScoreDeltaBaselinePlugin(
        metric=options.get("metric", "mean"),
        criteria=options.get("criteria"),
    ),
    schema=_DELTA_SCHEMA,
)


__all__ = ["ScoreDeltaBaselinePlugin"]
