"""CostSummaryAggregator - Aggregation plugin."""

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

_COST_SCHEMA = {
    "type": "object",
    "properties": {
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class CostSummaryAggregator(BasePlugin):
    """Aggregate cost and token usage metrics across all rows.

    Collects prompt_tokens, completion_tokens, and cost from response metrics
    (added by cost tracker) and computes totals, averages, min, and max.
    """

    name = "cost_summary"

    def __init__(
        self,
        *,
        on_error: str = "abort",
    ) -> None:
        # ADR-002-B: Security policy is immutable and hard-coded in plugin code
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # Aggregators work with experiment results
            allow_downgrade=True,  # Trusted to operate at lower levels if needed (ADR-005)
        )
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


def _create_cost_summary(options: dict[str, Any], context: PluginContext) -> CostSummaryAggregator:
    """Create cost summary aggregator.

    ADR-002-B: Security policy is hard-coded in plugin __init__, not injected by factory.
    """
    return CostSummaryAggregator(
        on_error=options.get("on_error", "abort"),
    )


register_aggregation_plugin(
    "cost_summary",
    _create_cost_summary,
    schema=_COST_SCHEMA,
    declared_security_level="UNOFFICIAL",  # ADR-002-B: Aggregators work with experiment results
)


__all__ = ["CostSummaryAggregator"]
