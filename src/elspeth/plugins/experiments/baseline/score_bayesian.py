"""ScoreBayesianBaselinePlugin - Baseline comparison plugin."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Sequence

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.plugin_registry import register_baseline_plugin
from elspeth.plugins.experiments._stats_helpers import (
    _collect_scores_by_criterion,
    _compute_bayesian_summary,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_BAYESIAN_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 2},
        "credible_interval": {"type": "number", "minimum": 0.5, "maximum": 0.999},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class ScoreBayesianBaselinePlugin(BasePlugin):
    """Estimate posterior probability that a variant beats the baseline."""

    name = "score_bayes"

    def __init__(
        self,
        *,
        criteria: Sequence[str] | None = None,
        min_samples: int = 2,
        credible_interval: float = 0.95,
        on_error: str = "abort",
    ) -> None:
        super().__init__(
            security_level=SecurityLevel.UNOFFICIAL,  # ADR-002-B: Immutable policy
            allow_downgrade=True  # ADR-002-B: Immutable policy
        )
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 2)
        self._ci = min(max(float(credible_interval), 0.5), 0.999)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive guard
            if self._on_error == "skip":
                logger.warning("score_bayes skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        base_scores = _collect_scores_by_criterion(baseline)
        var_scores = _collect_scores_by_criterion(variant)
        criteria = sorted(set(base_scores.keys()) & set(var_scores.keys()))
        if self._criteria is not None:
            criteria = [name for name in criteria if name in self._criteria]
        alpha = 1 - self._ci
        for name in criteria:
            base = base_scores.get(name, [])
            var = var_scores.get(name, [])
            if len(base) < self._min_samples or len(var) < self._min_samples:
                continue
            summary = _compute_bayesian_summary(base, var, alpha)
            if summary:
                results[name] = summary
        return results


def _create_score_bayesian(options: dict[str, Any], context: PluginContext) -> ScoreBayesianBaselinePlugin:
    """Create score_bayesian baseline plugin with smart security defaults."""
    return ScoreBayesianBaselinePlugin(
        criteria=options.get("criteria"),
        min_samples=int(options.get("min_samples", 2)),
        credible_interval=float(options.get("credible_interval", 0.95)),
        on_error=options.get("on_error", "abort"),
    )


register_baseline_plugin(
    "score_bayes",
    _create_score_bayesian,
    schema=_BAYESIAN_SCHEMA,
    declared_security_level="UNOFFICIAL",  # ADR-002-B: Baseline analyzers work with experiment results
)


__all__ = ["ScoreBayesianBaselinePlugin"]
