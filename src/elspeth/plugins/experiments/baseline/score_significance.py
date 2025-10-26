"""ScoreSignificanceBaselinePlugin - Baseline comparison plugin."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Sequence

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.plugin_registry import register_baseline_plugin
from elspeth.plugins.experiments._stats_helpers import (
    _benjamini_hochberg,
    _collect_scores_by_criterion,
    _compute_significance,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_SIGNIFICANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 2},
        "equal_var": {"type": "boolean"},
        "on_error": _ON_ERROR_SCHEMA,
        "adjustment": {"type": "string", "enum": ["none", "bonferroni", "fdr"]},
        "family_size": {"type": "integer", "minimum": 1},
    },
    "additionalProperties": True,
}


class ScoreSignificanceBaselinePlugin(BasePlugin):
    """Compare baseline and variant using effect sizes and t-tests."""

    name = "score_significance"

    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        criteria: Sequence[str] | None = None,
        min_samples: int = 2,
        equal_var: bool = False,
        adjustment: str = "none",
        family_size: int | None = None,
        on_error: str = "abort",
    ) -> None:
        super().__init__(security_level=security_level, allow_downgrade=True)  # ADR-005: Baseline statistic plugins trusted to downgrade
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 2)
        self._equal_var = bool(equal_var)
        adjustment = (adjustment or "none").lower()
        if adjustment not in {"none", "bonferroni", "fdr"}:
            adjustment = "none"
        self._adjustment = adjustment
        self._family_size = int(family_size) if family_size else None
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive guard
            if self._on_error == "skip":
                logger.warning("score_significance skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        base_scores = _collect_scores_by_criterion(baseline)
        var_scores = _collect_scores_by_criterion(variant)
        criteria = sorted(set(base_scores.keys()) & set(var_scores.keys()))
        if self._criteria is not None:
            criteria = [name for name in criteria if name in self._criteria]
        p_values: dict[str, float | None] = {}
        for name in criteria:
            base = base_scores.get(name, [])
            var = var_scores.get(name, [])
            if len(base) < self._min_samples or len(var) < self._min_samples:
                continue
            stats = _compute_significance(base, var, equal_var=self._equal_var)
            if stats:
                results[name] = stats
                p_value = stats.get("p_value")
                if isinstance(p_value, (float, int)) and math.isfinite(p_value):
                    p_values[name] = float(p_value)
                else:
                    p_values[name] = None

        if self._adjustment != "none" and p_values:
            family_size = self._family_size or len([name for name, value in p_values.items() if value is not None])
            family_size = max(int(family_size or len(p_values)), 1)
            if self._adjustment == "bonferroni":
                for name, p_value in p_values.items():
                    if p_value is None:
                        adjusted = None
                    else:
                        adjusted = min(p_value * family_size, 1.0)
                    result = results.get(name)
                    if result is not None:
                        result["adjusted_p_value"] = adjusted
                        result["adjustment"] = "bonferroni"
            elif self._adjustment == "fdr":
                try:
                    from statsmodels.stats.multitest import fdrcorrection  # pytype: disable=import-error

                    valid = [(name, p) for name, p in p_values.items() if p is not None]
                    p_vals = [p for _, p in valid]
                    _, adj = fdrcorrection(p_vals, alpha=0.05)
                except Exception:
                    valid = [(name, p) for name, p in p_values.items() if p is not None]
                    p_vals = [p for _, p in valid]
                    adj = _benjamini_hochberg(p_vals)
                for (name, _), adjusted in zip(valid, adj):
                    result = results.get(name)
                    if result is not None:
                        result["adjusted_p_value"] = float(adjusted)
                        result["adjustment"] = "fdr"
                missing = set(p_values.keys()) - {name for name, _ in (valid if "valid" in locals() else [])}
                for name in missing:
                    result = results.get(name)
                    if result is not None:
                        result["adjusted_p_value"] = None
                        result["adjustment"] = "fdr"
        return results


def _create_score_significance(options: dict[str, Any], context: PluginContext) -> ScoreSignificanceBaselinePlugin:
    """Create score significance baseline plugin with smart security defaults."""
    opts = dict(options)
    if "security_level" not in opts and context:
        opts["security_level"] = context.security_level
    return ScoreSignificanceBaselinePlugin(
        security_level=opts["security_level"],
        criteria=opts.get("criteria"),
        min_samples=int(opts.get("min_samples", 2)),
        equal_var=bool(opts.get("equal_var", False)),
        adjustment=opts.get("adjustment", "none"),
        family_size=opts.get("family_size"),
        on_error=opts.get("on_error", "abort"),
    )


register_baseline_plugin(
    "score_significance",
    _create_score_significance,
    schema=_SIGNIFICANCE_SCHEMA,
)


__all__ = ["ScoreSignificanceBaselinePlugin"]
