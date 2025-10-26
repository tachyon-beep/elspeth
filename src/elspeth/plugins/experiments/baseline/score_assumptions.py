"""ScoreAssumptionsBaselinePlugin - Baseline comparison plugin."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Sequence

from scipy import stats as scipy_stats

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.plugin_registry import register_baseline_plugin
from elspeth.plugins.experiments._stats_helpers import (
    _collect_scores_by_criterion,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_ASSUMPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 3},
        "alpha": {"type": "number", "minimum": 0.001, "maximum": 0.2},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class ScoreAssumptionsBaselinePlugin(BasePlugin):
    """Report normality and variance diagnostics for baseline vs. variant scores."""

    name = "score_assumptions"

    def __init__(
        self,
        *,
        security_level: SecurityLevel,        criteria: Sequence[str] | None = None,
        min_samples: int = 3,
        alpha: float = 0.05,
        on_error: str = "abort",
    ) -> None:
        super().__init__(security_level=security_level, allow_downgrade=True)  # ADR-005: Baseline plugins trusted to downgrade
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 3)
        self._alpha = float(alpha)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover
            if self._on_error == "skip":
                logger.warning("score_assumptions skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        if scipy_stats is None:
            return {}
        base_scores = _collect_scores_by_criterion(baseline)
        var_scores = _collect_scores_by_criterion(variant)
        criteria = sorted(set(base_scores.keys()) & set(var_scores.keys()))
        if self._criteria is not None:
            criteria = [name for name in criteria if name in self._criteria]

        results: dict[str, Any] = {}
        for name in criteria:
            base = base_scores.get(name, [])
            var = var_scores.get(name, [])
            entry: dict[str, Any] = {}
            if len(base) >= self._min_samples:
                try:
                    stat, pval = scipy_stats.shapiro(base)
                    entry["baseline"] = {
                        "statistic": float(stat),
                        "p_value": float(pval),
                        "is_normal": bool(pval > self._alpha),
                        "samples": len(base),
                    }
                except Exception:
                    entry["baseline"] = None
            else:
                entry["baseline"] = None
            if len(var) >= self._min_samples:
                try:
                    stat, pval = scipy_stats.shapiro(var)
                    entry["variant"] = {
                        "statistic": float(stat),
                        "p_value": float(pval),
                        "is_normal": bool(pval > self._alpha),
                        "samples": len(var),
                    }
                except Exception:
                    entry["variant"] = None
            else:
                entry["variant"] = None
            if len(base) >= 2 and len(var) >= 2:
                try:
                    stat, pval = scipy_stats.levene(base, var)
                    entry["variance"] = {
                        "statistic": float(stat),
                        "p_value": float(pval),
                        "equal_variance": bool(pval > self._alpha),
                    }
                except Exception:
                    entry["variance"] = None
            else:
                entry["variance"] = None
            if any(entry.values()):
                results[name] = entry
        return results


def _create_score_assumptions(options: dict[str, Any], context: PluginContext) -> ScoreAssumptionsBaselinePlugin:
    """Create score_assumptions baseline plugin with smart security defaults."""
    opts = dict(options)
    if "security_level" not in opts and context:
        opts["security_level"] = context.security_level
    return ScoreAssumptionsBaselinePlugin(
        security_level=opts["security_level"],
        criteria=options.get("criteria"),
        min_samples=int(options.get("min_samples", 3)),
        alpha=float(options.get("alpha", 0.05)),
        on_error=options.get("on_error", "abort"),
    )


register_baseline_plugin(
    "score_assumptions",
    _create_score_assumptions,
    schema=_ASSUMPTION_SCHEMA,
)


__all__ = ["ScoreAssumptionsBaselinePlugin"]
