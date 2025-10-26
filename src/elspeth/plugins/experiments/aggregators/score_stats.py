"""ScoreStatsAggregator - Aggregation plugin."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Mapping

import numpy as np

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.plugin_registry import register_aggregation_plugin

if TYPE_CHECKING:
    from elspeth.core.base.schema import DataFrameSchema

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


class ScoreStatsAggregator(BasePlugin):
    """Aggregate score statistics across all rows."""

    name = "score_stats"

    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        allow_downgrade: bool,
        source_field: str = "scores",
        flag_field: str = "score_flags",
        ddof: int = 0,
    ) -> None:
        super().__init__(security_level=security_level, allow_downgrade=allow_downgrade)
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
def _create_score_stats(options: dict[str, Any], context: PluginContext) -> ScoreStatsAggregator:
    """Create score stats aggregator with smart security defaults."""
    opts = dict(options)
    if "security_level" not in opts and context:
        opts["security_level"] = context.security_level
    allow_downgrade = opts.get("allow_downgrade", True)

    return ScoreStatsAggregator(
        security_level=opts["security_level"],
        allow_downgrade=allow_downgrade,
        source_field=opts.get("source_field", "scores"),
        flag_field=opts.get("flag_field", "score_flags"),
        ddof=int(opts.get("ddof", 0)),
    )


register_aggregation_plugin(
    "score_stats",
    _create_score_stats,
    schema=_STATS_SCHEMA,
)


__all__ = ["ScoreStatsAggregator"]
