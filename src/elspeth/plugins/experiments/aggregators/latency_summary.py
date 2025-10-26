"""LatencySummaryAggregator - Aggregation plugin."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

import numpy as np

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.plugin_registry import register_aggregation_plugin

if TYPE_CHECKING:
    from elspeth.core.base.schema import DataFrameSchema

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_LATENCY_SCHEMA = {
    "type": "object",
    "properties": {
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class LatencySummaryAggregator(BasePlugin):
    """Aggregate latency metrics across all rows.

    Collects latency_seconds from response metrics and computes
    totals, averages, percentiles, min, and max.
    """

    name = "latency_summary"

    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        allow_downgrade: bool,
        on_error: str = "abort",
    ) -> None:
        super().__init__(security_level=security_level, allow_downgrade=allow_downgrade)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return self._finalize_impl(records)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("latency_summary skipped due to error: %s", exc)
                return {}
            raise

    def _finalize_impl(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {}

        latency_list: list[float] = []

        for record in records:
            metrics = record.get("metrics") or {}
            latency = metrics.get("latency_seconds")

            if latency is not None:
                try:
                    lat_val = float(latency)
                    if not math.isnan(lat_val) and lat_val >= 0:
                        latency_list.append(lat_val)
                except (TypeError, ValueError):
                    pass

        if not latency_list:
            return {
                "total_requests": len(records),
                "requests_with_latency": 0,
            }

        arr = np.array(latency_list, dtype=float)

        return {
            "total_requests": len(records),
            "requests_with_latency": len(latency_list),
            "latency_seconds": {
                "mean": float(np.mean(arr)),
                "median": float(np.median(arr)),
                "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
                "p50": float(np.percentile(arr, 50)),
                "p95": float(np.percentile(arr, 95)),
                "p99": float(np.percentile(arr, 99)),
            },
        }

    def input_schema(self) -> type["DataFrameSchema"] | None:
        """LatencySummaryAggregator does not require specific input columns."""
        return None


def _create_latency_summary(options: dict[str, Any], context: PluginContext) -> LatencySummaryAggregator:
    """Create latency summary aggregator with smart security defaults."""
    opts = dict(options)
    if "security_level" not in opts and context:
        opts["security_level"] = context.security_level
    allow_downgrade = opts.get("allow_downgrade", True)

    return LatencySummaryAggregator(
        security_level=opts["security_level"],
        allow_downgrade=allow_downgrade,
        on_error=opts.get("on_error", "abort"),
    )


register_aggregation_plugin(
    "latency_summary",
    _create_latency_summary,
    schema=_LATENCY_SCHEMA,
)


__all__ = ["LatencySummaryAggregator"]
