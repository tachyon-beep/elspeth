from __future__ import annotations

import math

from elspeth.plugins.experiments._stats_helpers import (
    _benjamini_hochberg,
    _calculate_cliffs_delta,
    _collect_paired_scores_by_criterion,
    _collect_scores_by_criterion,
    _compute_bayesian_summary,
    _compute_distribution_shift,
    _compute_significance,
    _create_score_extractor_factory,
    krippendorff_alpha,
)


def test_collect_scores_and_pairs():
    payload = {
        "results": [
            {"metrics": {"scores": {"acc": 0.9, "f1": 0.8}}},
            {"metrics": {"scores": {"acc": 0.7, "f1": None}}},
            {"metrics": {"scores": {"acc": float("nan")}}},
        ]
    }
    by_name = _collect_scores_by_criterion(payload)
    assert by_name["acc"] == [0.9, 0.7]
    assert "f1" in by_name

    baseline = {"results": [{"metrics": {"scores": {"acc": 0.9}}}, {"metrics": {"scores": {"acc": 0.8}}}]}
    variant = {"results": [{"metrics": {"scores": {"acc": 0.92}}}, {"metrics": {"scores": {"acc": 0.81}}}]}
    pairs = _collect_paired_scores_by_criterion(baseline, variant)
    assert pairs["acc"] == [(0.9, 0.92), (0.8, 0.81)]


def test_effect_size_and_significance():
    delta, label = _calculate_cliffs_delta([1, 2, 3], [3, 4, 5])
    assert label in {"small", "medium", "large", "negligible"}
    sig = _compute_significance([1, 2, 3], [2, 3, 4])
    assert set(sig.keys()) >= {"baseline_mean", "variant_mean", "p_value"}
    # Exercise equal_var branch
    sig2 = _compute_significance([1, 2, 3], [2, 3, 4], equal_var=True)
    assert sig2["baseline_samples"] == 3


def test_bayesian_and_distribution():
    bayes = _compute_bayesian_summary([1, 2, 3], [2, 3, 4], 0.05)
    assert set(bayes.keys()) >= {"credible_interval", "prob_variant_gt_baseline"}
    shift = _compute_distribution_shift([1, 2, 3, 4], [2, 3, 4, 5])
    assert set(shift.keys()) >= {"ks_statistic", "mwu_pvalue", "js_divergence"}


def test_bh_correction_and_factory():
    adj = _benjamini_hochberg([0.01, 0.02, 0.5, 0.8])
    assert len(adj) == 4

    cfg = _create_score_extractor_factory(
        {
            "key": "scores",
            "parse_json_content": False,
            "allow_missing": True,
            "threshold_mode": "greater",
            "flag_field": "flag",
        }
    )
    assert cfg["key"] == "scores"


def test_krippendorff_alpha_variants():
    import numpy as np

    # Perfect agreement (interval) -> alpha ~ 1.0
    arr = np.array([[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]], dtype=float)
    a_int = krippendorff_alpha(arr, level="interval")
    assert a_int is not None and a_int > 0.99

    # Nominal: two categories, some disagreement
    arr_nom = np.array([[1, 1, 2], [2, 2, 2], [1, 2, 1]], dtype=float)
    a_nom = krippendorff_alpha(arr_nom, level="nominal")
    assert a_nom is not None and -1.0 <= a_nom <= 1.0

    # Ordinal (rank-based fallback) should be within bounds
    arr_ord = np.array([[1, 2, 3], [2, 2, 2], [1, 3, np.nan]], dtype=float)
    a_ord = krippendorff_alpha(arr_ord, level="ordinal")
    assert a_ord is not None and -1.0 <= a_ord <= 1.0
