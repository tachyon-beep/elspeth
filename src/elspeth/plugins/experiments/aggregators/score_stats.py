"""ScoreStatsAggregator - Aggregation plugin."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Mapping

import numpy as np

from elspeth.core.experiments.plugin_registry import register_aggregation_plugin

if TYPE_CHECKING:
    from elspeth.core.schema import DataFrameSchema

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_STATS_SCHEMA = {
    "type": "object",
    "properties": {
        "source_field": {"type": "string"},
        "flag_field": {"type": "string"},
        "ddof": {"type": "integer", "minimum": 0},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class ScoreStatsAggregator:
    """Aggregate score statistics across all rows."""

    name = "score_stats"

    def __init__(
        self,
        *,
        source_field: str = "scores",
        flag_field: str = "score_flags",
        ddof: int = 0,
    ) -> None:
        self._source_field = source_field
        self._flag_field = flag_field
        self._ddof = ddof

    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        criteria_values: dict[str, dict[str, Any]] = {}

        for record in records:
            metrics = record.get("metrics") or {}
            scores = metrics.get(self._source_field)
            if isinstance(scores, Mapping):
                for crit, value in scores.items():
                    slot = criteria_values.setdefault(crit, {"values": [], "missing": 0, "passes": 0})
                    if value is None or (isinstance(value, float) and math.isnan(value)):
                        slot["missing"] += 1
                        continue
                    slot["values"].append(float(value))
            flags = metrics.get(self._flag_field)
            if isinstance(flags, Mapping):
                for crit, passed in flags.items():
                    slot = criteria_values.setdefault(crit, {"values": [], "missing": 0, "passes": 0})
                    if passed:
                        slot["passes"] += 1

        summaries: dict[str, Any] = {}
        all_values: list[float] = []
        total_missing = 0
        total_pass = 0

        for crit, payload in criteria_values.items():
            values = payload.get("values", [])
            missing = payload.get("missing", 0)
            passes = payload.get("passes", 0)
            total_missing += missing
            total_pass += passes
            all_values.extend(values)
            summary = self._summarize_values(values, missing, passes)
            summaries[crit] = summary

        overall = self._summarize_values(all_values, total_missing, total_pass)
        return {
            "criteria": summaries,
            "overall": overall,
        }

    def _summarize_values(self, values: list[float], missing: int, passes: int) -> dict[str, Any]:
        count = len(values)
        total = count + missing
        result: dict[str, Any] = {
            "count": count,
            "missing": missing,
        }
        if count:
            arr = np.array(values, dtype=float)
            result.update(
                {
                    "mean": float(np.mean(arr)),
                    "median": float(np.median(arr)),
                    "min": float(np.min(arr)),
                    "max": float(np.max(arr)),
                }
            )
            if count > 1:
                result["std"] = float(np.std(arr, ddof=self._ddof))
            else:
                result["std"] = 0.0
        if total:
            result["pass_rate"] = passes / total
            result["passes"] = passes
        return result

    def input_schema(self) -> type["DataFrameSchema"] | None:
        """ScoreStatsAggregator does not require specific input columns."""
        return None


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


register_aggregation_plugin(
    "score_stats",
    lambda options, context: ScoreStatsAggregator(
        source_field=options.get("source_field", "scores"),
        flag_field=options.get("flag_field", "score_flags"),
        ddof=int(options.get("ddof", 0)),
    ),
    schema=_STATS_SCHEMA,
)


__all__ = ["ScoreStatsAggregator"]
