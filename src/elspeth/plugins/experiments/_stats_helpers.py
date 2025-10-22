"""Internal statistical helper functions shared across experiment plugins.

These functions are used by multiple aggregation and baseline plugins for
statistical computations. They are prefixed with underscore to indicate
they are internal implementation details.
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Mapping, Sequence

import numpy as np
from scipy import stats as scipy_stats


def _create_score_extractor_factory(options: dict[str, Any]) -> dict[str, Any]:
    """Factory helper for score extractor plugin creation."""
    from elspeth.core.validation.base import ConfigurationError

    if "key" not in options:
        raise ConfigurationError("key is required for score_extractor plugin")
    if "parse_json_content" not in options:
        raise ConfigurationError("parse_json_content is required for score_extractor plugin")
    if "allow_missing" not in options:
        raise ConfigurationError("allow_missing is required for score_extractor plugin")
    if "threshold_mode" not in options:
        raise ConfigurationError("threshold_mode is required for score_extractor plugin")
    if "flag_field" not in options:
        raise ConfigurationError("flag_field is required for score_extractor plugin")

    return {
        "key": options["key"],
        "criteria": options.get("criteria"),
        "parse_json_content": options["parse_json_content"],
        "allow_missing": options["allow_missing"],
        "threshold": options.get("threshold"),
        "threshold_mode": options["threshold_mode"],
        "flag_field": options["flag_field"],
    }


def _collect_scores_by_criterion(payload: Mapping[str, Any]) -> dict[str, list[float]]:
    """Collect all scores by criterion name from experiment results."""
    scores_by_name: dict[str, list[float]] = {}
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
) -> dict[str, list[tuple[float, float]]]:
    """Collect paired (baseline, variant) scores by criterion for matched comparison."""
    baseline_results = baseline.get("results", []) or []
    variant_results = variant.get("results", []) or []
    count = min(len(baseline_results), len(variant_results))
    pairs: dict[str, list[tuple[float, float]]] = {}
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
    """Compute Cliff's Delta effect size and interpret magnitude.

    Returns:
        Tuple of (delta, interpretation) where delta is in [-1, 1] and
        interpretation is one of: negligible, small, medium, large, no_data
    """
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
) -> dict[str, Any]:
    """Compute t-test statistics and effect size for two samples.

    Args:
        baseline: Baseline sample scores
        variant: Variant sample scores
        equal_var: Assume equal variances (pooled t-test)

    Returns:
        Dictionary with keys: baseline_mean, variant_mean, mean_difference,
        baseline_std, variant_std, baseline_samples, variant_samples,
        effect_size, t_stat, degrees_of_freedom, p_value
    """
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

    df: float | None = None

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
    if t_stat is not None and df is not None and scipy_stats is not None:
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
) -> dict[str, Any]:
    """Compute Bayesian credible interval and probability that variant > baseline.

    Args:
        baseline: Baseline sample scores
        variant: Variant sample scores
        alpha: Significance level for credible interval (e.g., 0.05 for 95% CI)

    Returns:
        Dictionary with keys: baseline_mean, variant_mean, mean_difference,
        std_error, degrees_of_freedom, prob_variant_gt_baseline, credible_interval
    """
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
) -> dict[str, Any]:
    """Compute distribution shift metrics (KS test, Mann-Whitney U, JS divergence).

    Args:
        baseline: Baseline sample scores
        variant: Variant sample scores

    Returns:
        Dictionary with keys: baseline_samples, variant_samples, baseline_mean,
        variant_mean, baseline_std, variant_std, ks_statistic, ks_pvalue,
        mwu_statistic, mwu_pvalue, js_divergence
    """
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
    """Apply Benjamini-Hochberg FDR correction to p-values.

    Args:
        p_values: Sequence of p-values to correct

    Returns:
        List of adjusted p-values (same length as input)
    """
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


def _krippendorff_alpha_interval(data: "np.ndarray") -> float | None:
    """Compute Krippendorff's alpha for interval data with missing values.

    Args:
        data: 2D array of shape (n_items, n_raters) with NaN for missing ratings.

    Returns:
        Alpha in [-inf, 1], or None if insufficient data.

    Notes:
        This implementation follows the pairwise-disagreement formulation for
        interval metrics. It computes observed disagreement (Do) as the
        average of squared differences among available rater pairs per item,
        and expected disagreement (De) as the average of squared differences
        among all value pairs in the pooled sample. Missing values (NaN) are
        ignored. For degenerate cases (no variance), returns 1.0 if all
        observed values are identical, else None.
    """
    if data.ndim != 2:
        return None
    x = np.asarray(data, dtype=float)
    # Require at least two items for a meaningful estimate
    if x.shape[0] < 2:
        return None
    v = x[~np.isnan(x)]
    m = v.size
    if m < 2:
        return None

    # Helper: mean of pairwise squared differences for a 1D vector
    def _pairwise_sqdiff_mean(vec: "np.ndarray") -> float:
        n = vec.size
        if n < 2:
            return np.nan
        # O(n^2) is acceptable for small analytics matrices
        s = 0.0
        cnt = 0
        for i in range(n):
            vi = vec[i]
            for j in range(i + 1, n):
                d = vi - vec[j]
                s += d * d
                cnt += 1
        return s / cnt

    De = _pairwise_sqdiff_mean(v)
    if not np.isfinite(De) or De <= 0:
        # No variance across pooled values: perfect agreement if all equal
        return 1.0 if np.allclose(v, v.mean()) else None

    s_do = 0.0
    c_do = 0
    for row in x:
        r = row[~np.isnan(row)]
        n = r.size
        if n >= 2:
            s = 0.0
            cnt = 0
            for i in range(n):
                ri = r[i]
                for j in range(i + 1, n):
                    d = ri - r[j]
                    s += d * d
                    cnt += 1
            s_do += s
            c_do += cnt

    if c_do == 0:
        return None
    Do = s_do / c_do
    return float(1.0 - (Do / De))


def _krippendorff_alpha_nominal(data: "np.ndarray") -> float | None:
    """Krippendorff's alpha for nominal (categorical) data.

    Uses 0/1 disagreement (1 if unequal labels). Missing values (NaN) ignored.
    """
    if data.ndim != 2:
        return None
    x = np.asarray(data)
    if x.shape[0] < 2:
        return None

    # Flatten non-NaN values to compute expected disagreement from category proportions
    v = x[~np.isnan(x)]
    if v.size < 2:
        return None

    # Map categories to integers (preserve floats by casting to object for hashing if needed)
    # For nominal, equality matters only.
    # Convert to Python objects to allow hashing of strings/ints uniformly
    v_obj = v.astype(object)
    # Frequencies
    unique, counts = np.unique(v_obj, return_counts=True)
    n = v_obj.size
    p = counts.astype(float) / float(n)
    De = float(1.0 - np.sum(p * p))
    if not np.isfinite(De) or De <= 0:
        return 1.0 if counts.size == 1 else None

    # Observed disagreement: average 0/1 inequality over rater pairs per item, weighted by pair counts
    s_do = 0.0
    c_do = 0
    for row in x:
        r = row[~np.isnan(row)]
        m = r.size
        if m >= 2:
            # Count unequal pairs
            unequal = 0
            total = m * (m - 1) // 2
            r_obj = r.astype(object)
            for i in range(m):
                ri = r_obj[i]
                for j in range(i + 1, m):
                    unequal += 0 if ri == r_obj[j] else 1
            s_do += unequal
            c_do += total
    if c_do == 0:
        return None
    Do = s_do / c_do
    return float(1.0 - (Do / De))


def krippendorff_alpha(data: "np.ndarray", level: str = "interval") -> float | None:
    """Compute Krippendorff's alpha for given measurement level.

    Args:
        data: 2D array (n_items, n_raters) with NaN for missing
        level: one of {"interval", "nominal", "ordinal"}

    Returns:
        Alpha or None if insufficient data.

    Notes:
        - "ordinal" falls back to rank-encoding then uses interval alpha.
          For many practical cases this is acceptable, though not identical
          to the cumulative-disagreement definition.
    """
    level = level.lower()
    if level == "interval":
        return _krippendorff_alpha_interval(data)
    if level == "nominal":
        return _krippendorff_alpha_nominal(data)
    if level == "ordinal":
        # Approximate ordinal alpha:
        # Rank-encode category values on the pooled set, then use interval alpha.
        # Note: This rank-transform approach is an approximation. For true ordinal
        # Krippendorff's α using cumulative distributions, see Krippendorff (2013).
        # This simplification is acceptable for many practical use cases where
        # ordinal categories are approximately evenly spaced.
        x = np.asarray(data, dtype=float)
        # Build ranks on pooled unique values (ignoring NaN)
        vals = x[~np.isnan(x)]
        if vals.size < 2:
            return None
        uniq = np.unique(vals)
        # Map each unique observed value to an ordinal rank
        mapping: dict[float, float] = {float(v): float(i) for i, v in enumerate(uniq)}
        def _map_val(val: float) -> float:
            return float("nan") if np.isnan(val) else mapping.get(float(val), float("nan"))
        xr = np.vectorize(_map_val, otypes=[float])(x)
        return _krippendorff_alpha_interval(np.asarray(xr, dtype=float))
    raise ValueError("level must be one of: interval, nominal, ordinal")


# Public aliases used by plugins/tests
krippendorff_alpha_interval = _krippendorff_alpha_interval
