"""ScorePowerAggregator - Aggregation plugin."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np
from statsmodels.stats.power import TTestPower

from elspeth.core.experiments.plugin_registry import register_aggregation_plugin
from elspeth.plugins.experiments._stats_helpers import (
    _collect_scores_by_criterion,
)

if TYPE_CHECKING:
    from elspeth.core.base.schema import DataFrameSchema

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_POWER_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 2},
        "alpha": {"type": "number", "minimum": 0.0, "maximum": 0.5},
        "target_power": {"type": "number", "minimum": 0.1, "maximum": 0.999},
        "effect_size": {"type": "number", "minimum": 0.0},
        "null_mean": {"type": "number"},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class ScorePowerAggregator:
    """Estimate power and required sample size for mean comparisons."""

    name = "score_power"

    def __init__(
        self,
        *,
        criteria: Sequence[str] | None = None,
        min_samples: int = 2,
        alpha: float = 0.05,
        target_power: float = 0.8,
        effect_size: float | None = None,
        null_mean: float = 0.0,
        on_error: str = "abort",
    ) -> None:
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 2)
        self._alpha = min(max(float(alpha), 1e-6), 0.25)
        self._target_power = min(max(float(target_power), 0.1), 0.999)
        self._effect_size = effect_size
        self._null_mean = float(null_mean)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def finalize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            return self._finalize_impl(records)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("score_power skipped due to error: %s", exc)
                return {}
            raise

    def _finalize_impl(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {}
        scores_by_name = _collect_scores_by_criterion({"results": records})
        criteria = sorted(scores_by_name.keys())
        if self._criteria is not None:
            criteria = [name for name in criteria if name in self._criteria]

        power_results: dict[str, Any] = {}
        for name in criteria:
            values = scores_by_name.get(name, [])
            if len(values) < self._min_samples:
                continue
            arr = np.asarray(values, dtype=float)
            mean = float(arr.mean())
            std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
            n = arr.size
            observed_effect = None
            if std > 0:
                observed_effect = (mean - self._null_mean) / std
            effect = self._effect_size or observed_effect

            required_n = None
            achieved_power = None
            if effect and effect > 0 and TTestPower is not None:
                try:
                    test = TTestPower()
                    required_n = test.solve_power(
                        effect_size=effect,
                        alpha=self._alpha,
                        power=self._target_power,
                        alternative="two-sided",
                    )
                    if observed_effect:
                        achieved_power = test.solve_power(
                            effect_size=observed_effect,
                            alpha=self._alpha,
                            nobs=n,
                            alternative="two-sided",
                        )
                except Exception:  # pragma: no cover
                    required_n = None
                    achieved_power = None

            power_results[name] = {
                "samples": n,
                "mean": mean,
                "std": std,
                "observed_effect_size": observed_effect,
                "target_effect_size": effect,
                "required_samples": float(required_n) if required_n is not None else None,
                "achieved_power": float(achieved_power) if achieved_power is not None else None,
                "alpha": self._alpha,
                "target_power": self._target_power,
            }

        return power_results

    def input_schema(self) -> type["DataFrameSchema"] | None:
        """ScorePowerAggregator does not require specific input columns."""
        return None


register_aggregation_plugin(
    "score_power",
    lambda options, context: ScorePowerAggregator(
        criteria=options.get("criteria"),
        min_samples=int(options.get("min_samples", 2)),
        alpha=float(options.get("alpha", 0.05)),
        target_power=float(options.get("target_power", 0.8)),
        effect_size=options.get("effect_size"),
        null_mean=float(options.get("null_mean", 0.0)),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_POWER_SCHEMA,
)


__all__ = ["ScorePowerAggregator"]
