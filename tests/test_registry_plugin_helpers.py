"""Tests for plugin_helpers module.

Tests the create_plugin_with_inheritance() function which consolidates
the "controls pattern" used across multiple registries.
"""

import pytest

from elspeth.core.plugins import PluginContext
from elspeth.core.registry.base import BasePluginRegistry
from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance
from elspeth.core.validation import ConfigurationError


class MockPlugin:
    """Mock plugin for testing."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def create_mock_plugin(options, context):
    """Factory for mock plugin."""
    return MockPlugin(**options)


@pytest.fixture
def mock_registry():
    """Create a mock registry for testing."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("test", create_mock_plugin, schema=None)
    return registry


@pytest.fixture
def parent_context():
    """Create a parent context for inheritance tests."""
    return PluginContext(
        plugin_name="parent",
        plugin_kind="parent_type",
        security_level="PROTECTED",
        determinism_level="high",
        provenance=("parent:test",),
    )


# Basic functionality tests


def test_create_plugin_basic(mock_registry):
    """Helper creates plugin with basic definition."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        "security_level": "OFFICIAL",
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
        allow_none=False,
    )

    assert isinstance(plugin, MockPlugin)
    assert plugin.value == "test_value"
    assert hasattr(plugin, "_elspeth_context")
    assert plugin._elspeth_context.security_level == "OFFICIAL"
    assert plugin._elspeth_context.determinism_level == "high"


def test_create_plugin_with_plugin_key(mock_registry):
    """Helper accepts 'plugin' key as alternative to 'name'."""
    definition = {
        "plugin": "test",  # Use 'plugin' instead of 'name'
        "options": {"value": "test_value"},
        "security_level": "OFFICIAL",
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    assert isinstance(plugin, MockPlugin)
    assert plugin.value == "test_value"


# Optional plugin tests (allow_none=True)


def test_create_plugin_none_with_allow_none(mock_registry):
    """Helper returns None when definition is None and allow_none=True."""
    plugin = create_plugin_with_inheritance(
        mock_registry,
        None,
        plugin_kind="test_plugin",
        allow_none=True,
    )

    assert plugin is None


def test_create_plugin_empty_dict_with_allow_none(mock_registry):
    """Helper returns None when definition is empty dict and allow_none=True."""
    plugin = create_plugin_with_inheritance(
        mock_registry,
        {},
        plugin_kind="test_plugin",
        allow_none=True,
    )

    assert plugin is None


def test_create_plugin_none_without_allow_none(mock_registry):
    """Helper raises ValueError when definition is None and allow_none=False."""
    with pytest.raises(ValueError, match="test_plugin definition cannot be empty"):
        create_plugin_with_inheritance(
            mock_registry,
            None,
            plugin_kind="test_plugin",
            allow_none=False,
        )


# Inheritance tests


def test_create_plugin_inherits_security_from_parent(mock_registry, parent_context):
    """Helper inherits security_level from parent when not specified."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        # No security_level specified
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
        parent_context=parent_context,
    )

    # Should inherit PROTECTED from parent
    assert plugin._elspeth_context.security_level == "PROTECTED"
    assert plugin._elspeth_context.determinism_level == "high"
    assert plugin._elspeth_context.parent == parent_context


def test_create_plugin_inherits_determinism_from_parent(mock_registry, parent_context):
    """Helper inherits determinism_level from parent when not specified."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        # No security_level specified - will inherit PROTECTED from parent
        # No determinism_level specified - will inherit from parent
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
        parent_context=parent_context,
    )

    assert plugin._elspeth_context.security_level == "PROTECTED"  # Inherited from parent
    # Should inherit "high" from parent
    assert plugin._elspeth_context.determinism_level == "high"


def test_create_plugin_overrides_parent_security(mock_registry, parent_context):
    """Helper uses explicit security_level instead of parent's."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        "security_level": "SECRET",  # Override parent's PROTECTED
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
        parent_context=parent_context,
    )

    # Should use explicit SECRET, not inherit PROTECTED
    assert plugin._elspeth_context.security_level == "SECRET"
    assert plugin._elspeth_context.parent == parent_context


def test_create_plugin_defaults_determinism_to_none(mock_registry):
    """Helper defaults determinism_level to 'none' when not specified."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        "security_level": "OFFICIAL",
        # No determinism_level, no parent
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
        parent_context=None,
    )

    # Should default to "none"
    assert plugin._elspeth_context.determinism_level == "none"


# Options coalescing tests


def test_create_plugin_security_in_definition(mock_registry):
    """Helper uses security_level from definition."""
    definition = {
        "name": "test",
        "security_level": "PROTECTED",  # In definition
        "options": {"value": "test_value"},
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    assert plugin._elspeth_context.security_level == "PROTECTED"


def test_create_plugin_security_in_options(mock_registry):
    """Helper uses security_level from options."""
    definition = {
        "name": "test",
        "options": {
            "value": "test_value",
            "security_level": "PROTECTED",  # In options
        },
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    assert plugin._elspeth_context.security_level == "PROTECTED"


def test_create_plugin_security_coalescing_error(mock_registry):
    """Helper raises ConfigurationError on conflicting security levels."""
    definition = {
        "name": "test",
        "security_level": "PROTECTED",
        "options": {
            "value": "test_value",
            "security_level": "SECRET",  # Conflict!
        },
        "determinism_level": "high",
    }

    with pytest.raises(ConfigurationError, match="test_plugin:test"):
        create_plugin_with_inheritance(
            mock_registry,
            definition,
            plugin_kind="test_plugin",
        )


def test_create_plugin_determinism_coalescing_error(mock_registry):
    """Helper raises ConfigurationError on conflicting determinism levels."""
    definition = {
        "name": "test",
        "security_level": "OFFICIAL",
        "determinism_level": "high",
        "options": {
            "value": "test_value",
            "determinism_level": "low",  # Conflict!
        },
    }

    with pytest.raises(ConfigurationError, match="test_plugin:test"):
        create_plugin_with_inheritance(
            mock_registry,
            definition,
            plugin_kind="test_plugin",
        )


# Provenance tracking tests


def test_create_plugin_provenance_from_definition(mock_registry):
    """Helper tracks provenance from definition security_level."""
    definition = {
        "name": "test",
        "security_level": "PROTECTED",
        "options": {"value": "test_value"},
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    provenance = plugin._elspeth_context.provenance
    assert "test_plugin:test.definition.security_level" in provenance
    assert "test_plugin:test.definition.determinism_level" in provenance


def test_create_plugin_provenance_from_options(mock_registry):
    """Helper tracks provenance from options security_level."""
    definition = {
        "name": "test",
        "options": {
            "value": "test_value",
            "security_level": "PROTECTED",
            "determinism_level": "high",
        },
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    provenance = plugin._elspeth_context.provenance
    assert "test_plugin:test.options.security_level" in provenance
    assert "test_plugin:test.options.determinism_level" in provenance


def test_create_plugin_provenance_inheritance(mock_registry, parent_context):
    """Helper tracks provenance when inheriting from parent."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        # No security_level - will inherit
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
        parent_context=parent_context,
    )

    provenance = plugin._elspeth_context.provenance
    assert "test_plugin:test.inherited.security_level" in provenance
    assert "test_plugin:test.inherited.determinism_level" in provenance


def test_create_plugin_additional_provenance(mock_registry):
    """Helper appends additional provenance sources."""
    definition = {
        "name": "test",
        "security_level": "OFFICIAL",
        "options": {"value": "test_value"},
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
        provenance=["custom:source1", "custom:source2"],
    )

    provenance = plugin._elspeth_context.provenance
    assert "custom:source1" in provenance
    assert "custom:source2" in provenance


# Error handling tests


def test_create_plugin_missing_name(mock_registry):
    """Helper raises ValueError when name is missing."""
    definition = {
        # No 'name' or 'plugin' key
        "options": {"value": "test_value"},
        "security_level": "OFFICIAL",
        "determinism_level": "high",
    }

    with pytest.raises(ValueError, match="test_plugin definition missing 'name' or 'plugin'"):
        create_plugin_with_inheritance(
            mock_registry,
            definition,
            plugin_kind="test_plugin",
        )


def test_create_plugin_unknown_plugin(mock_registry):
    """Helper raises ValueError for unknown plugin name."""
    definition = {
        "name": "nonexistent",
        "options": {"value": "test_value"},
        "security_level": "OFFICIAL",
        "determinism_level": "high",
    }

    with pytest.raises(ValueError, match="Unknown test_plugin 'nonexistent'"):
        create_plugin_with_inheritance(
            mock_registry,
            definition,
            plugin_kind="test_plugin",
        )


# Payload preparation tests


def test_create_plugin_strips_security_from_options(mock_registry):
    """Helper strips security_level and determinism_level from options payload."""
    definition = {
        "name": "test",
        "options": {
            "value": "test_value",
            "other_option": "other_value",
            "security_level": "OFFICIAL",  # Should be stripped
            "determinism_level": "high",  # Should be stripped
        },
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    # Plugin should have other_option but not security_level/determinism_level from options
    # (They're in the context, not as plugin attributes)
    assert plugin.value == "test_value"
    assert plugin.other_option == "other_value"
    # Note: plugin might have security_level from context application,
    # but it won't have it from the **options dict
    assert plugin._elspeth_context.security_level == "OFFICIAL"
    assert plugin._elspeth_context.determinism_level == "high"


def test_create_plugin_empty_options(mock_registry):
    """Helper handles empty options dict."""
    definition = {
        "name": "test",
        "options": {},
        "security_level": "OFFICIAL",
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    assert isinstance(plugin, MockPlugin)


def test_create_plugin_none_options(mock_registry):
    """Helper handles None options."""
    definition = {
        "name": "test",
        "options": None,
        "security_level": "OFFICIAL",
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    assert isinstance(plugin, MockPlugin)


# Context derivation tests


def test_create_plugin_derives_from_parent(mock_registry, parent_context):
    """Helper derives context from parent when parent exists."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        # No explicit security_level - will inherit PROTECTED from parent
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
        parent_context=parent_context,
    )

    # Should have parent link
    assert plugin._elspeth_context.parent == parent_context
    assert plugin._elspeth_context.plugin_name == "test"
    assert plugin._elspeth_context.plugin_kind == "test_plugin"
    assert plugin._elspeth_context.security_level == "PROTECTED"  # Inherited from parent


def test_create_plugin_creates_root_context(mock_registry):
    """Helper creates root context when no parent exists."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        "security_level": "OFFICIAL",
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
        parent_context=None,
    )

    # Should have no parent
    assert plugin._elspeth_context.parent is None
    assert plugin._elspeth_context.plugin_name == "test"
    assert plugin._elspeth_context.plugin_kind == "test_plugin"


# Integration test with real use case


def test_create_plugin_rate_limiter_pattern(mock_registry):
    """Helper works with rate_limiter pattern (optional, inherits security)."""
    # Rate limiters are optional and inherit security from parent
    parent = PluginContext(
        plugin_name="experiment",
        plugin_kind="experiment",
        security_level="PROTECTED",
        determinism_level="high",
        provenance=("experiment:test",),
    )

    # None definition - should return None
    plugin = create_plugin_with_inheritance(
        mock_registry,
        None,
        plugin_kind="rate_limiter",
        parent_context=parent,
        allow_none=True,
    )
    assert plugin is None

    # With definition - should inherit security
    definition = {
        "name": "test",
        "options": {"rate": 100},
        # No explicit security_level - should inherit
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="rate_limiter",
        parent_context=parent,
        allow_none=True,
    )

    assert plugin is not None
    assert plugin.rate == 100
    assert plugin._elspeth_context.security_level == "PROTECTED"  # Inherited


def test_create_plugin_experiment_plugin_pattern(mock_registry):
    """Helper works with experiment plugin pattern (required, explicit security)."""
    parent = PluginContext(
        plugin_name="experiment",
        plugin_kind="experiment",
        security_level="PROTECTED",
        determinism_level="high",
        provenance=("experiment:test",),
    )

    definition = {
        "name": "test",
        "security_level": "SECRET",  # Experiment plugins often specify explicitly
        "options": {"threshold": 0.5},
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="row_plugin",
        parent_context=parent,
        allow_none=False,  # Required
    )

    assert plugin is not None
    assert plugin.threshold == 0.5
    assert plugin._elspeth_context.security_level == "SECRET"  # Explicit, not inherited
    assert plugin._elspeth_context.determinism_level == "high"  # Inherited
