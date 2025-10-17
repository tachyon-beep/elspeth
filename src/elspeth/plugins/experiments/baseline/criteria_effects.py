"""CriteriaEffectsBaselinePlugin - Baseline comparison plugin."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy import stats as scipy_stats

from elspeth.core.experiments.plugin_registry import register_baseline_plugin
from elspeth.plugins.experiments._stats_helpers import (
    _collect_scores_by_criterion,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_CRITERIA_EFFECTS_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 2},
        "alpha": {"type": "number", "minimum": 0.001, "maximum": 0.5},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class CriteriaEffectsBaselinePlugin:
    """Perform per-criterion statistical comparisons between baseline and variant.

    Computes detailed statistics for each scoring criterion individually, including
    means, effect sizes, Mann-Whitney U tests, and significance flags. Provides
    finer-grained analysis than overall score comparisons.

    Useful for: understanding which criteria are most affected by changes,
    identifying criterion-specific regressions or improvements.
    """

    name = "criteria_effects"

    def __init__(
        self,
        *,
        criteria: list[str] | None = None,
        min_samples: int = 2,
        alpha: float = 0.05,
        on_error: str = "abort",
    ) -> None:
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 2)
        self._alpha = float(alpha)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("criteria_effects skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        base_scores = _collect_scores_by_criterion(baseline)
        var_scores = _collect_scores_by_criterion(variant)

        criteria = sorted(set(base_scores.keys()) & set(var_scores.keys()))

        if self._criteria is not None:
            criteria = [name for name in criteria if name in self._criteria]

        if not criteria:
            return {}

        results: dict[str, Any] = {}

        for crit_name in criteria:
            base = base_scores.get(crit_name, [])
            var = var_scores.get(crit_name, [])

            if len(base) < self._min_samples or len(var) < self._min_samples:
                continue

            base_arr = np.array(base, dtype=float)
            var_arr = np.array(var, dtype=float)

            baseline_mean = float(base_arr.mean())
            variant_mean = float(var_arr.mean())
            delta = variant_mean - baseline_mean

            # Cohen's d effect size
            n_base = base_arr.size
            n_var = var_arr.size
            var_base = base_arr.var(ddof=1) if n_base > 1 else 0.0
            var_var = var_arr.var(ddof=1) if n_var > 1 else 0.0
            pooled_var = ((n_base - 1) * var_base + (n_var - 1) * var_var) / (n_base + n_var - 2)
            effect_size = delta / math.sqrt(pooled_var) if pooled_var > 0 else None

            # Mann-Whitney U test (non-parametric)
            p_value = None
            if scipy_stats is not None:
                try:
                    mw_result = scipy_stats.mannwhitneyu(base, var, alternative="two-sided")
                    p_value = float(mw_result.pvalue)
                except Exception:  # pragma: no cover
                    p_value = None

            results[crit_name] = {
                "baseline_mean": round(baseline_mean, 2),
                "variant_mean": round(variant_mean, 2),
                "delta": round(delta, 2),
                "effect_size": round(effect_size, 3) if effect_size is not None else None,
                "p_value": round(p_value, 4) if p_value is not None else None,
                "significant": bool(p_value < self._alpha) if p_value is not None else None,
                "n_baseline": n_base,
                "n_variant": n_var,
            }

        return results


register_baseline_plugin(
    "criteria_effects",
    lambda options, context: CriteriaEffectsBaselinePlugin(
        criteria=options.get("criteria"),
        min_samples=int(options.get("min_samples", 2)),
        alpha=float(options.get("alpha", 0.05)),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_CRITERIA_EFFECTS_SCHEMA,
)


__all__ = ["CriteriaEffectsBaselinePlugin"]
