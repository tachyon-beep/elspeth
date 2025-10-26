"""RefereeAlignmentBaselinePlugin - Baseline comparison plugin."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, Mapping

import numpy as np

from elspeth.core.base.plugin import BasePlugin
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.plugin_registry import register_baseline_plugin

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_REFEREE_SCHEMA = {
    "type": "object",
    "properties": {
        "referee_fields": {"type": "array", "items": {"type": "string"}},
        "score_field": {"type": "string"},
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 2},
        "value_mapping": {"type": "object"},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class RefereeAlignmentBaselinePlugin(BasePlugin):
    """Compare LLM scores against human referee/expert judgments.

    This plugin measures how well LLM scores align with human expert assessments
    (referees). It computes alignment metrics (mean absolute error, correlation)
    between baseline and variant to determine if the variant improves agreement
    with human judgment.

    Useful for validating that model changes maintain or improve alignment with
    human expert consensus.
    """

    name = "referee_alignment"

    def __init__(
        self,
        *,
        security_level: SecurityLevel,        referee_fields: list[str] | None = None,
        score_field: str = "scores",
        criteria: list[str] | None = None,
        min_samples: int = 2,
        value_mapping: dict[str, float] | None = None,
        on_error: str = "abort",
    ) -> None:
        super().__init__(security_level=security_level, allow_downgrade=True)  # ADR-005: Baseline plugins trusted to downgrade
        self._referee_fields = referee_fields or ["referee_score"]
        self._score_field = score_field
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 2)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

        # Default value mapping for common string values
        default_mapping = {
            "yes": 5.0,
            "no": 1.0,
            "partially": 3.0,
            "partial": 3.0,
            "n/a": None,
            "na": None,
        }
        self._value_mapping = {**default_mapping, **(value_mapping or {})}

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("referee_alignment skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        # Extract scores and referee judgments for both experiments
        baseline_pairs = self._extract_score_pairs(baseline)
        variant_pairs = self._extract_score_pairs(variant)

        if not baseline_pairs and not variant_pairs:
            return {}

        # Compute alignment metrics
        results: dict[str, Any] = {}

        # Overall alignment
        baseline_alignment = self._compute_alignment_metrics(baseline_pairs)
        variant_alignment = self._compute_alignment_metrics(variant_pairs)

        if baseline_alignment:
            results["baseline"] = baseline_alignment

        if variant_alignment:
            results["variant"] = variant_alignment

        # Comparison
        if baseline_alignment and variant_alignment:
            # Lower MAE is better alignment
            mae_improved = variant_alignment["mean_absolute_error"] < baseline_alignment["mean_absolute_error"]
            # Higher correlation is better alignment
            corr_improved = False
            if baseline_alignment["correlation"] is not None and variant_alignment["correlation"] is not None:
                corr_improved = variant_alignment["correlation"] > baseline_alignment["correlation"]

            results["comparison"] = {
                "mae_improved": mae_improved,
                "mae_difference": variant_alignment["mean_absolute_error"] - baseline_alignment["mean_absolute_error"],
                "correlation_improved": corr_improved,
                "correlation_difference": (
                    variant_alignment["correlation"] - baseline_alignment["correlation"]
                    if variant_alignment["correlation"] is not None and baseline_alignment["correlation"] is not None
                    else None
                ),
            }

        # Per-criterion breakdown
        if self._criteria:
            criteria_results = {}
            for crit_name in self._criteria:
                baseline_crit = [(llm.get(crit_name), ref) for llm, ref in baseline_pairs if crit_name in llm]
                variant_crit = [(llm.get(crit_name), ref) for llm, ref in variant_pairs if crit_name in llm]

                # Filter out None scores
                baseline_crit = [
                    (score_value, referee_score)
                    for score_value, referee_score in baseline_crit
                    if score_value is not None and referee_score is not None
                ]
                variant_crit = [
                    (score_value, referee_score)
                    for score_value, referee_score in variant_crit
                    if score_value is not None and referee_score is not None
                ]

                if baseline_crit or variant_crit:
                    crit_result: dict[str, Any] = {}
                    if baseline_crit:
                        # baseline_crit has already filtered out None values
                        # Mypy doesn't track type narrowing through list comprehensions
                        crit_result["baseline"] = self._compute_alignment_metrics(
                            [({"score": sv}, rs) for sv, rs in baseline_crit]  # type: ignore[dict-item]
                        )
                    if variant_crit:
                        # variant_crit has already filtered out None values
                        # Mypy doesn't track type narrowing through list comprehensions
                        crit_result["variant"] = self._compute_alignment_metrics(
                            [({"score": sv}, rs) for sv, rs in variant_crit]  # type: ignore[dict-item]
                        )
                    criteria_results[crit_name] = crit_result

            if criteria_results:
                results["criteria"] = criteria_results

        return results

    def _extract_score_pairs(self, payload: dict[str, Any]) -> list[tuple[dict[str, float], float]]:
        """Extract (LLM scores dict, referee score) pairs from experiment results."""
        pairs: list[tuple[dict[str, float], float]] = []

        for result in payload.get("results", []) or []:
            row = result.get("row") or {}
            metrics = result.get("metrics") or {}

            # Extract referee score from row data
            referee_score = self._extract_referee_score(row)
            if referee_score is None:
                continue

            # Extract LLM scores
            llm_scores = metrics.get(self._score_field)
            if not isinstance(llm_scores, Mapping):
                continue

            # Convert to dict of floats
            score_dict: dict[str, float] = {}
            for crit_name, value in llm_scores.items():
                if self._criteria and crit_name not in self._criteria:
                    continue
                try:
                    score_val = float(value)
                    if not math.isnan(score_val):
                        score_dict[crit_name] = score_val
                except (TypeError, ValueError):
                    continue

            if score_dict:
                pairs.append((score_dict, referee_score))

        return pairs

    def _extract_referee_score(self, row: dict[str, Any]) -> float | None:
        """Extract and aggregate referee score from row data."""
        referee_values: list[float] = []

        for field_name in self._referee_fields:
            value = row.get(field_name)
            if value is None:
                continue

            # Try to convert to float
            converted = self._convert_referee_value(value)
            if converted is not None:
                referee_values.append(converted)

        # Return mean of all referee values
        return float(np.mean(referee_values)) if referee_values else None

    def _convert_referee_value(self, value: Any) -> float | None:
        """Convert referee value to float using mapping or direct conversion."""
        # Try direct numeric conversion first
        if isinstance(value, (int, float)):
            return float(value) if not math.isnan(float(value)) else None

        # Try string mapping
        if isinstance(value, str):
            value_lower = value.strip().lower()
            if value_lower in self._value_mapping:
                return self._value_mapping[value_lower]

            # Try parsing as number
            try:
                return float(value)
            except ValueError:
                pass

        return None

    def _compute_alignment_metrics(self, pairs: list[tuple[dict[str, float], float]]) -> dict[str, Any]:
        """Compute alignment metrics from (LLM scores, referee score) pairs."""
        if len(pairs) < self._min_samples:
            return {}

        # Compute mean LLM score for each pair
        llm_means: list[float] = []
        referee_scores: list[float] = []

        for llm_dict, ref_score in pairs:
            if llm_dict:
                llm_means.append(float(np.mean(list(llm_dict.values()))))
                referee_scores.append(ref_score)

        if not llm_means:
            return {}

        # Mean Absolute Error (lower is better)
        mae = float(np.mean([abs(llm - ref) for llm, ref in zip(llm_means, referee_scores)]))

        # Root Mean Square Error
        rmse = float(np.sqrt(np.mean([(llm - ref) ** 2 for llm, ref in zip(llm_means, referee_scores)])))

        # Correlation (higher is better)
        correlation = None
        if len(llm_means) >= 2:
            try:
                corr_matrix = np.corrcoef(llm_means, referee_scores)
                corr_val = corr_matrix[0, 1]
                if not np.isnan(corr_val):
                    correlation = float(corr_val)
            except Exception:  # pragma: no cover
                correlation = None

        # Agreement rate (within 1 point)
        within_1 = sum(1 for llm, ref in zip(llm_means, referee_scores) if abs(llm - ref) <= 1.0)
        agreement_rate = within_1 / len(llm_means)

        return {
            "samples": len(llm_means),
            "mean_absolute_error": mae,
            "root_mean_square_error": rmse,
            "correlation": correlation,
            "agreement_rate_within_1": agreement_rate,
            "llm_mean": float(np.mean(llm_means)),
            "llm_std": float(np.std(llm_means)),
            "referee_mean": float(np.mean(referee_scores)),
            "referee_std": float(np.std(referee_scores)),
        }


def _create_referee_alignment(options: dict[str, Any], context: PluginContext) -> RefereeAlignmentBaselinePlugin:
    """Create referee alignment baseline plugin with smart security defaults."""
    opts = dict(options)
    if "security_level" not in opts and context:
        opts["security_level"] = context.security_level
    return RefereeAlignmentBaselinePlugin(
        security_level=opts["security_level"],
        referee_fields=opts.get("referee_fields"),
        score_field=opts.get("score_field", "scores"),
        criteria=opts.get("criteria"),
        min_samples=int(opts.get("min_samples", 2)),
        value_mapping=opts.get("value_mapping"),
        on_error=opts.get("on_error", "abort"),
    )


register_baseline_plugin(
    "referee_alignment",
    _create_referee_alignment,
    schema=_REFEREE_SCHEMA,
)


# =====================================================================
# Priority 2 Features: Outlier Detection, Score Flips, Category Effects, Criteria Effects
# =====================================================================

_OUTLIER_SCHEMA = {
    "type": "object",
    "properties": {
        "top_n": {"type": "integer", "minimum": 1},
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_delta": {"type": "number", "minimum": 0},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


__all__ = ["RefereeAlignmentBaselinePlugin"]
