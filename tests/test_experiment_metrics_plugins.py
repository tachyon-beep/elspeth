import math

import pytest

from elspeth.core.experiments.plugin_registry import create_aggregation_plugin, create_baseline_plugin, create_row_plugin


@pytest.mark.parametrize(
    "response,expected",
    [
        ({"metrics": {"score": 4}}, 4.0),
        ({"metrics": {"score": "3.5"}}, 3.5),
        ({"content": '{"score": 2.25}'}, 2.25),
        ({"content": "not json"}, math.nan),
    ],
)
def test_score_extractor_basic(response, expected):
    plugin = create_row_plugin({"name": "score_extractor", "security_level": "official"})
    derived = plugin.process_row({}, {"crit": response})
    scores = derived["scores"]
    assert "crit" in scores
    if math.isnan(expected):
        assert math.isnan(scores["crit"])
    else:
        assert scores["crit"] == pytest.approx(expected)


def test_score_extractor_threshold_flag():
    plugin = create_row_plugin(
        {
            "name": "score_extractor",
            "security_level": "official",
            "options": {"threshold": 0.7, "threshold_mode": "gte"},
        }
    )
    responses = {
        "crit": {"metrics": {"score": 0.72}},
        "crit2": {"metrics": {"score": 0.65}},
    }

    derived = plugin.process_row({}, responses)
    assert derived["scores"]["crit"] == pytest.approx(0.72)
    assert derived["score_flags"]["crit"] is True
    assert derived["score_flags"]["crit2"] is False


def test_score_extractor_allow_missing():
    plugin = create_row_plugin(
        {
            "name": "score_extractor",
            "security_level": "official",
            "options": {"allow_missing": True},
        }
    )
    derived = plugin.process_row({}, {"crit": {"content": "{}"}})
    assert derived == {}


def test_score_stats_aggregator():
    row_plugin = create_row_plugin({"name": "score_extractor", "security_level": "official", "options": {"threshold": 0.7}})
    responses = [
        {"critA": {"metrics": {"score": 0.8}}},
        {"critA": {"metrics": {"score": 0.6}}},
        {"critA": {"metrics": {"score": "0.9"}}},
    ]
    records = []
    for resp in responses:
        metrics = row_plugin.process_row({}, resp)
        records.append({"metrics": metrics})

    agg_plugin = create_aggregation_plugin({"name": "score_stats", "security_level": "official"})
    summary = agg_plugin.finalize(records)
    crit_summary = summary["criteria"]["critA"]

    assert crit_summary["count"] == 3
    assert crit_summary["passes"] == 2  # threshold flag from extractor
    assert crit_summary["pass_rate"] == pytest.approx(2 / 3)
    assert crit_summary["mean"] == pytest.approx((0.8 + 0.6 + 0.9) / 3)


def test_score_delta_baseline_plugin():
    agg_plugin = create_aggregation_plugin({"name": "score_stats", "security_level": "official"})
    baseline_payload = {
        "aggregates": {
            "score_stats": agg_plugin.finalize(
                [
                    {"metrics": {"scores": {"crit": 0.5}}},
                ]
            )
        }
    }
    variant_payload = {
        "aggregates": {
            "score_stats": agg_plugin.finalize(
                [
                    {"metrics": {"scores": {"crit": 0.8}}},
                ]
            )
        }
    }

    plugin = create_baseline_plugin({"name": "score_delta", "security_level": "official"})
    delta = plugin.compare(baseline_payload, variant_payload)
    assert delta["crit"] == pytest.approx(0.8 - 0.5)


def test_score_recommendation_aggregator():
    row_plugin = create_row_plugin({"name": "score_extractor", "security_level": "official"})
    records = []
    for value in [0.4, 0.6, 0.7, 0.9, 0.85]:
        metrics = row_plugin.process_row({}, {"critA": {"metrics": {"score": value}}})
        records.append({"metrics": metrics})

    rec_plugin = create_aggregation_plugin(
        {
            "name": "score_recommendation",
            "security_level": "official",
            "options": {"min_samples": 3, "improvement_margin": 0.01},
        }
    )
    payload = rec_plugin.finalize(records)

    assert "critA" in payload["recommendation"]
    assert payload["best_criteria"] == "critA"


def test_score_significance_baseline_plugin(monkeypatch):
    import elspeth.plugins.experiments.metrics as metrics_mod

    class DummyT:
        @staticmethod
        def sf(value, df):
            return 0.2  # arbitrary

    monkeypatch.setattr(metrics_mod, "scipy_stats", type("DummyStats", (), {"t": DummyT})())

    baseline_payload = {
        "results": [
            {"metrics": {"scores": {"crit": 0.4}}},
            {"metrics": {"scores": {"crit": 0.5}}},
            {"metrics": {"scores": {"crit": 0.6}}},
        ]
    }
    variant_payload = {
        "results": [
            {"metrics": {"scores": {"crit": 0.7}}},
            {"metrics": {"scores": {"crit": 0.8}}},
            {"metrics": {"scores": {"crit": 0.9}}},
        ]
    }

    plugin = create_baseline_plugin({"name": "score_significance", "security_level": "official"})
    result = plugin.compare(baseline_payload, variant_payload)
    stats = result["crit"]
    assert stats["baseline_samples"] == 3
    assert stats["variant_samples"] == 3
    assert stats["baseline_mean"] == pytest.approx(0.5)
    assert stats["variant_mean"] == pytest.approx(0.8)
    assert stats["effect_size"] is not None
    assert stats["t_stat"] is not None
    assert stats["p_value"] == pytest.approx(0.4)  # since sf returns 0.2 and two-tailed multiplies by 2


def test_score_cliffs_delta():
    plugin = create_baseline_plugin({"name": "score_cliffs_delta", "security_level": "official"})
    baseline = {
        "results": [
            {"metrics": {"scores": {"crit": 1}}},
            {"metrics": {"scores": {"crit": 2}}},
            {"metrics": {"scores": {"crit": 3}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"crit": 4}}},
            {"metrics": {"scores": {"crit": 5}}},
            {"metrics": {"scores": {"crit": 6}}},
        ]
    }
    result = plugin.compare(baseline, variant)
    assert "crit" in result
    delta = result["crit"]["delta"]
    assert delta > 0.0
    assert result["crit"]["interpretation"] in {"small", "medium", "large"}


def test_score_assumptions_baseline_plugin():
    import scipy.stats  # noqa: F401

    plugin = create_baseline_plugin({"name": "score_assumptions", "security_level": "official"})
    baseline = {
        "results": [
            {"metrics": {"scores": {"crit": 3}}},
            {"metrics": {"scores": {"crit": 4}}},
            {"metrics": {"scores": {"crit": 5}}},
            {"metrics": {"scores": {"crit": 4}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"crit": 4}}},
            {"metrics": {"scores": {"crit": 5}}},
            {"metrics": {"scores": {"crit": 6}}},
            {"metrics": {"scores": {"crit": 5}}},
        ]
    }
    result = plugin.compare(baseline, variant)
    entry = result["crit"]
    assert "baseline" in entry and entry["baseline"]["samples"] == 4
    assert "variance" in entry


def test_score_practical_baseline_plugin():
    plugin = create_baseline_plugin(
        {
            "name": "score_practical",
            "security_level": "official",
            "options": {"threshold": 1.0, "success_threshold": 4.0},
        }
    )
    baseline = {
        "results": [
            {"metrics": {"scores": {"crit": 3}}},
            {"metrics": {"scores": {"crit": 4}}},
            {"metrics": {"scores": {"crit": 3}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"crit": 4}}},
            {"metrics": {"scores": {"crit": 5}}},
            {"metrics": {"scores": {"crit": 5}}},
        ]
    }
    result = plugin.compare(baseline, variant)
    stats = result["crit"]
    assert stats["pairs"] == 3
    assert stats["meaningful_change_rate"] > 0
    assert stats["variant_success_rate"] >= stats["baseline_success_rate"]


def test_score_significance_with_adjustments():
    baseline = {
        "results": [
            {"metrics": {"scores": {"crit": 1}}},
            {"metrics": {"scores": {"crit": 2}}},
            {"metrics": {"scores": {"crit": 3}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"crit": 3}}},
            {"metrics": {"scores": {"crit": 4}}},
            {"metrics": {"scores": {"crit": 5}}},
        ]
    }
    plugin = create_baseline_plugin(
        {"name": "score_significance", "security_level": "official", "options": {"adjustment": "bonferroni", "family_size": 10}}
    )
    result = plugin.compare(baseline, variant)
    assert "adjusted_p_value" in result["crit"]


def test_score_variant_ranking():
    aggregator = create_aggregation_plugin(
        {
            "name": "score_variant_ranking",
            "security_level": "official",
            "options": {"threshold": 0.6, "weight_mean": 1.0, "weight_pass": 1.0},
        }
    )
    records = [
        {"metrics": {"score": 0.5}},
        {"metrics": {"score": 0.7}},
        {"metrics": {"score": 0.9}},
        {"metrics": {"scores": {"analysis": 0.8, "prioritization": 0.6}}},
    ]
    summary = aggregator.finalize(records)
    assert summary["samples"] == 4
    assert summary["composite_score"] > 0


def test_score_significance_on_error_skip(monkeypatch):
    import elspeth.plugins.experiments.metrics as metrics_mod

    plugin = metrics_mod.ScoreSignificanceBaselinePlugin(on_error="skip")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(metrics_mod, "_collect_scores_by_criterion", boom)
    assert plugin.compare({"results": []}, {"results": []}) == {}


def test_score_agreement_aggregator(monkeypatch):
    plugin = create_aggregation_plugin({"name": "score_agreement", "security_level": "official"})
    records = []
    values = [
        {"scores": {"critA": 0.6, "critB": 0.65}},
        {"scores": {"critA": 0.7, "critB": 0.75}},
        {"scores": {"critA": 0.8, "critB": 0.78}},
    ]
    for metrics in values:
        records.append({"metrics": metrics})

    # monkeypatch pingouin response
    import elspeth.plugins.experiments.metrics as metrics_mod

    class DummyPingouin:
        @staticmethod
        def krippendorff_alpha(df, reliability_data=True):
            return 0.5

    monkeypatch.setattr(metrics_mod, "pingouin", DummyPingouin())
    result = plugin.finalize(records)
    assert "cronbach_alpha" in result
    assert result["criteria"] == ["critA", "critB"]
    assert result["krippendorff_alpha"] == pytest.approx(0.5)


def test_score_agreement_on_error_skip(monkeypatch):
    import elspeth.plugins.experiments.metrics as metrics_mod

    plugin = metrics_mod.ScoreAgreementAggregator(on_error="skip")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(metrics_mod, "_collect_scores_by_criterion", boom)
    assert plugin.finalize([{}]) == {}


def test_score_bayes_baseline_plugin(monkeypatch):
    import elspeth.plugins.experiments.metrics as metrics_mod

    baseline = {
        "results": [
            {"metrics": {"scores": {"crit": 0.4}}},
            {"metrics": {"scores": {"crit": 0.5}}},
            {"metrics": {"scores": {"crit": 0.6}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"crit": 0.7}}},
            {"metrics": {"scores": {"crit": 0.8}}},
            {"metrics": {"scores": {"crit": 0.9}}},
        ]
    }

    class DummyT:
        @staticmethod
        def cdf(x):
            return 0.2

        @staticmethod
        def ppf(q):
            return 0.5

    class DummyStats:
        @staticmethod
        def t(df, loc=0.0, scale=1.0):
            return DummyT()

    monkeypatch.setattr(metrics_mod, "scipy_stats", DummyStats())

    plugin = create_baseline_plugin({"name": "score_bayes", "security_level": "official", "options": {"credible_interval": 0.9}})
    result = plugin.compare(baseline, variant)
    stats = result["crit"]
    assert stats["prob_variant_gt_baseline"] == pytest.approx(0.8)
    assert len(stats["credible_interval"]) == 2


def test_score_bayes_on_error_skip(monkeypatch):
    import elspeth.plugins.experiments.metrics as metrics_mod

    plugin = metrics_mod.ScoreBayesianBaselinePlugin(on_error="skip")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(metrics_mod, "_collect_scores_by_criterion", boom)
    assert plugin.compare({"results": []}, {"results": []}) == {}


def test_score_power_aggregator(monkeypatch):
    import elspeth.plugins.experiments.metrics as metrics_mod

    records = [
        {"metrics": {"scores": {"crit": 0.6}}},
        {"metrics": {"scores": {"crit": 0.7}}},
        {"metrics": {"scores": {"crit": 0.8}}},
    ]

    class DummyTest:
        def solve_power(self, effect_size=None, alpha=None, power=None, nobs=None, alternative=None):
            if nobs is None:
                return 42
            return 0.75

    monkeypatch.setattr(metrics_mod, "TTestPower", lambda: DummyTest())
    plugin = create_aggregation_plugin(
        {
            "name": "score_power",
            "security_level": "official",
            "options": {"null_mean": 0.5, "alpha": 0.05, "target_power": 0.8},
        }
    )
    result = plugin.finalize(records)
    stats = result["crit"]
    assert stats["required_samples"] == pytest.approx(42)
    assert stats["achieved_power"] == pytest.approx(0.75)


def test_score_power_on_error_skip(monkeypatch):
    import elspeth.plugins.experiments.metrics as metrics_mod

    plugin = metrics_mod.ScorePowerAggregator(on_error="skip")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(metrics_mod, "_collect_scores_by_criterion", boom)
    assert plugin.finalize([{}]) == {}


def test_score_distribution_baseline_plugin(monkeypatch):
    import elspeth.plugins.experiments.metrics as metrics_mod

    baseline = {
        "results": [
            {"metrics": {"scores": {"crit": 0.2}}},
            {"metrics": {"scores": {"crit": 0.3}}},
            {"metrics": {"scores": {"crit": 0.5}}},
        ]
    }
    variant = {
        "results": [
            {"metrics": {"scores": {"crit": 0.8}}},
            {"metrics": {"scores": {"crit": 0.9}}},
            {"metrics": {"scores": {"crit": 0.7}}},
        ]
    }

    class DummyKS:
        statistic = 0.5
        pvalue = 0.01

    class DummyMW:
        statistic = 2.0
        pvalue = 0.02

    class DummyStats:
        @staticmethod
        def ks_2samp(a, b, alternative="two-sided"):
            return DummyKS()

        @staticmethod
        def mannwhitneyu(a, b, alternative="two-sided"):
            return DummyMW()

    monkeypatch.setattr(metrics_mod, "scipy_stats", DummyStats())

    plugin = create_baseline_plugin({"name": "score_distribution", "security_level": "official"})
    result = plugin.compare(baseline, variant)
    stats = result["crit"]
    assert stats["ks_statistic"] == pytest.approx(0.5)
    assert stats["mwu_statistic"] == pytest.approx(2.0)
    assert stats["js_divergence"] >= 0


def test_score_distribution_on_error_skip(monkeypatch):
    import elspeth.plugins.experiments.metrics as metrics_mod

    plugin = metrics_mod.ScoreDistributionAggregator(on_error="skip")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(metrics_mod, "_collect_scores_by_criterion", boom)
    assert plugin.compare({"results": []}, {"results": []}) == {}
