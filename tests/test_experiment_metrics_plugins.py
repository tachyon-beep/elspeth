import math

import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.core.experiments.plugin_registry import create_aggregation_plugin, create_baseline_plugin, create_row_plugin

# Required options for score_extractor plugin (no defaults allowed)
SCORE_EXTRACTOR_REQUIRED = {
    "key": "score",
    "parse_json_content": True,
    "allow_missing": False,
    "threshold_mode": "gte",
    "flag_field": "score_flags",
}


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
    plugin = create_row_plugin(
        {
            "name": "score_extractor",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": SCORE_EXTRACTOR_REQUIRED,
        }
    )
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
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {**SCORE_EXTRACTOR_REQUIRED, "threshold": 0.7},
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
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {**SCORE_EXTRACTOR_REQUIRED, "allow_missing": True},
        }
    )
    derived = plugin.process_row({}, {"crit": {"content": "{}"}})
    assert derived == {}


def test_score_stats_aggregator():
    row_plugin = create_row_plugin(
        {
            "name": "score_extractor",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {**SCORE_EXTRACTOR_REQUIRED, "threshold": 0.7},
        }
    )
    responses = [
        {"critA": {"metrics": {"score": 0.8}}},
        {"critA": {"metrics": {"score": 0.6}}},
        {"critA": {"metrics": {"score": "0.9"}}},
    ]
    records = []
    for resp in responses:
        metrics = row_plugin.process_row({}, resp)
        records.append({"metrics": metrics})

    agg_plugin = create_aggregation_plugin({"name": "score_stats", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    summary = agg_plugin.finalize(records)
    crit_summary = summary["criteria"]["critA"]

    assert crit_summary["count"] == 3
    assert crit_summary["passes"] == 2  # threshold flag from extractor
    assert crit_summary["pass_rate"] == pytest.approx(2 / 3)
    assert crit_summary["mean"] == pytest.approx((0.8 + 0.6 + 0.9) / 3)


def test_score_delta_baseline_plugin():
    agg_plugin = create_aggregation_plugin({"name": "score_stats", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
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

    plugin = create_baseline_plugin({"name": "score_delta", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    delta = plugin.compare(baseline_payload, variant_payload)
    assert delta["crit"] == pytest.approx(0.8 - 0.5)


def test_score_recommendation_aggregator():
    row_plugin = create_row_plugin(
        {"name": "score_extractor", "security_level": "OFFICIAL", "determinism_level": "guaranteed", "options": SCORE_EXTRACTOR_REQUIRED}
    )
    records = []
    for value in [0.4, 0.6, 0.7, 0.9, 0.85]:
        metrics = row_plugin.process_row({}, {"critA": {"metrics": {"score": value}}})
        records.append({"metrics": metrics})

    rec_plugin = create_aggregation_plugin(
        {
            "name": "score_recommendation",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"min_samples": 3, "improvement_margin": 0.01},
        }
    )
    payload = rec_plugin.finalize(records)

    assert "critA" in payload["recommendation"]
    assert payload["best_criteria"] == "critA"


def test_score_significance_baseline_plugin(monkeypatch):
    import elspeth.plugins.experiments._stats_helpers as stats_helpers

    class DummyT:
        @staticmethod
        def sf(value, df):
            return 0.2  # arbitrary

    monkeypatch.setattr(stats_helpers, "scipy_stats", type("DummyStats", (), {"t": DummyT})())

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

    plugin = create_baseline_plugin({"name": "score_significance", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
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
    plugin = create_baseline_plugin({"name": "score_cliffs_delta", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
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
    plugin = create_baseline_plugin({"name": "score_assumptions", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
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
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
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
        {
            "name": "score_significance",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"adjustment": "bonferroni", "family_size": 10},
        }
    )
    result = plugin.compare(baseline, variant)
    assert "adjusted_p_value" in result["crit"]


def test_score_variant_ranking():
    aggregator = create_aggregation_plugin(
        {
            "name": "score_variant_ranking",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
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
    import elspeth.plugins.experiments._stats_helpers as stats_helpers
    from elspeth.plugins.experiments.baseline.score_significance import ScoreSignificanceBaselinePlugin

    plugin = ScoreSignificanceBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        on_error="skip"
    )

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(stats_helpers, "_collect_scores_by_criterion", boom)
    assert plugin.compare({"results": []}, {"results": []}) == {}


def test_score_agreement_aggregator(monkeypatch):
    plugin = create_aggregation_plugin({"name": "score_agreement", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    records = []
    values = [
        {"scores": {"critA": 0.6, "critB": 0.65}},
        {"scores": {"critA": 0.7, "critB": 0.75}},
        {"scores": {"critA": 0.8, "critB": 0.78}},
    ]
    for metrics in values:
        records.append({"metrics": metrics})

    # Validate Krippendorff's alpha via in-tree implementation
    from elspeth.plugins.experiments._stats_helpers import krippendorff_alpha_interval
    import numpy as np

    result = plugin.finalize(records)
    assert "cronbach_alpha" in result
    assert result["criteria"] == ["critA", "critB"]
    # Build array to compute expected alpha (rows=items, cols=criteria)
    arr = np.array([[0.6, 0.65], [0.7, 0.75], [0.8, 0.78]], dtype=float)
    expected_alpha = krippendorff_alpha_interval(arr)
    if expected_alpha is not None:
        assert result["krippendorff_alpha"] == pytest.approx(expected_alpha)
    else:
        assert result["krippendorff_alpha"] is None


def test_score_agreement_on_error_skip(monkeypatch):
    import elspeth.plugins.experiments._stats_helpers as stats_helpers
    from elspeth.plugins.experiments.aggregators.score_agreement import ScoreAgreementAggregator

    plugin = ScoreAgreementAggregator(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        on_error="skip"
    )

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(stats_helpers, "_collect_scores_by_criterion", boom)
    assert plugin.finalize([{}]) == {}


def test_score_bayes_baseline_plugin(monkeypatch):
    import elspeth.plugins.experiments._stats_helpers as stats_helpers

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

    monkeypatch.setattr(stats_helpers, "scipy_stats", DummyStats())

    plugin = create_baseline_plugin(
        {"name": "score_bayes", "security_level": "OFFICIAL", "determinism_level": "guaranteed", "options": {"credible_interval": 0.9}}
    )
    result = plugin.compare(baseline, variant)
    stats = result["crit"]
    assert stats["prob_variant_gt_baseline"] == pytest.approx(0.8)
    assert len(stats["credible_interval"]) == 2


def test_score_bayes_on_error_skip(monkeypatch):
    import elspeth.plugins.experiments._stats_helpers as stats_helpers
    from elspeth.plugins.experiments.baseline.score_bayesian import ScoreBayesianBaselinePlugin

    plugin = ScoreBayesianBaselinePlugin(security_level=SecurityLevel.OFFICIAL, on_error="skip")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(stats_helpers, "_collect_scores_by_criterion", boom)
    assert plugin.compare({"results": []}, {"results": []}) == {}


def test_score_power_aggregator(monkeypatch):
    import elspeth.plugins.experiments.aggregators.score_power as score_power_mod

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

    monkeypatch.setattr(score_power_mod, "TTestPower", DummyTest)
    plugin = create_aggregation_plugin(
        {
            "name": "score_power",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"null_mean": 0.5, "alpha": 0.05, "target_power": 0.8},
        }
    )
    result = plugin.finalize(records)
    stats = result["crit"]
    assert stats["required_samples"] == pytest.approx(42)
    assert stats["achieved_power"] == pytest.approx(0.75)


def test_score_power_on_error_skip(monkeypatch):
    import elspeth.plugins.experiments._stats_helpers as stats_helpers
    from elspeth.plugins.experiments.aggregators.score_power import ScorePowerAggregator

    plugin = ScorePowerAggregator(on_error="skip")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(stats_helpers, "_collect_scores_by_criterion", boom)
    assert plugin.finalize([{}]) == {}


def test_score_distribution_baseline_plugin(monkeypatch):
    import elspeth.plugins.experiments._stats_helpers as stats_helpers

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

    monkeypatch.setattr(stats_helpers, "scipy_stats", DummyStats())

    plugin = create_baseline_plugin({"name": "score_distribution", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    result = plugin.compare(baseline, variant)
    stats = result["crit"]
    assert stats["ks_statistic"] == pytest.approx(0.5)
    assert stats["mwu_statistic"] == pytest.approx(2.0)
    assert stats["js_divergence"] >= 0


def test_score_distribution_on_error_skip(monkeypatch):
    import elspeth.plugins.experiments._stats_helpers as stats_helpers
    from elspeth.plugins.experiments.baseline.score_distribution import ScoreDistributionAggregator

    plugin = ScoreDistributionAggregator(security_level=SecurityLevel.OFFICIAL, on_error="skip")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(stats_helpers, "_collect_scores_by_criterion", boom)
    assert plugin.compare({"results": []}, {"results": []}) == {}


def test_cost_summary_aggregator():
    plugin = create_aggregation_plugin({"name": "cost_summary", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    records = [
        {"metrics": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.005}},
        {"metrics": {"prompt_tokens": 150, "completion_tokens": 75, "cost": 0.0075}},
        {"metrics": {"prompt_tokens": 120, "completion_tokens": 60, "cost": 0.006}},
    ]

    result = plugin.finalize(records)

    assert result["total_requests"] == 3
    assert result["requests_with_cost"] == 3
    assert result["prompt_tokens"]["total"] == 370
    assert result["prompt_tokens"]["mean"] == pytest.approx(370 / 3)
    assert result["prompt_tokens"]["min"] == 100
    assert result["prompt_tokens"]["max"] == 150
    assert result["completion_tokens"]["total"] == 185
    assert result["cost"]["total"] == pytest.approx(0.0185)
    assert result["cost"]["mean"] == pytest.approx(0.0185 / 3)


def test_cost_summary_aggregator_partial_data():
    plugin = create_aggregation_plugin({"name": "cost_summary", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    records = [
        {"metrics": {"prompt_tokens": 100}},
        {"metrics": {"completion_tokens": 50}},
        {"metrics": {"cost": 0.005}},
        {"metrics": {}},
    ]

    result = plugin.finalize(records)

    assert result["total_requests"] == 4
    assert result["requests_with_cost"] == 1
    assert result["prompt_tokens"]["total"] == 100
    assert result["completion_tokens"]["total"] == 50
    assert result["cost"]["total"] == pytest.approx(0.005)


def test_cost_summary_aggregator_empty():
    plugin = create_aggregation_plugin({"name": "cost_summary", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    result = plugin.finalize([])
    assert result == {}


def test_latency_summary_aggregator():
    plugin = create_aggregation_plugin({"name": "latency_summary", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    records = [
        {"metrics": {"latency_seconds": 0.5}},
        {"metrics": {"latency_seconds": 1.2}},
        {"metrics": {"latency_seconds": 0.8}},
        {"metrics": {"latency_seconds": 2.0}},
        {"metrics": {"latency_seconds": 0.6}},
    ]

    result = plugin.finalize(records)

    assert result["total_requests"] == 5
    assert result["requests_with_latency"] == 5
    assert result["latency_seconds"]["mean"] == pytest.approx(1.02)
    assert result["latency_seconds"]["median"] == pytest.approx(0.8)
    assert result["latency_seconds"]["min"] == pytest.approx(0.5)
    assert result["latency_seconds"]["max"] == pytest.approx(2.0)
    # Percentiles with small samples use interpolation
    assert result["latency_seconds"]["p95"] > result["latency_seconds"]["median"]
    assert result["latency_seconds"]["p99"] > result["latency_seconds"]["p95"]


def test_latency_summary_aggregator_missing_data():
    plugin = create_aggregation_plugin({"name": "latency_summary", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    records = [
        {"metrics": {"latency_seconds": 0.5}},
        {"metrics": {}},
        {"metrics": {"latency_seconds": 1.2}},
    ]

    result = plugin.finalize(records)

    assert result["total_requests"] == 3
    assert result["requests_with_latency"] == 2
    assert result["latency_seconds"]["mean"] == pytest.approx(0.85)


def test_latency_summary_aggregator_no_latency():
    plugin = create_aggregation_plugin({"name": "latency_summary", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})
    records = [
        {"metrics": {}},
        {"metrics": {}},
    ]

    result = plugin.finalize(records)

    assert result["total_requests"] == 2
    assert result["requests_with_latency"] == 0
    assert "latency_seconds" not in result


def test_cost_summary_on_error_skip(monkeypatch):
    from elspeth.plugins.experiments.aggregators.cost_summary import CostSummaryAggregator

    plugin = CostSummaryAggregator(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        on_error="skip"
    )

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    plugin._finalize_impl = boom
    assert plugin.finalize([{}]) == {}


def test_latency_summary_on_error_skip(monkeypatch):
    from elspeth.plugins.experiments.aggregators.latency_summary import LatencySummaryAggregator

    plugin = LatencySummaryAggregator(
        security_level=SecurityLevel.UNOFFICIAL,
        allow_downgrade=True,
        on_error="skip"
    )

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    plugin._finalize_impl = boom
    assert plugin.finalize([{}]) == {}


def test_rationale_analysis_basic():
    """Test basic rationale analysis with rationales in metrics."""
    plugin = create_aggregation_plugin({"name": "rationale_analysis", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})

    records = [
        {
            "responses": {"crit": {"metrics": {"rationale": "This is clearly excellent work.", "score": 5}}},
            "metrics": {"scores": {"crit": 5.0}},
        },
        {
            "responses": {"crit": {"metrics": {"rationale": "The quality seems somewhat lacking.", "score": 2}}},
            "metrics": {"scores": {"crit": 2.0}},
        },
        {
            "responses": {"crit": {"metrics": {"rationale": "Good performance overall.", "score": 4}}},
            "metrics": {"scores": {"crit": 4.0}},
        },
    ]

    result = plugin.finalize(records)

    assert "criteria" in result
    assert "overall" in result
    assert "crit" in result["criteria"]

    crit_stats = result["criteria"]["crit"]
    assert crit_stats["count"] == 3
    assert crit_stats["avg_length_chars"] > 0
    assert crit_stats["avg_length_words"] > 0
    assert "low_score_keywords" in crit_stats
    assert "high_score_keywords" in crit_stats
    assert "confidence_indicators" in crit_stats

    overall = result["overall"]
    assert overall["total_rationales"] == 3
    assert overall["avg_length_chars"] > 0


def test_rationale_analysis_from_json_content():
    """Test rationale extraction from JSON content."""
    plugin = create_aggregation_plugin({"name": "rationale_analysis", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})

    records = [
        {
            "responses": {"crit": {"content": '{"rationale": "Excellent work", "score": 5}'}},
            "metrics": {"scores": {"crit": 5.0}},
        },
        {
            "responses": {"crit": {"content": '{"rationale": "Poor quality", "score": 1}'}},
            "metrics": {"scores": {"crit": 1.0}},
        },
    ]

    result = plugin.finalize(records)

    assert result["criteria"]["crit"]["count"] == 2
    assert len(result["criteria"]["crit"]["high_score_keywords"]) > 0
    assert len(result["criteria"]["crit"]["low_score_keywords"]) > 0


def test_rationale_analysis_keyword_filtering():
    """Test that stop words and short words are filtered."""
    plugin = create_aggregation_plugin(
        {
            "name": "rationale_analysis",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"min_word_length": 4},
        }
    )

    records = [
        {
            "responses": {
                "crit": {
                    "metrics": {
                        "rationale": "The quality is excellent and comprehensive enough for production use.",
                        "score": 5,
                    }
                }
            },
            "metrics": {"scores": {"crit": 5.0}},
        }
    ]

    result = plugin.finalize(records)

    # Check that short words like "is" and "and" are not in keywords
    crit_stats = result["criteria"]["crit"]
    high_keywords = [kw["word"] for kw in crit_stats["high_score_keywords"]]
    assert "the" not in high_keywords
    assert "and" not in high_keywords
    assert "is" not in high_keywords
    # Should have longer words
    assert any(len(word) >= 4 for word in high_keywords)


def test_rationale_analysis_confidence_detection():
    """Test confidence indicator detection."""
    plugin = create_aggregation_plugin({"name": "rationale_analysis", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})

    records = [
        {
            "responses": {"crit": {"metrics": {"rationale": "This is clearly and definitely excellent.", "score": 5}}},
            "metrics": {"scores": {"crit": 5.0}},
        },
        {
            "responses": {"crit": {"metrics": {"rationale": "Maybe this is somewhat acceptable.", "score": 3}}},
            "metrics": {"scores": {"crit": 3.0}},
        },
        {
            "responses": {"crit": {"metrics": {"rationale": "This seems likely to be good.", "score": 4}}},
            "metrics": {"scores": {"crit": 4.0}},
        },
    ]

    result = plugin.finalize(records)

    confidence = result["criteria"]["crit"]["confidence_indicators"]
    assert "high_confidence_rate" in confidence
    assert "low_confidence_rate" in confidence
    assert "hedge_rate" in confidence
    # At least one should have high confidence words
    assert confidence["high_confidence_rate"] > 0
    # At least one should have low confidence words
    assert confidence["low_confidence_rate"] > 0
    # At least one should have hedging words
    assert confidence["hedge_rate"] > 0


def test_rationale_analysis_length_score_correlation():
    """Test length-score correlation computation."""
    plugin = create_aggregation_plugin({"name": "rationale_analysis", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})

    # Create records where longer rationales correlate with higher scores
    records = [
        {
            "responses": {"crit": {"metrics": {"rationale": "Short", "score": 1}}},
            "metrics": {"scores": {"crit": 1.0}},
        },
        {
            "responses": {"crit": {"metrics": {"rationale": "Longer rationale here", "score": 3}}},
            "metrics": {"scores": {"crit": 3.0}},
        },
        {
            "responses": {"crit": {"metrics": {"rationale": "Much longer rationale with more detailed explanation", "score": 5}}},
            "metrics": {"scores": {"crit": 5.0}},
        },
    ]

    result = plugin.finalize(records)

    corr = result["criteria"]["crit"]["length_score_correlation"]
    assert corr is not None
    # Should show positive correlation
    assert corr > 0


def test_rationale_analysis_multiple_criteria():
    """Test analysis across multiple criteria."""
    plugin = create_aggregation_plugin({"name": "rationale_analysis", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})

    records = [
        {
            "responses": {
                "analysis": {"metrics": {"rationale": "Good analysis", "score": 4}},
                "prioritization": {"metrics": {"rationale": "Excellent prioritization", "score": 5}},
            },
            "metrics": {"scores": {"analysis": 4.0, "prioritization": 5.0}},
        },
        {
            "responses": {
                "analysis": {"metrics": {"rationale": "Weak analysis", "score": 2}},
                "prioritization": {"metrics": {"rationale": "Poor prioritization", "score": 2}},
            },
            "metrics": {"scores": {"analysis": 2.0, "prioritization": 2.0}},
        },
    ]

    result = plugin.finalize(records)

    assert "analysis" in result["criteria"]
    assert "prioritization" in result["criteria"]
    assert result["criteria"]["analysis"]["count"] == 2
    assert result["criteria"]["prioritization"]["count"] == 2
    assert result["overall"]["total_rationales"] == 4


def test_rationale_analysis_criteria_filter():
    """Test filtering to specific criteria."""
    plugin = create_aggregation_plugin(
        {
            "name": "rationale_analysis",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"criteria": ["analysis"]},
        }
    )

    records = [
        {
            "responses": {
                "analysis": {"metrics": {"rationale": "Good analysis", "score": 4}},
                "prioritization": {"metrics": {"rationale": "Excellent prioritization", "score": 5}},
            },
            "metrics": {"scores": {"analysis": 4.0, "prioritization": 5.0}},
        }
    ]

    result = plugin.finalize(records)

    assert "analysis" in result["criteria"]
    assert "prioritization" not in result["criteria"]
    assert result["overall"]["total_rationales"] == 1


def test_rationale_analysis_top_keywords_limit():
    """Test limiting top keywords."""
    plugin = create_aggregation_plugin(
        {
            "name": "rationale_analysis",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"top_keywords": 3},
        }
    )

    records = [
        {
            "responses": {
                "crit": {
                    "metrics": {
                        "rationale": "Excellent outstanding superb magnificent wonderful terrific fantastic amazing great good",
                        "score": 5,
                    }
                }
            },
            "metrics": {"scores": {"crit": 5.0}},
        }
    ]

    result = plugin.finalize(records)

    high_keywords = result["criteria"]["crit"]["high_score_keywords"]
    assert len(high_keywords) <= 3
    for kw in high_keywords:
        assert "word" in kw
        assert "count" in kw


def test_rationale_analysis_missing_rationales():
    """Test handling of missing rationales."""
    plugin = create_aggregation_plugin({"name": "rationale_analysis", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})

    records = [
        {
            "responses": {"crit": {"metrics": {"score": 4}}},  # No rationale
            "metrics": {"scores": {"crit": 4.0}},
        },
        {
            "responses": {"crit": {"content": '{"score": 3}'}},  # No rationale in JSON
            "metrics": {"scores": {"crit": 3.0}},
        },
    ]

    result = plugin.finalize(records)

    # Should return empty structure when no rationales found
    assert result["overall"]["total_rationales"] == 0


def test_rationale_analysis_empty_records():
    """Test with empty record list."""
    plugin = create_aggregation_plugin({"name": "rationale_analysis", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})

    result = plugin.finalize([])

    assert result == {}


def test_rationale_analysis_on_error_skip():
    """Test on_error='skip' behavior."""
    from elspeth.plugins.experiments.aggregators.rationale_analysis import RationaleAnalysisAggregator

    plugin = RationaleAnalysisAggregator(on_error="skip")

    # Mock to raise an error
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    plugin._finalize_impl = boom
    assert plugin.finalize([{}]) == {}


def test_rationale_analysis_on_error_abort():
    """Test on_error='abort' behavior (default)."""
    from elspeth.plugins.experiments.aggregators.rationale_analysis import RationaleAnalysisAggregator

    plugin = RationaleAnalysisAggregator(on_error="abort")

    # Mock to raise an error
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    plugin._finalize_impl = boom

    with pytest.raises(RuntimeError, match="boom"):
        plugin.finalize([{}])


def test_rationale_analysis_custom_field_names():
    """Test using custom field names for rationale and score."""
    plugin = create_aggregation_plugin(
        {
            "name": "rationale_analysis",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"rationale_field": "explanation", "score_field": "rating"},
        }
    )

    records = [
        {
            "responses": {"crit": {"metrics": {"explanation": "This is excellent work.", "rating": 5}}},
            "metrics": {"scores": {"crit": 5.0}},
        }
    ]

    result = plugin.finalize(records)

    assert result["criteria"]["crit"]["count"] == 1
    assert result["criteria"]["crit"]["avg_length_chars"] > 0


def test_referee_alignment_basic():
    """Test basic referee alignment with numeric scores."""
    plugin = create_baseline_plugin(
        {
            "name": "referee_alignment",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"referee_fields": ["referee_score"]},
        }
    )

    baseline = {
        "results": [
            {"row": {"referee_score": 4.0}, "metrics": {"scores": {"crit": 3.5}}},
            {"row": {"referee_score": 5.0}, "metrics": {"scores": {"crit": 4.8}}},
            {"row": {"referee_score": 3.0}, "metrics": {"scores": {"crit": 3.2}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"referee_score": 4.0}, "metrics": {"scores": {"crit": 4.1}}},
            {"row": {"referee_score": 5.0}, "metrics": {"scores": {"crit": 4.9}}},
            {"row": {"referee_score": 3.0}, "metrics": {"scores": {"crit": 3.1}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    assert "baseline" in result
    assert "variant" in result
    assert "comparison" in result

    # Variant should have lower MAE (better alignment)
    assert result["comparison"]["mae_improved"] is True
    assert result["variant"]["mean_absolute_error"] < result["baseline"]["mean_absolute_error"]
    assert result["baseline"]["samples"] == 3
    assert result["variant"]["samples"] == 3


def test_referee_alignment_string_values():
    """Test referee alignment with string value mapping."""
    plugin = create_baseline_plugin(
        {
            "name": "referee_alignment",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"referee_fields": ["referee_judgment"]},
        }
    )

    baseline = {
        "results": [
            {"row": {"referee_judgment": "Yes"}, "metrics": {"scores": {"crit": 4.5}}},
            {"row": {"referee_judgment": "No"}, "metrics": {"scores": {"crit": 2.0}}},
            {"row": {"referee_judgment": "Partially"}, "metrics": {"scores": {"crit": 3.5}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"referee_judgment": "Yes"}, "metrics": {"scores": {"crit": 4.8}}},
            {"row": {"referee_judgment": "No"}, "metrics": {"scores": {"crit": 1.5}}},
            {"row": {"referee_judgment": "Partially"}, "metrics": {"scores": {"crit": 3.2}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    assert "baseline" in result
    assert "variant" in result
    # Should map Yes->5.0, No->1.0, Partially->3.0
    assert result["baseline"]["samples"] == 3
    assert result["variant"]["samples"] == 3


def test_referee_alignment_multiple_referee_fields():
    """Test aggregating multiple referee fields."""
    plugin = create_baseline_plugin(
        {
            "name": "referee_alignment",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"referee_fields": ["referee_1", "referee_2", "referee_3"]},
        }
    )

    baseline = {
        "results": [
            {
                "row": {"referee_1": 4.0, "referee_2": 5.0, "referee_3": 4.0},
                "metrics": {"scores": {"crit": 4.2}},
            },
            {
                "row": {"referee_1": 3.0, "referee_2": 3.0, "referee_3": 4.0},
                "metrics": {"scores": {"crit": 3.5}},
            },
        ]
    }

    variant = {
        "results": [
            {
                "row": {"referee_1": 4.0, "referee_2": 5.0, "referee_3": 4.0},
                "metrics": {"scores": {"crit": 4.4}},
            },
            {
                "row": {"referee_1": 3.0, "referee_2": 3.0, "referee_3": 4.0},
                "metrics": {"scores": {"crit": 3.4}},
            },
        ]
    }

    result = plugin.compare(baseline, variant)

    # Should compute mean of referee scores: (4+5+4)/3 = 4.33, (3+3+4)/3 = 3.33
    assert result["baseline"]["samples"] == 2
    assert result["variant"]["samples"] == 2
    assert "referee_mean" in result["baseline"]


def test_referee_alignment_criteria_filter():
    """Test filtering to specific criteria."""
    plugin = create_baseline_plugin(
        {
            "name": "referee_alignment",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"referee_fields": ["referee_score"], "criteria": ["analysis"]},
        }
    )

    baseline = {
        "results": [
            {
                "row": {"referee_score": 4.0},
                "metrics": {"scores": {"analysis": 3.8, "prioritization": 4.2}},
            }
        ]
    }

    variant = {
        "results": [
            {
                "row": {"referee_score": 4.0},
                "metrics": {"scores": {"analysis": 4.1, "prioritization": 3.5}},
            }
        ]
    }

    result = plugin.compare(baseline, variant)

    # Should have criteria breakdown for 'analysis' only
    assert "criteria" in result
    assert "analysis" in result["criteria"]
    assert "prioritization" not in result["criteria"]


def test_referee_alignment_correlation():
    """Test correlation computation."""
    plugin = create_baseline_plugin(
        {
            "name": "referee_alignment",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
        }
    )

    # Create data with strong positive correlation
    baseline = {
        "results": [
            {"row": {"referee_score": 1.0}, "metrics": {"scores": {"crit": 1.2}}},
            {"row": {"referee_score": 2.0}, "metrics": {"scores": {"crit": 2.1}}},
            {"row": {"referee_score": 3.0}, "metrics": {"scores": {"crit": 3.3}}},
            {"row": {"referee_score": 4.0}, "metrics": {"scores": {"crit": 3.9}}},
            {"row": {"referee_score": 5.0}, "metrics": {"scores": {"crit": 4.8}}},
        ]
    }

    # Even stronger correlation in variant
    variant = {
        "results": [
            {"row": {"referee_score": 1.0}, "metrics": {"scores": {"crit": 1.1}}},
            {"row": {"referee_score": 2.0}, "metrics": {"scores": {"crit": 2.0}}},
            {"row": {"referee_score": 3.0}, "metrics": {"scores": {"crit": 3.1}}},
            {"row": {"referee_score": 4.0}, "metrics": {"scores": {"crit": 4.0}}},
            {"row": {"referee_score": 5.0}, "metrics": {"scores": {"crit": 4.9}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    assert result["baseline"]["correlation"] is not None
    assert result["variant"]["correlation"] is not None
    # Both should have high positive correlation
    assert result["baseline"]["correlation"] > 0.8
    assert result["variant"]["correlation"] > 0.8
    # Variant should have better correlation
    assert result["comparison"]["correlation_improved"] is True


def test_referee_alignment_agreement_rate():
    """Test agreement rate within 1 point."""
    plugin = create_baseline_plugin(
        {
            "name": "referee_alignment",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
        }
    )

    baseline = {
        "results": [
            {"row": {"referee_score": 4.0}, "metrics": {"scores": {"crit": 4.5}}},  # within 1
            {"row": {"referee_score": 3.0}, "metrics": {"scores": {"crit": 5.0}}},  # not within 1
            {"row": {"referee_score": 5.0}, "metrics": {"scores": {"crit": 4.8}}},  # within 1
        ]
    }

    variant = {
        "results": [
            {"row": {"referee_score": 4.0}, "metrics": {"scores": {"crit": 4.2}}},  # within 1
            {"row": {"referee_score": 3.0}, "metrics": {"scores": {"crit": 3.5}}},  # within 1
            {"row": {"referee_score": 5.0}, "metrics": {"scores": {"crit": 4.9}}},  # within 1
        ]
    }

    result = plugin.compare(baseline, variant)

    # Baseline: 2/3 within 1 = 0.667
    assert result["baseline"]["agreement_rate_within_1"] == pytest.approx(2 / 3)
    # Variant: 3/3 within 1 = 1.0
    assert result["variant"]["agreement_rate_within_1"] == pytest.approx(1.0)


def test_referee_alignment_custom_value_mapping():
    """Test custom value mapping."""
    plugin = create_baseline_plugin(
        {
            "name": "referee_alignment",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {
                "referee_fields": ["referee_rating"],
                "value_mapping": {"excellent": 5.0, "good": 4.0, "fair": 3.0, "poor": 2.0},
            },
        }
    )

    baseline = {
        "results": [
            {"row": {"referee_rating": "excellent"}, "metrics": {"scores": {"crit": 4.8}}},
            {"row": {"referee_rating": "good"}, "metrics": {"scores": {"crit": 3.9}}},
            {"row": {"referee_rating": "fair"}, "metrics": {"scores": {"crit": 3.2}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"referee_rating": "excellent"}, "metrics": {"scores": {"crit": 4.9}}},
            {"row": {"referee_rating": "good"}, "metrics": {"scores": {"crit": 4.1}}},
            {"row": {"referee_rating": "fair"}, "metrics": {"scores": {"crit": 3.1}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    assert result["baseline"]["samples"] == 3
    assert result["variant"]["samples"] == 3


def test_referee_alignment_min_samples():
    """Test minimum samples requirement."""
    plugin = create_baseline_plugin(
        {
            "name": "referee_alignment",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
            "options": {"min_samples": 5},
        }
    )

    # Only 2 samples - below minimum
    baseline = {
        "results": [
            {"row": {"referee_score": 4.0}, "metrics": {"scores": {"crit": 3.8}}},
            {"row": {"referee_score": 5.0}, "metrics": {"scores": {"crit": 4.9}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"referee_score": 4.0}, "metrics": {"scores": {"crit": 4.1}}},
            {"row": {"referee_score": 5.0}, "metrics": {"scores": {"crit": 5.0}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Should return empty dicts due to min_samples
    assert result == {}


def test_referee_alignment_missing_referee_scores():
    """Test handling missing referee scores."""
    plugin = create_baseline_plugin(
        {
            "name": "referee_alignment",
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
        }
    )

    baseline = {
        "results": [
            {"row": {"referee_score": 4.0}, "metrics": {"scores": {"crit": 3.8}}},
            {"row": {}, "metrics": {"scores": {"crit": 4.2}}},  # Missing referee score
            {"row": {"referee_score": 5.0}, "metrics": {"scores": {"crit": 4.9}}},
        ]
    }

    variant = {
        "results": [
            {"row": {"referee_score": 4.0}, "metrics": {"scores": {"crit": 4.1}}},
            {"row": {}, "metrics": {"scores": {"crit": 3.5}}},  # Missing referee score
            {"row": {"referee_score": 5.0}, "metrics": {"scores": {"crit": 5.0}}},
        ]
    }

    result = plugin.compare(baseline, variant)

    # Should only use rows with referee scores
    assert result["baseline"]["samples"] == 2
    assert result["variant"]["samples"] == 2


def test_referee_alignment_on_error_skip():
    """Test on_error='skip' behavior."""
    from elspeth.plugins.experiments.baseline.referee_alignment import RefereeAlignmentBaselinePlugin

    plugin = RefereeAlignmentBaselinePlugin(security_level=SecurityLevel.OFFICIAL, on_error="skip")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    plugin._compare_impl = boom
    assert plugin.compare({"results": []}, {"results": []}) == {}


def test_referee_alignment_on_error_abort():
    """Test on_error='abort' behavior (default)."""
    from elspeth.plugins.experiments.baseline.referee_alignment import RefereeAlignmentBaselinePlugin

    plugin = RefereeAlignmentBaselinePlugin(security_level=SecurityLevel.OFFICIAL, on_error="abort")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    plugin._compare_impl = boom

    with pytest.raises(RuntimeError, match="boom"):
        plugin.compare({"results": []}, {"results": []})
