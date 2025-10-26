"""ScoreDistributionAggregator - Aggregation plugin."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Sequence

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.plugin_registry import register_baseline_plugin
from elspeth.plugins.experiments._stats_helpers import (
    _collect_scores_by_criterion,
    _compute_distribution_shift,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_DISTRIBUTION_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 2},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class ScoreDistributionAggregator(BasePlugin):
    """Assess distribution shifts between baseline and variant deployments."""

    name = "score_distribution"

    def __init__(
        self,
        *,
        security_level: SecurityLevel,        criteria: Sequence[str] | None = None,
        min_samples: int = 2,
        on_error: str = "abort",
    ) -> None:
        super().__init__(security_level=security_level, allow_downgrade=True)  # ADR-005: Baseline plugins trusted to downgrade
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 2)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        # This aggregator expects to inspect baseline + variant payloads, so per-run finalize is empty.
        return {}

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive guard
            if self._on_error == "skip":
                logger.warning("score_distribution skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        base_scores = _collect_scores_by_criterion(baseline)
        var_scores = _collect_scores_by_criterion(variant)
        criteria = sorted(set(base_scores.keys()) & set(var_scores.keys()))
        if self._criteria is not None:
            criteria = [name for name in criteria if name in self._criteria]
        results: dict[str, Any] = {}
        for name in criteria:
            base = base_scores.get(name, [])
            var = var_scores.get(name, [])
            if len(base) < self._min_samples or len(var) < self._min_samples:
                continue
            stats = _compute_distribution_shift(base, var)
            if stats:
                results[name] = stats
        return results


def _create_score_distribution(options: dict[str, Any], context: PluginContext) -> ScoreDistributionAggregator:
    """Create score distribution baseline plugin with smart security defaults."""
    opts = dict(options)
    if "security_level" not in opts and context:
        opts["security_level"] = context.security_level
    return ScoreDistributionAggregator(
        security_level=opts["security_level"],
        criteria=opts.get("criteria"),
        min_samples=int(opts.get("min_samples", 2)),
        on_error=opts.get("on_error", "abort"),
    )


register_baseline_plugin(
    "score_distribution",
    _create_score_distribution,
    schema=_DISTRIBUTION_SCHEMA,
)


__all__ = ["ScoreDistributionAggregator"]
