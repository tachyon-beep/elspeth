"""Coverage tests for experiment plugin_registry to reach 80% coverage.

Focuses on uncovered lines:
- Lines 131-133, 163-165, 189-191, 215-217, 241-243: Defensive None checks
- Lines 136-139: Row plugin error message compatibility
"""

from __future__ import annotations

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.experiments.plugin_registry import (
    create_aggregation_plugin,
    create_baseline_plugin,
    create_early_stop_plugin,
    create_row_plugin,
    create_validation_plugin,
    normalize_early_stop_definitions,
    validate_aggregation_plugin_definition,
    validate_baseline_plugin_definition,
    validate_early_stop_plugin_definition,
    validate_row_plugin_definition,
    validate_validation_plugin_definition,
)
from elspeth.core.validation.base import ConfigurationError


@pytest.fixture
def test_context():
    """Create test plugin context."""
    return PluginContext(
        security_level="internal",
        determinism_level="guaranteed",
        provenance=["test"],
        plugin_kind="experiment",
        plugin_name="test",
    )


def test_create_row_plugin_unknown_raises_compatible_error(test_context):
    """Test unknown row plugin raises compatible error - lines 136-139."""
    with pytest.raises(ValueError, match="Unknown row experiment plugin 'totally_unknown'"):
        create_row_plugin({"name": "totally_unknown"}, parent_context=test_context)


def test_validate_row_plugin_empty_definition():
    """Test validation with empty definition."""
    with pytest.raises(ConfigurationError, match="cannot be empty"):
        validate_row_plugin_definition({})


def test_validate_row_plugin_missing_name():
    """Test validation with missing name."""
    with pytest.raises(ConfigurationError, match="missing 'name' field"):
        validate_row_plugin_definition({"options": {}})


def test_validate_row_plugin_invalid_name_type():
    """Test validation with non-string name."""
    with pytest.raises(ConfigurationError, match="name is not a string"):
        validate_row_plugin_definition({"name": 123})


def test_validate_row_plugin_none_options():
    """Test validation treats None options as empty dict."""
    # Should not raise on None options (treated as {})
    try:
        validate_row_plugin_definition({
            "name": "noop",
            "options": None,
            "security_level": "internal"
        })
    except ConfigurationError as exc:
        # May fail on unknown plugin, but not on None options
        assert "options" not in str(exc)


def test_validate_row_plugin_invalid_options_type():
    """Test validation with non-dict options."""
    with pytest.raises(ConfigurationError, match="options must be a mapping"):
        validate_row_plugin_definition({
            "name": "noop",
            "options": "string"
        })


def test_validate_aggregation_plugin_empty_definition():
    """Test validation with empty definition."""
    with pytest.raises(ConfigurationError, match="cannot be empty"):
        validate_aggregation_plugin_definition({})


def test_validate_aggregation_plugin_none_options():
    """Test validation treats None options as empty dict."""
    try:
        validate_aggregation_plugin_definition({
            "name": "score_stats",
            "options": None,
            "security_level": "internal"
        })
    except ConfigurationError as exc:
        assert "options" not in str(exc)


def test_validate_baseline_plugin_empty_definition():
    """Test validation with empty definition."""
    with pytest.raises(ConfigurationError, match="cannot be empty"):
        validate_baseline_plugin_definition({})


def test_validate_baseline_plugin_none_options():
    """Test validation treats None options as empty dict."""
    try:
        validate_baseline_plugin_definition({
            "name": "row_count",
            "options": None,
            "security_level": "internal"
        })
    except ConfigurationError as exc:
        assert "options" not in str(exc)


def test_validate_validation_plugin_empty_definition():
    """Test validation with empty definition."""
    with pytest.raises(ConfigurationError, match="cannot be empty"):
        validate_validation_plugin_definition({})


def test_validate_validation_plugin_none_options():
    """Test validation treats None options as empty dict."""
    try:
        validate_validation_plugin_definition({
            "name": "regex",
            "options": None,
            "security_level": "internal"
        })
    except ConfigurationError as exc:
        assert "options" not in str(exc)


def test_validate_early_stop_plugin_empty_definition():
    """Test validation with empty definition."""
    with pytest.raises(ConfigurationError, match="cannot be empty"):
        validate_early_stop_plugin_definition({})


def test_validate_early_stop_plugin_none_options():
    """Test validation treats None options as empty dict."""
    try:
        validate_early_stop_plugin_definition({
            "name": "threshold",
            "options": None,
            "security_level": "internal"
        })
    except ConfigurationError as exc:
        assert "options" not in str(exc)


def test_normalize_early_stop_none():
    """Test normalizing None early stop definitions."""
    result = normalize_early_stop_definitions(None)
    assert result == []


def test_normalize_early_stop_empty_list():
    """Test normalizing empty list."""
    result = normalize_early_stop_definitions([])
    assert result == []


def test_normalize_early_stop_single_object():
    """Test normalizing single object (not list)."""
    definition = {
        "name": "threshold",
        "options": {"metric": "score", "threshold": 10}
    }
    result = normalize_early_stop_definitions(definition)

    assert len(result) == 1
    assert result[0]["name"] == "threshold"


def test_normalize_early_stop_list():
    """Test normalizing list of definitions."""
    definitions = [
        {"name": "threshold", "options": {"metric": "score", "threshold": 10}},
        {"metric": "accuracy", "threshold": 0.8},  # Shorthand
    ]
    result = normalize_early_stop_definitions(definitions)

    assert len(result) == 2
    assert result[0]["name"] == "threshold"
    assert result[1]["name"] == "threshold"  # Default name


def test_normalize_early_stop_invalid_type():
    """Test normalizing invalid type raises."""
    with pytest.raises(ConfigurationError, match="must be an object or list"):
        normalize_early_stop_definitions("string")


def test_normalize_early_stop_entry_not_mapping():
    """Test normalizing entry that's not a mapping."""
    with pytest.raises(ConfigurationError, match="must be an object"):
        normalize_early_stop_definitions(["string"])


def test_normalize_early_stop_invalid_options_type():
    """Test normalizing entry with non-mapping options."""
    with pytest.raises(ConfigurationError, match="options must be an object"):
        normalize_early_stop_definitions([{
            "name": "threshold",
            "options": "string"
        }])


def test_normalize_early_stop_shorthand_with_extra_keys():
    """Test normalizing with plugin name and extra keys."""
    definition = {
        "name": "threshold",
        "options": {"metric": "score"},
        "threshold": 10,  # Extra key merged into options
        "comparison": "gte"  # Extra key merged into options
    }
    result = normalize_early_stop_definitions(definition)

    assert result[0]["name"] == "threshold"
    assert result[0]["options"]["threshold"] == 10
    assert result[0]["options"]["comparison"] == "gte"
    assert result[0]["options"]["metric"] == "score"


def test_normalize_early_stop_pure_shorthand():
    """Test normalizing pure shorthand (no name/plugin key)."""
    definition = {
        "metric": "score",
        "threshold": 10,
        "comparison": "gte"
    }
    result = normalize_early_stop_definitions(definition)

    assert result[0]["name"] == "threshold"  # Default
    assert result[0]["options"]["metric"] == "score"
    assert result[0]["options"]["threshold"] == 10


def test_normalize_early_stop_plugin_key():
    """Test normalizing with 'plugin' instead of 'name'."""
    definition = {
        "plugin": "threshold",  # Use 'plugin' instead of 'name'
        "options": {"metric": "score", "threshold": 10}
    }
    result = normalize_early_stop_definitions(definition)

    assert result[0]["name"] == "threshold"


def test_create_plugins_with_valid_definitions(test_context):
    """Test creating all plugin types with valid definitions."""
    # Row plugin
    row_def = {
        "name": "noop",
        "security_level": "internal",
        "determinism_level": "guaranteed"
    }
    row_plugin = create_row_plugin(row_def, parent_context=test_context)
    assert row_plugin is not None

    # Aggregation plugin
    agg_def = {
        "name": "score_stats",
        "security_level": "internal",
        "determinism_level": "guaranteed"
    }
    agg_plugin = create_aggregation_plugin(agg_def, parent_context=test_context)
    assert agg_plugin is not None

    # Baseline plugin
    baseline_def = {
        "name": "score_delta",
        "security_level": "internal",
        "determinism_level": "guaranteed"
    }
    baseline_plugin = create_baseline_plugin(baseline_def, parent_context=test_context)
    assert baseline_plugin is not None

    # Validation plugin
    validation_def = {
        "name": "regex_match",
        "security_level": "internal",
        "determinism_level": "guaranteed",
        "options": {"pattern": ".*"}
    }
    validation_plugin = create_validation_plugin(validation_def, parent_context=test_context)
    assert validation_plugin is not None

    # Early stop plugin
    early_stop_def = {
        "name": "threshold",
        "security_level": "internal",
        "determinism_level": "guaranteed",
        "options": {"metric": "score", "threshold": 10}
    }
    early_stop_plugin = create_early_stop_plugin(early_stop_def, parent_context=test_context)
    assert early_stop_plugin is not None


def test_validate_plugins_with_security_level_conflicts():
    """Test validation with conflicting security levels."""
    # Row plugin
    with pytest.raises(ConfigurationError, match="row_plugin:noop"):
        validate_row_plugin_definition({
            "name": "noop",
            "security_level": "public",
            "options": {"security_level": "restricted"}
        })

    # Aggregation plugin
    with pytest.raises(ConfigurationError, match="aggregation_plugin:score_stats"):
        validate_aggregation_plugin_definition({
            "name": "score_stats",
            "security_level": "public",
            "options": {"security_level": "restricted"}
        })

    # Baseline plugin
    with pytest.raises(ConfigurationError, match="baseline_plugin:row_count"):
        validate_baseline_plugin_definition({
            "name": "row_count",
            "security_level": "public",
            "options": {"security_level": "restricted"}
        })

    # Validation plugin
    with pytest.raises(ConfigurationError, match="validation_plugin:regex"):
        validate_validation_plugin_definition({
            "name": "regex",
            "security_level": "public",
            "options": {"security_level": "restricted", "pattern": ".*"}
        })

    # Early stop plugin
    with pytest.raises(ConfigurationError, match="early_stop_plugin:threshold"):
        validate_early_stop_plugin_definition({
            "name": "threshold",
            "security_level": "public",
            "options": {"security_level": "restricted", "metric": "score", "threshold": 10}
        })


def test_validate_plugins_with_unknown_names():
    """Test validation with unknown plugin names."""
    with pytest.raises(ConfigurationError):
        validate_row_plugin_definition({
            "name": "totally_unknown_row_plugin",
            "security_level": "internal"
        })

    with pytest.raises(ConfigurationError):
        validate_aggregation_plugin_definition({
            "name": "totally_unknown_agg_plugin",
            "security_level": "internal"
        })

    with pytest.raises(ConfigurationError):
        validate_baseline_plugin_definition({
            "name": "totally_unknown_baseline_plugin",
            "security_level": "internal"
        })

    with pytest.raises(ConfigurationError):
        validate_validation_plugin_definition({
            "name": "totally_unknown_validation_plugin",
            "security_level": "internal"
        })

    with pytest.raises(ConfigurationError):
        validate_early_stop_plugin_definition({
            "name": "totally_unknown_early_stop_plugin",
            "security_level": "internal"
        })
