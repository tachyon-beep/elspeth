"""Coverage tests for ThresholdEarlyStopPlugin to reach 80% coverage.

Focuses on uncovered lines:
- Line 25: Empty metric validation
- Line 28-29: Invalid threshold value
- Line 33: Invalid comparison key
- Line 49: Already triggered check
- Line 54: Missing value
- Line 58-59: Non-numeric value
- Line 66: Not meeting min_rows
- Line 76-79: Label and metadata handling
- Line 89: Missing nested metric
- Line 95, 97, 99: Other comparison operators
"""

from __future__ import annotations

import pytest

from elspeth.plugins.experiments.early_stop import ThresholdEarlyStopPlugin


def test_empty_metric_raises():
    """Test that empty metric raises ValueError - line 25."""
    with pytest.raises(ValueError, match="requires a 'metric' path"):
        ThresholdEarlyStopPlugin(metric="", threshold=10)

    with pytest.raises(ValueError, match="requires a 'metric' path"):
        ThresholdEarlyStopPlugin(metric=None, threshold=10)


def test_invalid_threshold_raises():
    """Test that invalid threshold raises ValueError - lines 28-29."""
    with pytest.raises(ValueError, match="Invalid threshold value"):
        ThresholdEarlyStopPlugin(metric="score", threshold="not_a_number")

    with pytest.raises(ValueError, match="Invalid threshold value"):
        ThresholdEarlyStopPlugin(metric="score", threshold=None)

    with pytest.raises(ValueError, match="Invalid threshold value"):
        ThresholdEarlyStopPlugin(metric="score", threshold=[1, 2, 3])


def test_invalid_comparison_defaults_to_gte():
    """Test that invalid comparison defaults to 'gte' - line 33."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10, comparison="invalid")
    assert plugin._comparison == "gte"

    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10, comparison=None)
    assert plugin._comparison == "gte"


def test_already_triggered_returns_cached_reason():
    """Test that already triggered check returns cached reason - line 49."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10, min_rows=1)

    record1 = {"metrics": {"score": 15}}
    result1 = plugin.check(record1)
    assert result1 is not None
    assert result1["metric"] == "score"

    # Second check should return same reason (cached)
    record2 = {"metrics": {"score": 20}}
    result2 = plugin.check(record2)
    assert result2 == result1


def test_missing_value_returns_none():
    """Test that missing value returns None - line 54."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10)

    # No metrics at all
    result = plugin.check({})
    assert result is None

    # Metrics is None
    result = plugin.check({"metrics": None})
    assert result is None

    # Metrics missing the key
    result = plugin.check({"metrics": {"other": 5}})
    assert result is None


def test_non_numeric_value_returns_none():
    """Test that non-numeric value returns None - lines 58-59."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10)

    # String value
    result = plugin.check({"metrics": {"score": "not a number"}})
    assert result is None

    # None value
    result = plugin.check({"metrics": {"score": None}})
    assert result is None

    # Dict value
    result = plugin.check({"metrics": {"score": {"nested": 5}}})
    assert result is None


def test_min_rows_threshold():
    """Test min_rows threshold - line 66."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10, min_rows=3)

    # First row - below min_rows
    result = plugin.check({"metrics": {"score": 15}})
    assert result is None

    # Second row - still below min_rows
    result = plugin.check({"metrics": {"score": 16}})
    assert result is None

    # Third row - meets min_rows, should trigger
    result = plugin.check({"metrics": {"score": 17}})
    assert result is not None
    assert result["rows_observed"] == 3


def test_label_and_metadata_in_reason():
    """Test label and metadata are added to reason - lines 76-79."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10, label="accuracy_check")

    metadata = {"experiment": "test_exp", "variant": "A"}
    result = plugin.check({"metrics": {"score": 15}}, metadata=metadata)

    assert result is not None
    assert result["label"] == "accuracy_check"
    assert result["experiment"] == "test_exp"
    assert result["variant"] == "A"


def test_nested_metric_extraction():
    """Test nested metric path extraction - line 89."""
    plugin = ThresholdEarlyStopPlugin(metric="outer.inner.value", threshold=10)

    # Valid nested path
    record = {"metrics": {"outer": {"inner": {"value": 15}}}}
    result = plugin.check(record)
    assert result is not None

    # Reset plugin for next test
    plugin.reset()

    # Missing intermediate level
    record = {"metrics": {"outer": {"wrong": {"value": 15}}}}
    result = plugin.check(record)
    assert result is None

    # Non-dict intermediate
    record = {"metrics": {"outer": "string"}}
    result = plugin.check(record)
    assert result is None


def test_comparison_gt():
    """Test 'gt' comparison operator - line 95."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10, comparison="gt")

    # Equal - should not trigger
    result = plugin.check({"metrics": {"score": 10}})
    assert result is None

    # Greater - should trigger
    result = plugin.check({"metrics": {"score": 10.1}})
    assert result is not None
    assert result["comparison"] == "gt"


def test_comparison_lte():
    """Test 'lte' comparison operator - line 97."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10, comparison="lte")

    # Greater - should not trigger
    result = plugin.check({"metrics": {"score": 11}})
    assert result is None

    # Equal - should trigger
    plugin.reset()
    result = plugin.check({"metrics": {"score": 10}})
    assert result is not None

    # Less - should trigger
    plugin.reset()
    result = plugin.check({"metrics": {"score": 9}})
    assert result is not None
    assert result["comparison"] == "lte"


def test_comparison_lt():
    """Test 'lt' comparison operator - line 99."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10, comparison="lt")

    # Equal - should not trigger
    result = plugin.check({"metrics": {"score": 10}})
    assert result is None

    # Less - should trigger
    result = plugin.check({"metrics": {"score": 9.9}})
    assert result is not None
    assert result["comparison"] == "lt"


def test_reset():
    """Test reset clears state."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10, min_rows=2)

    # Trigger the plugin
    plugin.check({"metrics": {"score": 15}})
    plugin.check({"metrics": {"score": 16}})

    # Reset
    plugin.reset()
    assert plugin._rows_observed == 0
    assert plugin._triggered_reason is None

    # Should not trigger immediately after reset
    result = plugin.check({"metrics": {"score": 17}})
    assert result is None  # min_rows not met yet


def test_min_rows_enforces_minimum():
    """Test that min_rows is enforced to be at least 1."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10, min_rows=0)
    assert plugin._min_rows == 1

    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10, min_rows=-5)
    assert plugin._min_rows == 1


def test_metadata_does_not_overwrite_reason_keys():
    """Test that metadata doesn't overwrite reason keys - line 78."""
    plugin = ThresholdEarlyStopPlugin(metric="score", threshold=10)

    # Metadata has 'metric' key, should not overwrite
    metadata = {"metric": "fake", "custom_key": "custom_value"}
    result = plugin.check({"metrics": {"score": 15}}, metadata=metadata)

    assert result is not None
    assert result["metric"] == "score"  # Should be from reason, not metadata
    assert result["custom_key"] == "custom_value"  # Custom key should be added
