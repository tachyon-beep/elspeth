"""CostSummaryAggregator - Aggregation plugin."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

import numpy as np

from elspeth.core.experiments.plugin_registry import register_aggregation_plugin

if TYPE_CHECKING:
    from elspeth.core.schema import DataFrameSchema

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_COST_SCHEMA = {
    "type": "object",
    "properties": {
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class CostSummaryAggregator:
    """Aggregate cost and token usage metrics across all rows.

    Collects prompt_tokens, completion_tokens, and cost from response metrics
    (added by cost tracker) and computes totals, averages, min, and max.
    """

    name = "cost_summary"

    def __init__(self, *, on_error: str = "abort") -> None:
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return self._finalize_impl(records)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("cost_summary skipped due to error: %s", exc)
                return {}
            raise

    def _finalize_impl(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {}

        prompt_tokens_list: list[int] = []
        completion_tokens_list: list[int] = []
        cost_list: list[float] = []

        for record in records:
            metrics = record.get("metrics") or {}
            prompt_tokens = metrics.get("prompt_tokens")
            completion_tokens = metrics.get("completion_tokens")
            cost = metrics.get("cost")

            if prompt_tokens is not None:
                try:
                    prompt_tokens_list.append(int(prompt_tokens))
                except (TypeError, ValueError):
                    pass

            if completion_tokens is not None:
                try:
                    completion_tokens_list.append(int(completion_tokens))
                except (TypeError, ValueError):
                    pass

            if cost is not None:
                try:
                    cost_list.append(float(cost))
                except (TypeError, ValueError):
                    pass

        result: dict[str, Any] = {
            "total_requests": len(records),
            "requests_with_cost": len(cost_list),
        }

        if prompt_tokens_list:
            result["prompt_tokens"] = {
                "total": sum(prompt_tokens_list),
                "mean": float(np.mean(prompt_tokens_list)),
                "median": float(np.median(prompt_tokens_list)),
                "min": min(prompt_tokens_list),
                "max": max(prompt_tokens_list),
            }

        if completion_tokens_list:
            result["completion_tokens"] = {
                "total": sum(completion_tokens_list),
                "mean": float(np.mean(completion_tokens_list)),
                "median": float(np.median(completion_tokens_list)),
                "min": min(completion_tokens_list),
                "max": max(completion_tokens_list),
            }

        if cost_list:
            result["cost"] = {
                "total": sum(cost_list),
                "mean": float(np.mean(cost_list)),
                "median": float(np.median(cost_list)),
                "min": min(cost_list),
                "max": max(cost_list),
            }

        return result

    def input_schema(self) -> type["DataFrameSchema"] | None:
        """CostSummaryAggregator does not require specific input columns."""
        return None


class LatencySummaryAggregator:
    """Aggregate latency metrics across all rows.

    Collects latency_seconds from response metrics and computes
    totals, averages, percentiles, min, and max.
    """

    name = "latency_summary"

    def __init__(self, *, on_error: str = "abort") -> None:
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


register_aggregation_plugin(
    "cost_summary",
    lambda options, context: CostSummaryAggregator(
        on_error=options.get("on_error", "abort"),
    ),
    schema=_COST_SCHEMA,
)


__all__ = ["CostSummaryAggregator"]
