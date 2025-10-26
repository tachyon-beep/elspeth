"""CategoryEffectsAggregator - Baseline comparison plugin."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

import numpy as np

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

_CATEGORY_SCHEMA = {
    "type": "object",
    "properties": {
        "category_field": {"type": "string"},
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 1},
        "top_n": {"type": "integer", "minimum": 1},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class CategoryEffectsAggregator(BasePlugin):
    """Analyze how categorical variables affect score distributions.

    Discovers categories dynamically from row data, computes per-category statistics,
    effect sizes, and ranks categories by impact magnitude. Useful for understanding
    which subpopulations are most affected by variant changes.

    Example use case: Understanding performance across document types, user segments,
    or difficulty levels.
    """

    name = "category_effects"

    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        allow_downgrade: bool,
        category_field: str = "category",
        criteria: list[str] | None = None,
        min_samples: int = 2,
        top_n: int = 10,
        on_error: str = "abort",
    ) -> None:
        super().__init__(security_level=security_level, allow_downgrade=allow_downgrade)
        self._category_field = category_field
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 1)
        self._top_n = max(int(top_n), 1)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("category_effects skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        # Discover categories from baseline data
        categories = self._discover_categories(baseline)

        if not categories:
            return {}

        # Analyze each category
        category_impacts: dict[str, dict[str, Any]] = {}

        for category in categories:
            baseline_cat = self._filter_by_category(baseline, category)
            variant_cat = self._filter_by_category(variant, category)

            if not baseline_cat or not variant_cat:
                continue

            # Extract scores
            baseline_scores = _collect_scores_by_criterion({"results": baseline_cat})
            variant_scores = _collect_scores_by_criterion({"results": variant_cat})

            # Compute overall mean for this category
            all_baseline = []
            all_variant = []
            for crit_name in baseline_scores:
                if self._criteria and crit_name not in self._criteria:
                    continue
                all_baseline.extend(baseline_scores.get(crit_name, []))
                all_variant.extend(variant_scores.get(crit_name, []))

            if len(all_baseline) < self._min_samples or len(all_variant) < self._min_samples:
                continue

            baseline_mean = float(np.mean(all_baseline))
            variant_mean = float(np.mean(all_variant))
            delta = variant_mean - baseline_mean

            # Compute Cohen's d effect size
            effect_size = self._compute_cohens_d(all_baseline, all_variant)

            category_impacts[category] = {
                "baseline_mean": round(baseline_mean, 2),
                "variant_mean": round(variant_mean, 2),
                "delta": round(delta, 2),
                "effect_size": round(effect_size, 3) if effect_size is not None else None,
                "baseline_samples": len(all_baseline),
                "variant_samples": len(all_variant),
            }

        if not category_impacts:
            return {}

        # Rank by absolute effect size
        ranked = sorted(
            category_impacts.items(),
            key=lambda x: abs(x[1]["effect_size"]) if x[1]["effect_size"] is not None else 0,
            reverse=True,
        )

        return {
            "category_impacts": category_impacts,
            "most_affected": [{"category": k, **v} for k, v in ranked[: self._top_n]],
            "least_affected": [{"category": k, **v} for k, v in ranked[-self._top_n :]],
            "total_categories": len(category_impacts),
        }

    def _discover_categories(self, payload: dict[str, Any]) -> set[str]:
        """Discover unique category values from baseline data."""
        categories: set[str] = set()
        for result in payload.get("results", []) or []:
            row = result.get("row") or {}
            category = row.get(self._category_field)
            if category is not None and isinstance(category, (str, int, float)):
                categories.add(str(category))
        return categories

    def _filter_by_category(self, payload: dict[str, Any], category: str) -> list[dict[str, Any]]:
        """Filter results by category value."""
        filtered = []
        for result in payload.get("results", []) or []:
            row = result.get("row") or {}
            cat_value = row.get(self._category_field)
            if cat_value is not None and str(cat_value) == category:
                filtered.append(result)
        return filtered

    def _compute_cohens_d(self, baseline: list[float], variant: list[float]) -> float | None:
        """Compute Cohen's d effect size."""
        if not baseline or not variant:
            return None

        arr_base = np.array(baseline, dtype=float)
        arr_var = np.array(variant, dtype=float)

        n_base = arr_base.size
        n_var = arr_var.size

        if n_base < 2 or n_var < 2:
            return None

        mean_base = arr_base.mean()
        mean_var = arr_var.mean()
        var_base = arr_base.var(ddof=1)
        var_var = arr_var.var(ddof=1)

        pooled_var = ((n_base - 1) * var_base + (n_var - 1) * var_var) / (n_base + n_var - 2)

        # Guard against near-zero variance (numerical stability)
        if pooled_var <= 1e-10:
            return None

        return float((mean_var - mean_base) / math.sqrt(pooled_var))


def _create_category_effects(options: dict[str, Any], context: PluginContext) -> CategoryEffectsAggregator:
    """Create category effects baseline plugin with smart security defaults."""
    opts = dict(options)
    if "security_level" not in opts and context:
        opts["security_level"] = context.security_level
    allow_downgrade = opts.get("allow_downgrade", True)

    return CategoryEffectsAggregator(
        security_level=opts["security_level"],
        allow_downgrade=allow_downgrade,
        category_field=opts.get("category_field", "category"),
        criteria=opts.get("criteria"),
        min_samples=int(opts.get("min_samples", 2)),
        top_n=int(opts.get("top_n", 10)),
        on_error=opts.get("on_error", "abort"),
    )


register_baseline_plugin(
    "category_effects",
    _create_category_effects,
    schema=_CATEGORY_SCHEMA,
)


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


__all__ = ["CategoryEffectsAggregator"]
