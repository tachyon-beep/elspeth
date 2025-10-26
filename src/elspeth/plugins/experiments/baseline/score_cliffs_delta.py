"""ScoreCliffsDeltaPlugin - Baseline comparison plugin."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Sequence

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.plugin_registry import register_baseline_plugin
from elspeth.plugins.experiments._stats_helpers import (
    _calculate_cliffs_delta,
    _collect_scores_by_criterion,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_CLIFFS_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 1},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class ScoreCliffsDeltaPlugin(BasePlugin):
    """Compute Cliff's delta effect size between baseline and variant."""

    name = "score_cliffs_delta"

    def __init__(
        self,
        *,
        security_level: SecurityLevel,
        allow_downgrade: bool,
        criteria: Sequence[str] | None = None,
        min_samples: int = 1,
        on_error: str = "abort",
    ) -> None:
        super().__init__(security_level=security_level, allow_downgrade=allow_downgrade)
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 1)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive guard
            if self._on_error == "skip":
                logger.warning("score_cliffs_delta skipped due to error: %s", exc)
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
            group1 = base_scores.get(name, [])
            group2 = var_scores.get(name, [])
            if len(group1) < self._min_samples or len(group2) < self._min_samples:
                continue
            delta, interpretation = _calculate_cliffs_delta(group1, group2)
            results[name] = {
                "delta": delta,
                "interpretation": interpretation,
                "baseline_samples": len(group1),
                "variant_samples": len(group2),
            }
        return results


def _create_score_cliffs_delta(options: dict[str, Any], context: PluginContext) -> ScoreCliffsDeltaPlugin:
    """Create Cliff's delta baseline plugin with smart security defaults."""
    opts = dict(options)
    if "security_level" not in opts and context:
        opts["security_level"] = context.security_level
    allow_downgrade = opts.get("allow_downgrade", True)

    return ScoreCliffsDeltaPlugin(
        security_level=opts["security_level"],
        allow_downgrade=allow_downgrade,
        criteria=opts.get("criteria"),
        min_samples=int(opts.get("min_samples", 1)),
        on_error=opts.get("on_error", "abort"),
    )


register_baseline_plugin(
    "score_cliffs_delta",
    _create_score_cliffs_delta,
    schema=_CLIFFS_SCHEMA,
)


__all__ = ["ScoreCliffsDeltaPlugin"]
