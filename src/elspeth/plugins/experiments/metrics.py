"""Metrics and statistical experiment plugins."""

from __future__ import annotations

import json
import logging
import math
from statistics import NormalDist
from typing import Any, Dict, Mapping, Sequence

import numpy as np

from elspeth.core.experiments.plugin_registry import register_aggregation_plugin, register_baseline_plugin, register_row_plugin

logger = logging.getLogger(__name__)

try:
    from scipy import stats as scipy_stats  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    scipy_stats = None

try:
    import pingouin  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pingouin = None

try:
    from statsmodels.stats.power import TTestPower  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    TTestPower = None

_ON_ERROR_SCHEMA = {"type": "string", "enum": ["abort", "skip"]}

_ROW_SCHEMA = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "criteria": {"type": "array", "items": {"type": "string"}},
        "parse_json_content": {"type": "boolean"},
        "allow_missing": {"type": "boolean"},
        "threshold": {"type": "number"},
        "threshold_mode": {"type": "string", "enum": ["gt", "gte", "lt", "lte"]},
        "flag_field": {"type": "string"},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}

_STATS_SCHEMA = {
    "type": "object",
    "properties": {
        "source_field": {"type": "string"},
        "flag_field": {"type": "string"},
        "ddof": {"type": "integer", "minimum": 0},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}

_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "min_samples": {"type": "integer", "minimum": 0},
        "improvement_margin": {"type": "number"},
        "source_field": {"type": "string"},
        "flag_field": {"type": "string"},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}

_DELTA_SCHEMA = {
    "type": "object",
    "properties": {
        "metric": {"type": "string"},
        "criteria": {"type": "array", "items": {"type": "string"}},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}

_CLIFFS_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 1},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}

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

_PRACTICAL_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "threshold": {"type": "number"},
        "success_threshold": {"type": "number"},
        "min_samples": {"type": "integer", "minimum": 1},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}

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

_AGREEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_items": {"type": "integer", "minimum": 2},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}

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

_DISTRIBUTION_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"}},
        "min_samples": {"type": "integer", "minimum": 2},
        "on_error": _ON_ERROR_SCHEMA,
    },
    "additionalProperties": True,
}


class ScoreExtractorPlugin:
    """Extract numeric scores from LLM responses.

    The plugin inspects the per-criteria response payload for numeric values under
    the configured key (default: ``score``). Values are normalised to ``float``
    whenever possible. When ``threshold`` is supplied the plugin also flags rows
    that meet the threshold for downstream aggregators.
    """

    name = "score_extractor"

    def __init__(
        self,
        *,
        key: str = "score",
        criteria: list[str] | None = None,
        parse_json_content: bool = True,
        allow_missing: bool = False,
        threshold: float | None = None,
        threshold_mode: str = "gte",
        flag_field: str = "score_flags",
    ) -> None:
        self._key = key
        self._criteria = set(criteria) if criteria else None
        self._parse_json = parse_json_content
        self._allow_missing = allow_missing
        self._threshold = threshold
        self._threshold_mode = threshold_mode
        self._flag_field = flag_field

    def process_row(self, row: Dict[str, Any], responses: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
        scores: Dict[str, float] = {}
        flags: Dict[str, bool] = {}

        for crit_name, response in responses.items():
            if self._criteria and crit_name not in self._criteria:
                continue
            value = self._extract_value(response)
            if value is None:
                if not self._allow_missing:
                    scores[crit_name] = np.nan
                continue
            scores[crit_name] = value
            if self._threshold is not None:
                flags[crit_name] = self._compare_threshold(value)

        derived: Dict[str, Any] = {}
        if scores:
            derived.setdefault("scores", {}).update(scores)
        if flags:
            derived[self._flag_field] = flags
        return derived

    def _extract_value(self, response: Mapping[str, Any]) -> float | None:
        metrics = response.get("metrics") if isinstance(response, Mapping) else None
        if isinstance(metrics, Mapping) and self._key in metrics:
            return self._coerce_number(metrics.get(self._key))

        if self._parse_json:
            content = response.get("content") if isinstance(response, Mapping) else None
            if isinstance(content, str):
                try:
                    payload = json.loads(content)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, Mapping) and self._key in payload:
                    return self._coerce_number(payload.get(self._key))
        return None

    @staticmethod
    def _coerce_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned.endswith("%"):
                cleaned = cleaned[:-1]
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    def _compare_threshold(self, value: float) -> bool:
        mode = self._threshold_mode
        threshold = float(self._threshold)
        if mode == "gt":
            return value > threshold
        if mode == "gte":
            return value >= threshold
        if mode == "lt":
            return value < threshold
        if mode == "lte":
            return value <= threshold
        raise ValueError(f"Unsupported threshold_mode '{mode}'")


register_row_plugin(
    "score_extractor",
    lambda options, context: ScoreExtractorPlugin(
        key=options.get("key", "score"),
        criteria=options.get("criteria"),
        parse_json_content=options.get("parse_json_content", True),
        allow_missing=options.get("allow_missing", False),
        threshold=options.get("threshold"),
        threshold_mode=options.get("threshold_mode", "gte"),
        flag_field=options.get("flag_field", "score_flags"),
    ),
    schema=_ROW_SCHEMA,
)


class ScoreStatsAggregator:
    """Aggregate score statistics across all rows."""

    name = "score_stats"

    def __init__(
        self,
        *,
        source_field: str = "scores",
        flag_field: str = "score_flags",
        ddof: int = 0,
    ) -> None:
        self._source_field = source_field
        self._flag_field = flag_field
        self._ddof = ddof

    def finalize(self, records: list[Dict[str, Any]]) -> Dict[str, Any]:
        criteria_values: Dict[str, Dict[str, Any]] = {}

        for record in records:
            metrics = record.get("metrics") or {}
            scores = metrics.get(self._source_field)
            if isinstance(scores, Mapping):
                for crit, value in scores.items():
                    slot = criteria_values.setdefault(crit, {"values": [], "missing": 0, "passes": 0})
                    if value is None or (isinstance(value, float) and math.isnan(value)):
                        slot["missing"] += 1
                        continue
                    slot["values"].append(float(value))
            flags = metrics.get(self._flag_field)
            if isinstance(flags, Mapping):
                for crit, passed in flags.items():
                    slot = criteria_values.setdefault(crit, {"values": [], "missing": 0, "passes": 0})
                    if passed:
                        slot["passes"] += 1

        summaries: Dict[str, Any] = {}
        all_values: list[float] = []
        total_missing = 0
        total_pass = 0

        for crit, payload in criteria_values.items():
            values = payload.get("values", [])
            missing = payload.get("missing", 0)
            passes = payload.get("passes", 0)
            total_missing += missing
            total_pass += passes
            all_values.extend(values)
            summary = self._summarize_values(values, missing, passes)
            summaries[crit] = summary

        overall = self._summarize_values(all_values, total_missing, total_pass)
        return {
            "criteria": summaries,
            "overall": overall,
        }

    def _summarize_values(self, values: list[float], missing: int, passes: int) -> Dict[str, Any]:
        count = len(values)
        total = count + missing
        result: Dict[str, Any] = {
            "count": count,
            "missing": missing,
        }
        if count:
            arr = np.array(values, dtype=float)
            result.update(
                {
                    "mean": float(np.mean(arr)),
                    "median": float(np.median(arr)),
                    "min": float(np.min(arr)),
                    "max": float(np.max(arr)),
                }
            )
            if count > 1:
                result["std"] = float(np.std(arr, ddof=self._ddof))
            else:
                result["std"] = 0.0
        if total:
            result["pass_rate"] = passes / total
            result["passes"] = passes
        return result


class ScoreDeltaBaselinePlugin:
    """Compare score statistics between baseline and variant."""

    name = "score_delta"

    def __init__(self, *, metric: str = "mean", criteria: list[str] | None = None) -> None:
        self._metric = metric
        self._criteria = set(criteria) if criteria else None

    def compare(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        base_stats = self._extract_stats(baseline)
        var_stats = self._extract_stats(variant)
        if not base_stats or not var_stats:
            return {}

        diffs: Dict[str, Any] = {}
        keys = set(base_stats.keys()) & set(var_stats.keys())
        for crit in sorted(keys):
            if self._criteria and crit not in self._criteria:
                continue
            base_metric = base_stats[crit].get(self._metric)
            var_metric = var_stats[crit].get(self._metric)
            if base_metric is None or var_metric is None:
                continue
            diffs[crit] = var_metric - base_metric
        return diffs

    @staticmethod
    def _extract_stats(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        aggregates = payload.get("aggregates") if isinstance(payload, Mapping) else None
        if not isinstance(aggregates, Mapping):
            return {}
        stats = aggregates.get("score_stats")
        if not isinstance(stats, Mapping):
            return {}
        criteria = stats.get("criteria")
        if not isinstance(criteria, Mapping):
            return {}
        return criteria


register_aggregation_plugin(
    "score_stats",
    lambda options, context: ScoreStatsAggregator(
        source_field=options.get("source_field", "scores"),
        flag_field=options.get("flag_field", "score_flags"),
        ddof=int(options.get("ddof", 0)),
    ),
    schema=_STATS_SCHEMA,
)

register_baseline_plugin(
    "score_delta",
    lambda options, context: ScoreDeltaBaselinePlugin(
        metric=options.get("metric", "mean"),
        criteria=options.get("criteria"),
    ),
    schema=_DELTA_SCHEMA,
)


class ScoreCliffsDeltaPlugin:
    """Compute Cliff's delta effect size between baseline and variant."""

    name = "score_cliffs_delta"

    def __init__(self, *, criteria: Sequence[str] | None = None, min_samples: int = 1, on_error: str = "abort") -> None:
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 1)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive guard
            if self._on_error == "skip":
                logger.warning("score_cliffs_delta skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        base_scores = _collect_scores_by_criterion(baseline)
        var_scores = _collect_scores_by_criterion(variant)
        criteria = sorted(set(base_scores.keys()) & set(var_scores.keys()))
        if self._criteria is not None:
            criteria = [name for name in criteria if name in self._criteria]

        results: Dict[str, Any] = {}
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


register_baseline_plugin(
    "score_cliffs_delta",
    lambda options, context: ScoreCliffsDeltaPlugin(
        criteria=options.get("criteria"),
        min_samples=int(options.get("min_samples", 1)),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_CLIFFS_SCHEMA,
)


class ScoreAssumptionsBaselinePlugin:
    """Report normality and variance diagnostics for baseline vs. variant scores."""

    name = "score_assumptions"

    def __init__(
        self,
        *,
        criteria: Sequence[str] | None = None,
        min_samples: int = 3,
        alpha: float = 0.05,
        on_error: str = "abort",
    ) -> None:
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 3)
        self._alpha = float(alpha)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover
            if self._on_error == "skip":
                logger.warning("score_assumptions skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        if scipy_stats is None:
            return {}
        base_scores = _collect_scores_by_criterion(baseline)
        var_scores = _collect_scores_by_criterion(variant)
        criteria = sorted(set(base_scores.keys()) & set(var_scores.keys()))
        if self._criteria is not None:
            criteria = [name for name in criteria if name in self._criteria]

        results: Dict[str, Any] = {}
        for name in criteria:
            base = base_scores.get(name, [])
            var = var_scores.get(name, [])
            entry: Dict[str, Any] = {}
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


register_baseline_plugin(
    "score_assumptions",
    lambda options, context: ScoreAssumptionsBaselinePlugin(
        criteria=options.get("criteria"),
        min_samples=int(options.get("min_samples", 3)),
        alpha=float(options.get("alpha", 0.05)),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_ASSUMPTION_SCHEMA,
)


class ScorePracticalBaselinePlugin:
    """Assess practical significance (meaningful change, NNT, success deltas)."""

    name = "score_practical"

    def __init__(
        self,
        *,
        criteria: Sequence[str] | None = None,
        threshold: float = 1.0,
        success_threshold: float = 4.0,
        min_samples: int = 1,
        on_error: str = "abort",
    ) -> None:
        self._criteria = set(criteria) if criteria else None
        self._threshold = float(threshold)
        self._success_threshold = float(success_threshold)
        self._min_samples = max(int(min_samples), 1)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover
            if self._on_error == "skip":
                logger.warning("score_practical skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        pairs = _collect_paired_scores_by_criterion(baseline, variant)
        criteria = sorted(pairs.keys())
        if self._criteria is not None:
            criteria = [name for name in criteria if name in self._criteria]

        results: Dict[str, Any] = {}
        for name in criteria:
            paired = pairs.get(name, [])
            if len(paired) < self._min_samples:
                continue
            diffs = [v - b for b, v in paired]
            meaningful = [abs(d) >= self._threshold for d in diffs]
            meaningful_rate = sum(meaningful) / len(paired)
            baseline_success = sum(1 for b, _ in paired if b >= self._success_threshold) / len(paired)
            variant_success = sum(1 for _, v in paired if v >= self._success_threshold) / len(paired)
            success_delta = variant_success - baseline_success
            if success_delta > 0:
                nnt = 1.0 / success_delta
            else:
                nnt = float("inf")
            results[name] = {
                "pairs": len(paired),
                "mean_difference": float(np.mean(diffs)),
                "median_difference": float(np.median(diffs)),
                "meaningful_change_rate": meaningful_rate,
                "success_threshold": self._success_threshold,
                "baseline_success_rate": baseline_success,
                "variant_success_rate": variant_success,
                "success_delta": success_delta,
                "number_needed_to_treat": nnt,
            }
        return results


register_baseline_plugin(
    "score_practical",
    lambda options, context: ScorePracticalBaselinePlugin(
        criteria=options.get("criteria"),
        threshold=float(options.get("threshold", 1.0)),
        success_threshold=float(options.get("success_threshold", 4.0)),
        min_samples=int(options.get("min_samples", 1)),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_PRACTICAL_SCHEMA,
)


class ScoreSignificanceBaselinePlugin:
    """Compare baseline and variant using effect sizes and t-tests."""

    name = "score_significance"

    def __init__(
        self,
        *,
        criteria: Sequence[str] | None = None,
        min_samples: int = 2,
        equal_var: bool = False,
        adjustment: str = "none",
        family_size: int | None = None,
        on_error: str = "abort",
    ) -> None:
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

    def compare(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive guard
            if self._on_error == "skip":
                logger.warning("score_significance skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
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


register_baseline_plugin(
    "score_significance",
    lambda options, context: ScoreSignificanceBaselinePlugin(
        criteria=options.get("criteria"),
        min_samples=int(options.get("min_samples", 2)),
        equal_var=bool(options.get("equal_var", False)),
        adjustment=options.get("adjustment", "none"),
        family_size=options.get("family_size"),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_SIGNIFICANCE_SCHEMA,
)


class ScoreBayesianBaselinePlugin:
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
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 2)
        self._ci = min(max(float(credible_interval), 0.5), 0.999)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def compare(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive guard
            if self._on_error == "skip":
                logger.warning("score_bayes skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
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


register_baseline_plugin(
    "score_bayes",
    lambda options, context: ScoreBayesianBaselinePlugin(
        criteria=options.get("criteria"),
        min_samples=int(options.get("min_samples", 2)),
        credible_interval=float(options.get("credible_interval", 0.95)),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_BAYESIAN_SCHEMA,
)


class ScoreRecommendationAggregator:
    """Generate a lightweight recommendation based on score statistics."""

    name = "score_recommendation"

    def __init__(
        self,
        *,
        min_samples: int = 5,
        improvement_margin: float = 0.05,
        source_field: str = "scores",
        flag_field: str = "score_flags",
    ) -> None:
        self._min_samples = min_samples
        self._improvement_margin = improvement_margin
        self._stats = ScoreStatsAggregator(source_field=source_field, flag_field=flag_field)

    def finalize(self, records: list[Dict[str, Any]]) -> Dict[str, Any]:
        stats = self._stats.finalize(records)
        overall = stats.get("overall", {})
        criteria = stats.get("criteria", {})
        count = overall.get("count", 0)

        if count < self._min_samples:
            message = "Insufficient data for confident recommendation"
            best = None
        else:
            best = self._select_best(criteria)
            if not best:
                message = "No clear leader across criteria"
            else:
                message = self._build_message(best, criteria[best], overall)

        payload: Dict[str, Any] = {
            "recommendation": message,
            "summary": overall,
        }
        if best:
            payload["best_criteria"] = best
            payload["best_stats"] = criteria[best]
        return payload

    def _select_best(self, criteria: Mapping[str, Mapping[str, Any]]) -> str | None:
        best_name = None
        best_mean = float("-inf")
        for name, summary in criteria.items():
            mean = summary.get("mean")
            if mean is None:
                continue
            if mean > best_mean:
                best_name = name
                best_mean = mean
        return best_name

    def _build_message(self, name: str, stats: Mapping[str, Any], overall: Mapping[str, Any]) -> str:
        mean = stats.get("mean")
        pass_rate = stats.get("pass_rate")
        overall_mean = overall.get("mean")

        clauses = [f"{name} leads with mean score {mean:.2f}" if mean is not None else f"{name} leads"]
        if pass_rate is not None:
            clauses.append(f"pass rate {pass_rate:.0%}")
        if overall_mean is not None and mean is not None:
            delta = mean - overall_mean
            if abs(delta) >= self._improvement_margin:
                direction = "above" if delta > 0 else "below"
                clauses.append(f"which is {abs(delta):.2f} {direction} overall average")
        return ", ".join(clauses)


register_aggregation_plugin(
    "score_recommendation",
    lambda options, context: ScoreRecommendationAggregator(
        min_samples=int(options.get("min_samples", 5)),
        improvement_margin=float(options.get("improvement_margin", 0.05)),
        source_field=options.get("source_field", "scores"),
        flag_field=options.get("flag_field", "score_flags"),
    ),
    schema=_RECOMMENDATION_SCHEMA,
)


class ScoreVariantRankingAggregator:
    """Compute a simple composite ranking score for an experiment."""

    name = "score_variant_ranking"

    def __init__(self, *, threshold: float = 0.7, weight_mean: float = 1.0, weight_pass: float = 1.0) -> None:
        self._threshold = float(threshold)
        self._weight_mean = float(weight_mean)
        self._weight_pass = float(weight_pass)

    def finalize(self, records: list[Dict[str, Any]]) -> Dict[str, Any]:
        values = []
        pass_count = 0
        for record in records:
            metrics = record.get("metrics") or {}
            # Prefer aggregated "score" field, fallback to mean of per-criteria
            base_value = metrics.get("score")
            if base_value is None and isinstance(metrics.get("scores"), Mapping):
                scores_map = metrics["scores"]
                try:
                    numbers = [float(v) for v in scores_map.values()]
                except (TypeError, ValueError):
                    numbers = []
                if numbers:
                    base_value = float(np.mean(numbers))
            if base_value is None:
                continue
            try:
                number = float(base_value)
            except (TypeError, ValueError):
                continue
            if math.isnan(number):
                continue
            values.append(number)
            if number >= self._threshold:
                pass_count += 1
        if not values:
            return {}
        arr = np.asarray(values, dtype=float)
        mean = float(arr.mean())
        median = float(np.median(arr))
        score = self._weight_mean * mean + self._weight_pass * (pass_count / len(values))
        return {
            "samples": len(values),
            "mean": mean,
            "median": median,
            "min": float(arr.min()),
            "max": float(arr.max()),
            "threshold": self._threshold,
            "pass_rate": pass_count / len(values),
            "composite_score": score,
        }


register_aggregation_plugin(
    "score_variant_ranking",
    lambda options, context: ScoreVariantRankingAggregator(
        threshold=float(options.get("threshold", 0.7)),
        weight_mean=float(options.get("weight_mean", 1.0)),
        weight_pass=float(options.get("weight_pass", 1.0)),
    ),
    schema={
        "type": "object",
        "properties": {
            "threshold": {"type": "number"},
            "weight_mean": {"type": "number"},
            "weight_pass": {"type": "number"},
        },
        "additionalProperties": True,
    },
)


class ScoreAgreementAggregator:
    """Assess agreement/reliability across criteria scores."""

    name = "score_agreement"

    def __init__(self, *, criteria: Sequence[str] | None = None, min_items: int = 2, on_error: str = "abort") -> None:
        self._criteria = list(criteria) if criteria else None
        self._min_items = max(int(min_items), 2)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def finalize(self, records: list[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            return self._finalize_impl(records)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("score_agreement skipped due to error: %s", exc)
                return {}
            raise

    def _finalize_impl(self, records: list[Dict[str, Any]]) -> Dict[str, Any]:
        if not records:
            return {}

        matrix: Dict[str, list[float]] = {}
        for record in records:
            metrics = record.get("metrics") or {}
            scores = metrics.get("scores") or {}
            if not isinstance(scores, Mapping):
                continue
            for name, value in scores.items():
                if self._criteria and name not in self._criteria:
                    continue
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isnan(number):
                    continue
                matrix.setdefault(name, []).append(number)

        usable = {name: values for name, values in matrix.items() if len(values) >= self._min_items}
        if len(usable) < 2:
            return {}

        columns = sorted(usable.keys())
        lengths = [len(usable[name]) for name in columns]
        max_len = max(lengths)
        data = []
        for idx in range(max_len):
            row = []
            for name in columns:
                values = usable[name]
                row.append(values[idx] if idx < len(values) else np.nan)
            data.append(row)
        arr = np.array(data, dtype=float)

        mask = ~np.isnan(arr).all(axis=1)
        arr = arr[mask]
        if arr.shape[0] < self._min_items:
            return {}

        item_variances = np.nanvar(arr, axis=0, ddof=1)
        total_variance = np.nanvar(arr, ddof=1)
        n_items = arr.shape[1]
        if total_variance <= 0 or n_items < 2 or np.isnan(total_variance):
            cronbach_alpha = None
        else:
            cronbach_alpha = (n_items / (n_items - 1)) * (1 - np.nansum(item_variances) / total_variance)

        correlations = []
        for i in range(n_items):
            for j in range(i + 1, n_items):
                col_i = arr[:, i]
                col_j = arr[:, j]
                valid = ~np.isnan(col_i) & ~np.isnan(col_j)
                if valid.sum() >= 2:
                    corr = np.corrcoef(col_i[valid], col_j[valid])[0, 1]
                    if not np.isnan(corr):
                        correlations.append(corr)
        avg_correlation = float(np.mean(correlations)) if correlations else None

        krippendorff_alpha = None
        if pingouin is not None and arr.shape[1] >= 2:
            try:
                import pandas as pd

                df = pd.DataFrame({columns[i]: arr[:, i] for i in range(n_items)})
                krippendorff_alpha = float(pingouin.krippendorff_alpha(df, reliability_data=True))
            except Exception:  # pragma: no cover - pingouin failure
                krippendorff_alpha = None

        return {
            "criteria": columns,
            "cronbach_alpha": cronbach_alpha,
            "average_correlation": avg_correlation,
            "krippendorff_alpha": krippendorff_alpha,
        }


register_aggregation_plugin(
    "score_agreement",
    lambda options, context: ScoreAgreementAggregator(
        criteria=options.get("criteria"),
        min_items=int(options.get("min_items", 2)),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_AGREEMENT_SCHEMA,
)


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

    def finalize(self, records: list[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            return self._finalize_impl(records)
        except Exception as exc:  # pragma: no cover - defensive
            if self._on_error == "skip":
                logger.warning("score_power skipped due to error: %s", exc)
                return {}
            raise

    def _finalize_impl(self, records: list[Dict[str, Any]]) -> Dict[str, Any]:
        if not records:
            return {}
        scores_by_name = _collect_scores_by_criterion({"results": records})
        criteria = sorted(scores_by_name.keys())
        if self._criteria is not None:
            criteria = [name for name in criteria if name in self._criteria]

        power_results: Dict[str, Any] = {}
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


class ScoreDistributionAggregator:
    """Assess distribution shifts between baseline and variant deployments."""

    name = "score_distribution"

    def __init__(
        self,
        *,
        criteria: Sequence[str] | None = None,
        min_samples: int = 2,
        on_error: str = "abort",
    ) -> None:
        self._criteria = set(criteria) if criteria else None
        self._min_samples = max(int(min_samples), 2)
        if on_error not in {"abort", "skip"}:
            raise ValueError("on_error must be 'abort' or 'skip'")
        self._on_error = on_error

    def finalize(self, records: list[Dict[str, Any]]) -> Dict[str, Any]:
        # This aggregator expects to inspect baseline + variant payloads, so per-run finalize is empty.
        return {}

    def compare(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._compare_impl(baseline, variant)
        except Exception as exc:  # pragma: no cover - defensive guard
            if self._on_error == "skip":
                logger.warning("score_distribution skipped due to error: %s", exc)
                return {}
            raise

    def _compare_impl(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        base_scores = _collect_scores_by_criterion(baseline)
        var_scores = _collect_scores_by_criterion(variant)
        criteria = sorted(set(base_scores.keys()) & set(var_scores.keys()))
        if self._criteria is not None:
            criteria = [name for name in criteria if name in self._criteria]
        results: Dict[str, Any] = {}
        for name in criteria:
            base = base_scores.get(name, [])
            var = var_scores.get(name, [])
            if len(base) < self._min_samples or len(var) < self._min_samples:
                continue
            stats = _compute_distribution_shift(base, var)
            if stats:
                results[name] = stats
        return results


register_baseline_plugin(
    "score_distribution",
    lambda options, context: ScoreDistributionAggregator(
        criteria=options.get("criteria"),
        min_samples=int(options.get("min_samples", 2)),
        on_error=options.get("on_error", "abort"),
    ),
    schema=_DISTRIBUTION_SCHEMA,
)


def _collect_scores_by_criterion(payload: Mapping[str, Any]) -> Dict[str, list[float]]:
    scores_by_name: Dict[str, list[float]] = {}
    for record in payload.get("results", []) or []:
        metrics = record.get("metrics") or {}
        scores = metrics.get("scores") or {}
        if not isinstance(scores, Mapping):
            continue
        for name, value in scores.items():
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isnan(number):
                continue
            scores_by_name.setdefault(name, []).append(number)
    return scores_by_name


def _collect_paired_scores_by_criterion(
    baseline: Mapping[str, Any],
    variant: Mapping[str, Any],
) -> Dict[str, list[tuple[float, float]]]:
    baseline_results = baseline.get("results", []) or []
    variant_results = variant.get("results", []) or []
    count = min(len(baseline_results), len(variant_results))
    pairs: Dict[str, list[tuple[float, float]]] = {}
    for index in range(count):
        base_metrics = (baseline_results[index].get("metrics") if isinstance(baseline_results[index], Mapping) else {}) or {}
        var_metrics = (variant_results[index].get("metrics") if isinstance(variant_results[index], Mapping) else {}) or {}
        base_scores = base_metrics.get("scores") or {}
        var_scores = var_metrics.get("scores") or {}
        if not isinstance(base_scores, Mapping) or not isinstance(var_scores, Mapping):
            continue
        for name, base_value in base_scores.items():
            if name not in var_scores:
                continue
            try:
                base_number = float(base_value)
                var_number = float(var_scores[name])
            except (TypeError, ValueError):
                continue
            if math.isnan(base_number) or math.isnan(var_number):
                continue
            pairs.setdefault(name, []).append((base_number, var_number))
    return pairs


def _calculate_cliffs_delta(group1: Sequence[float], group2: Sequence[float]) -> tuple[float, str]:
    arr1 = np.asarray(list(group1), dtype=float)
    arr2 = np.asarray(list(group2), dtype=float)
    if arr1.size == 0 or arr2.size == 0:
        return 0.0, "no_data"
    dominance = 0
    for x in arr1:
        dominance += np.sum(arr2 > x)
        dominance -= np.sum(arr2 < x)
    delta = dominance / (arr1.size * arr2.size)
    abs_delta = abs(delta)
    if abs_delta < 0.147:
        interpretation = "negligible"
    elif abs_delta < 0.33:
        interpretation = "small"
    elif abs_delta < 0.474:
        interpretation = "medium"
    else:
        interpretation = "large"
    return float(delta), interpretation


def _compute_significance(
    baseline: Sequence[float],
    variant: Sequence[float],
    *,
    equal_var: bool = False,
) -> Dict[str, Any]:
    arr_base = np.asarray(list(baseline), dtype=float)
    arr_var = np.asarray(list(variant), dtype=float)
    n_base = arr_base.size
    n_var = arr_var.size
    mean_base = float(arr_base.mean()) if n_base else 0.0
    mean_var = float(arr_var.mean()) if n_var else 0.0
    mean_diff = mean_var - mean_base
    var_base = float(arr_base.var(ddof=1)) if n_base > 1 else 0.0
    var_var = float(arr_var.var(ddof=1)) if n_var > 1 else 0.0
    std_base = math.sqrt(var_base) if var_base > 0 else 0.0
    std_var = math.sqrt(var_var) if var_var > 0 else 0.0

    denom = math.sqrt((var_base / n_base if n_base > 0 else 0.0) + (var_var / n_var if n_var > 0 else 0.0))
    t_stat = mean_diff / denom if denom > 0 else None

    df = None

    if equal_var and n_base > 1 and n_var > 1:
        df = n_base + n_var - 2
    else:
        term_base = (var_base / n_base) if n_base > 1 else 0.0
        term_var = (var_var / n_var) if n_var > 1 else 0.0
        denom_terms = term_base + term_var
        if denom_terms > 0:
            numerator = denom_terms**2
            denominator = 0.0
            if n_base > 1 and term_base > 0:
                denominator += (term_base**2) / (n_base - 1)
            if n_var > 1 and term_var > 0:
                denominator += (term_var**2) / (n_var - 1)
            df = numerator / denominator if denominator > 0 else None
        else:
            df = None

    pooled = None
    if n_base > 1 and n_var > 1:
        pooled = ((n_base - 1) * var_base + (n_var - 1) * var_var) / (n_base + n_var - 2)
    effect_size = None
    if pooled is not None and pooled > 0:
        effect_size = mean_diff / math.sqrt(pooled)
    elif std_base > 0 or std_var > 0:
        pooled_var = ((std_base**2) + (std_var**2)) / 2
        if pooled_var > 0:
            effect_size = mean_diff / math.sqrt(pooled_var)

    p_value = None
    if t_stat is not None and "df" in locals() and df is not None and scipy_stats is not None:
        try:
            p_value = float(scipy_stats.t.sf(abs(t_stat), df) * 2)
        except Exception:  # pragma: no cover - scipy failure
            p_value = None

    return {
        "baseline_mean": mean_base,
        "variant_mean": mean_var,
        "mean_difference": mean_diff,
        "baseline_std": std_base,
        "variant_std": std_var,
        "baseline_samples": n_base,
        "variant_samples": n_var,
        "effect_size": effect_size,
        "t_stat": t_stat,
        "degrees_of_freedom": df,
        "p_value": p_value,
    }


def _compute_bayesian_summary(
    baseline: Sequence[float],
    variant: Sequence[float],
    alpha: float,
) -> Dict[str, Any]:
    arr_base = np.asarray(list(baseline), dtype=float)
    arr_var = np.asarray(list(variant), dtype=float)
    n_base = arr_base.size
    n_var = arr_var.size
    mean_base = float(arr_base.mean()) if n_base else 0.0
    mean_var = float(arr_var.mean()) if n_var else 0.0
    mean_diff = mean_var - mean_base
    var_base = float(arr_base.var(ddof=1)) if n_base > 1 else 0.0
    var_var = float(arr_var.var(ddof=1)) if n_var > 1 else 0.0
    stderr = math.sqrt((var_base / n_base if n_base > 0 else 0.0) + (var_var / n_var if n_var > 0 else 0.0))
    if stderr <= 0:
        return {}

    term_base = (var_base / n_base) if n_base > 1 else 0.0
    term_var = (var_var / n_var) if n_var > 1 else 0.0
    denom_terms = term_base + term_var
    df = None
    if denom_terms > 0:
        numerator = denom_terms**2
        denominator = 0.0
        if n_base > 1 and term_base > 0:
            denominator += (term_base**2) / (n_base - 1)
        if n_var > 1 and term_var > 0:
            denominator += (term_var**2) / (n_var - 1)
        df = numerator / denominator if denominator > 0 else None

    if df is not None and scipy_stats is not None:
        dist = scipy_stats.t(df, loc=mean_diff, scale=stderr)
        prob = 1 - float(dist.cdf(0))
        half_width = float(dist.ppf(1 - alpha / 2) - mean_diff)
        ci_lower = mean_diff - half_width
        ci_upper = mean_diff + half_width
    else:
        norm = NormalDist(mean_diff, stderr)
        prob = 1 - norm.cdf(0)
        z = NormalDist().inv_cdf(1 - alpha / 2)
        ci_lower = mean_diff - z * stderr
        ci_upper = mean_diff + z * stderr

    return {
        "baseline_mean": mean_base,
        "variant_mean": mean_var,
        "mean_difference": mean_diff,
        "std_error": stderr,
        "degrees_of_freedom": df,
        "prob_variant_gt_baseline": prob,
        "credible_interval": [ci_lower, ci_upper],
    }


def _compute_distribution_shift(
    baseline: Sequence[float],
    variant: Sequence[float],
) -> Dict[str, Any]:
    arr_base = np.asarray(list(baseline), dtype=float)
    arr_var = np.asarray(list(variant), dtype=float)
    n_base = arr_base.size
    n_var = arr_var.size
    mean_base = float(arr_base.mean()) if n_base else 0.0
    mean_var = float(arr_var.mean()) if n_var else 0.0
    var_base = float(arr_base.var(ddof=1)) if n_base > 1 else 0.0
    var_var = float(arr_var.var(ddof=1)) if n_var > 1 else 0.0
    std_base = math.sqrt(var_base) if var_base > 0 else 0.0
    std_var = math.sqrt(var_var) if var_var > 0 else 0.0

    ks_stat = None
    ks_pvalue = None
    if scipy_stats is not None and n_base >= 2 and n_var >= 2:
        try:
            ks = scipy_stats.ks_2samp(arr_base, arr_var, alternative="two-sided")
            ks_stat = float(ks.statistic)
            ks_pvalue = float(ks.pvalue)
        except Exception:  # pragma: no cover
            ks_stat = None
            ks_pvalue = None

    mw_stat = None
    mw_pvalue = None
    if scipy_stats is not None and n_base >= 2 and n_var >= 2:
        try:
            mw = scipy_stats.mannwhitneyu(arr_base, arr_var, alternative="two-sided")
            mw_stat = float(mw.statistic)
            mw_pvalue = float(mw.pvalue)
        except Exception:  # pragma: no cover
            mw_stat = None
            mw_pvalue = None

    # Jensen-Shannon divergence with smoothing
    try:
        hist_range = (
            float(min(arr_base.min(initial=0), arr_var.min(initial=0))),
            float(max(arr_base.max(initial=0), arr_var.max(initial=0))),
        )
        if hist_range[0] == hist_range[1]:
            js_divergence = 0.0
        else:
            hist_base, bins = np.histogram(arr_base, bins="auto", range=hist_range, density=True)
            hist_var, _ = np.histogram(arr_var, bins=bins, density=True)
            hist_base = hist_base + 1e-12
            hist_var = hist_var + 1e-12
            hist_base /= hist_base.sum()
            hist_var /= hist_var.sum()
            m = 0.5 * (hist_base + hist_var)
            js_divergence = float(0.5 * (np.sum(hist_base * np.log(hist_base / m)) + np.sum(hist_var * np.log(hist_var / m))))
    except Exception:  # pragma: no cover
        js_divergence = None

    return {
        "baseline_samples": n_base,
        "variant_samples": n_var,
        "baseline_mean": mean_base,
        "variant_mean": mean_var,
        "baseline_std": std_base,
        "variant_std": std_var,
        "ks_statistic": ks_stat,
        "ks_pvalue": ks_pvalue,
        "mwu_statistic": mw_stat,
        "mwu_pvalue": mw_pvalue,
        "js_divergence": js_divergence,
    }


def _benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    m = len(p_values)
    if m == 0:
        return []
    sorted_indices = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    prev = 1.0
    for rank, idx in reversed(list(enumerate(sorted_indices, start=1))):
        corrected = p_values[idx] * m / rank
        value = min(corrected, prev)
        adjusted[idx] = min(value, 1.0)
        prev = adjusted[idx]
    return adjusted


__all__ = [
    "ScoreExtractorPlugin",
    "ScoreStatsAggregator",
    "ScoreDeltaBaselinePlugin",
    "ScoreSignificanceBaselinePlugin",
    "ScoreBayesianBaselinePlugin",
    "ScoreRecommendationAggregator",
    "ScoreAgreementAggregator",
    "ScorePowerAggregator",
    "ScoreDistributionAggregator",
    "ScoreCliffsDeltaPlugin",
    "ScoreAssumptionsBaselinePlugin",
    "ScorePracticalBaselinePlugin",
    "ScoreVariantRankingAggregator",
]
