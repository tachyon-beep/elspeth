"""Coverage tests for ScoreDeltaBaselinePlugin to reach 80% coverage.

Focuses on uncovered lines:
- Line 41: Empty stats case
- Line 47: Criteria filtering
- Line 51: Missing metrics
- Line 59, 62, 65: _extract_stats edge cases
"""

from __future__ import annotations

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.experiments.baseline.score_delta import ScoreDeltaBaselinePlugin


@pytest.fixture
def context():
    """Create test plugin context."""
    return PluginContext(
        security_level="internal",
        determinism_level="guaranteed",  # Use valid value
        provenance=["test"],
        plugin_kind="baseline_plugin",
        plugin_name="score_delta",
    )


def test_score_delta_empty_stats(context):
    """Test score_delta with empty/missing stats - line 41."""
    plugin = ScoreDeltaBaselinePlugin(
        security_level=context.security_level,
        metric="mean"
    )

    # Both baseline and variant have no score_stats
    baseline = {"aggregates": {}}
    variant = {"aggregates": {}}

    result = plugin.compare(baseline, variant)
    assert result == {}

    # Only baseline has stats
    baseline = {"aggregates": {"score_stats": {"criteria": {"accuracy": {"mean": 0.8}}}}}
    variant = {"aggregates": {}}
    result = plugin.compare(baseline, variant)
    assert result == {}


def test_score_delta_criteria_filtering(context):
    """Test criteria filtering - line 47."""
    # Only include specific criteria
    plugin = ScoreDeltaBaselinePlugin(
        security_level=context.security_level,
        metric="mean",
        criteria=["accuracy"]
    )

    baseline = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.7},
                    "precision": {"mean": 0.6},
                }
            }
        }
    }
    variant = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.8},
                    "precision": {"mean": 0.75},
                }
            }
        }
    }

    result = plugin.compare(baseline, variant)
    # Only accuracy should be included (precision filtered out)
    assert "accuracy" in result
    assert "precision" not in result
    assert result["accuracy"] == pytest.approx(0.1)


def test_score_delta_missing_metrics(context):
    """Test handling of missing metrics in criteria - line 51."""
    plugin = ScoreDeltaBaselinePlugin(
        security_level=context.security_level,
        metric="median"
    )

    baseline = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.7},  # Has mean but not median
                    "recall": {"mean": 0.6, "median": 0.65},
                }
            }
        }
    }
    variant = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.8},  # Has mean but not median
                    "recall": {"mean": 0.75, "median": 0.8},
                }
            }
        }
    }

    result = plugin.compare(baseline, variant)
    # accuracy should be skipped (no median), only recall
    assert "accuracy" not in result
    assert "recall" in result
    assert result["recall"] == pytest.approx(0.15)


def test_extract_stats_not_mapping(context):
    """Test _extract_stats with non-mapping payload - line 59."""
    plugin = ScoreDeltaBaselinePlugin(security_level=context.security_level)

    # Non-dict payload
    result = plugin._extract_stats("not a dict")
    assert result == {}

    # None payload
    result = plugin._extract_stats(None)
    assert result == {}

    # List payload
    result = plugin._extract_stats([1, 2, 3])
    assert result == {}


def test_extract_stats_no_aggregates(context):
    """Test _extract_stats with missing aggregates - line 62."""
    plugin = ScoreDeltaBaselinePlugin(security_level=context.security_level)

    # aggregates is not a mapping
    result = plugin._extract_stats({"aggregates": "string"})
    assert result == {}

    result = plugin._extract_stats({"aggregates": None})
    assert result == {}

    result = plugin._extract_stats({"aggregates": [1, 2, 3]})
    assert result == {}


def test_extract_stats_no_score_stats(context):
    """Test _extract_stats with missing/invalid score_stats - line 65."""
    plugin = ScoreDeltaBaselinePlugin(security_level=context.security_level)

    # score_stats is not a mapping
    result = plugin._extract_stats({"aggregates": {"score_stats": "string"}})
    assert result == {}

    result = plugin._extract_stats({"aggregates": {"score_stats": None}})
    assert result == {}

    result = plugin._extract_stats({"aggregates": {"score_stats": [1, 2]}})
    assert result == {}

    # score_stats has no criteria
    result = plugin._extract_stats({"aggregates": {"score_stats": {}}})
    assert result == {}

    # criteria is not a mapping
    result = plugin._extract_stats({"aggregates": {"score_stats": {"criteria": "string"}}})
    assert result == {}


def test_score_delta_with_criteria_none_values(context):
    """Test when criteria values are None."""
    plugin = ScoreDeltaBaselinePlugin(
        security_level=context.security_level,
        metric="mean"
    )

    baseline = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": None},
                }
            }
        }
    }
    variant = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.8},
                }
            }
        }
    }

    result = plugin.compare(baseline, variant)
    # Should skip accuracy because baseline mean is None
    assert result == {}


def test_score_delta_metric_variants():
    """Test different metric types."""
    baseline = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.7, "std": 0.1, "min": 0.5, "max": 0.9},
                }
            }
        }
    }
    variant = {
        "aggregates": {
            "score_stats": {
                "criteria": {
                    "accuracy": {"mean": 0.8, "std": 0.15, "min": 0.6, "max": 0.95},
                }
            }
        }
    }

    # Test with std metric
    plugin = ScoreDeltaBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        metric="std"
    )
    result = plugin.compare(baseline, variant)
    assert result["accuracy"] == pytest.approx(0.05)

    # Test with min metric
    plugin = ScoreDeltaBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        metric="min"
    )
    result = plugin.compare(baseline, variant)
    assert result["accuracy"] == pytest.approx(0.1)

    # Test with max metric
    plugin = ScoreDeltaBaselinePlugin(
        security_level=SecurityLevel.UNOFFICIAL,
        metric="max"
    )
    result = plugin.compare(baseline, variant)
    assert result["accuracy"] == pytest.approx(0.05)
