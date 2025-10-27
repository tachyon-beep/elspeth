"""Tests for plugin_helpers module.

Tests the create_plugin_with_inheritance() function which consolidates
the "controls pattern" used across multiple registries.
"""

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.base import BasePluginRegistry
from elspeth.core.registries.plugin_helpers import create_plugin_with_inheritance
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
    """Create a mock registry for testing.

    ADR-002-B: All plugins must declare security level at registration.
    """
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("test", create_mock_plugin, schema=None, declared_security_level="UNOFFICIAL")
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
    assert plugin._elspeth_context.security_level == "UNOFFICIAL"  # From factory registration
    assert plugin._elspeth_context.determinism_level == "high"


def test_create_plugin_with_plugin_key(mock_registry):
    """Helper accepts 'plugin' key as alternative to 'name'."""
    definition = {
        "plugin": "test",  # Use 'plugin' instead of 'name'
        "options": {"value": "test_value"},
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


def test_create_plugin_requires_security_even_with_parent(mock_registry, parent_context):
    """Helper prevents downgrade from parent security level (ADR-002-B).

    With ADR-002-B, security_level is optional (defaults to UNOFFICIAL).
    If parent has higher level, child defaulting to UNOFFICIAL triggers downgrade error.
    """
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        "determinism_level": "high",
        # No security_level → defaults to UNOFFICIAL
    }

    # Parent has PROTECTED, child defaults to UNOFFICIAL → downgrade error
    with pytest.raises(ConfigurationError, match="cannot downgrade parent level"):
        create_plugin_with_inheritance(
            mock_registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=parent_context,
        )


def test_create_plugin_requires_determinism_even_with_parent(mock_registry, parent_context):
    """Helper refuses to inherit determinism_level; plugin must declare it."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
    }

    with pytest.raises(ConfigurationError, match="determinism_level must be declared"):
        create_plugin_with_inheritance(
            mock_registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=parent_context,
        )


def test_create_plugin_overrides_parent_security(parent_context):
    """Helper uses factory security_level (not inherited from parent).

    ADR-002-B: Security levels come from factory registration, not config.
    """
    # Create a registry with SECRET-level plugin
    secret_registry = BasePluginRegistry[MockPlugin]("test_plugin")
    secret_registry.register("test", create_mock_plugin, schema=None, declared_security_level="SECRET")

    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        secret_registry,
        definition,
        plugin_kind="test_plugin",
        parent_context=parent_context,
    )

    # Should use factory's SECRET, not inherit parent's PROTECTED
    assert plugin._elspeth_context.security_level == "SECRET"
    assert plugin._elspeth_context.parent == parent_context


def test_create_plugin_requires_determinism_when_no_parent(mock_registry):
    """Helper enforces determinism_level even without parent."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
    }

    with pytest.raises(ConfigurationError, match="determinism_level must be declared"):
        create_plugin_with_inheritance(
            mock_registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=None,
        )


# Options coalescing tests


def test_create_plugin_security_in_definition(mock_registry):
    """Helper REJECTS security_level from definition (ADR-002-B)."""
    definition = {
        "name": "test",
        "security_level": "PROTECTED",  # In definition - should be rejected
        "options": {"value": "test_value"},
        "determinism_level": "high",
    }

    with pytest.raises(ConfigurationError, match="security_level must NOT be specified in configuration"):
        create_plugin_with_inheritance(
            mock_registry,
            definition,
            plugin_kind="test_plugin",
        )


def test_create_plugin_security_in_options(mock_registry):
    """Helper REJECTS security_level from options (ADR-002-B)."""
    definition = {
        "name": "test",
        "options": {
            "value": "test_value",
            "security_level": "PROTECTED",  # In options - should be rejected
        },
        "determinism_level": "high",
    }

    with pytest.raises(ConfigurationError, match="security_level must NOT be specified in configuration"):
        create_plugin_with_inheritance(
            mock_registry,
            definition,
            plugin_kind="test_plugin",
        )


def test_create_plugin_security_coalescing_error(mock_registry):
    """Helper raises ConfigurationError when security_level appears anywhere in config (ADR-002-B)."""
    definition = {
        "name": "test",
        "security_level": "PROTECTED",
        "options": {
            "value": "test_value",
        },
        "determinism_level": "high",
    }

    with pytest.raises(ConfigurationError, match="security_level must NOT be specified in configuration"):
        create_plugin_with_inheritance(
            mock_registry,
            definition,
            plugin_kind="test_plugin",
        )


def test_create_plugin_determinism_coalescing_error(mock_registry):
    """Helper raises ConfigurationError on conflicting determinism levels."""
    definition = {
        "name": "test",
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
    """Helper tracks provenance from factory and definition (ADR-002-B)."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    provenance = plugin._elspeth_context.provenance
    assert "test_plugin:test.factory.declared_security_level" in provenance
    assert "test_plugin:test.definition.determinism_level" in provenance


def test_create_plugin_provenance_from_options(mock_registry):
    """Helper tracks provenance from factory and options (ADR-002-B)."""
    definition = {
        "name": "test",
        "options": {
            "value": "test_value",
            "determinism_level": "high",
        },
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    provenance = plugin._elspeth_context.provenance
    assert "test_plugin:test.factory.declared_security_level" in provenance
    assert "test_plugin:test.options.determinism_level" in provenance


def test_create_plugin_missing_levels_raises(mock_registry, parent_context):
    """Plugins without explicit determinism_level fail to instantiate (ADR-002-B).

    With ADR-002-B, security_level is optional (defaults to UNOFFICIAL),
    but determinism_level is REQUIRED and must be explicitly declared.
    """
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        # No security_level → OK (defaults to UNOFFICIAL)
        # No determinism_level → ERROR (required)
    }

    with pytest.raises(ConfigurationError, match="determinism_level must be declared"):
        create_plugin_with_inheritance(
            mock_registry,
            definition,
            plugin_kind="test_plugin",
            parent_context=parent_context,
        )


def test_create_plugin_additional_provenance(mock_registry):
    """Helper appends additional provenance sources."""
    definition = {
        "name": "test",
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
    """Helper strips determinism_level from options payload (security_level rejected by ADR-002-B)."""
    definition = {
        "name": "test",
        "options": {
            "value": "test_value",
            "other_option": "other_value",
            "determinism_level": "high",  # Should be stripped
        },
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    # Plugin should have other_option but not determinism_level from options
    # (They're in the context, not as plugin attributes)
    assert plugin.value == "test_value"
    assert plugin.other_option == "other_value"
    # Note: plugin might have determinism_level from context application,
    # but it won't have it from the **options dict
    assert plugin._elspeth_context.security_level == "UNOFFICIAL"  # From factory
    assert plugin._elspeth_context.determinism_level == "high"


def test_create_plugin_empty_options(mock_registry):
    """Helper handles empty options dict."""
    definition = {
        "name": "test",
        "options": {},
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
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        mock_registry,
        definition,
        plugin_kind="test_plugin",
    )

    assert isinstance(plugin, MockPlugin)


# Context derivation tests


def test_create_plugin_derives_from_parent(parent_context):
    """Helper derives context from parent when parent exists.

    ADR-002-B: Plugin gets factory's security level (not from parent or config).
    """
    # Create registry with PROTECTED-level plugin
    protected_registry = BasePluginRegistry[MockPlugin]("test_plugin")
    protected_registry.register("test", create_mock_plugin, schema=None, declared_security_level="PROTECTED")

    definition = {
        "name": "test",
        "options": {"value": "test_value"},
        "determinism_level": "high",
    }

    plugin = create_plugin_with_inheritance(
        protected_registry,
        definition,
        plugin_kind="test_plugin",
        parent_context=parent_context,
    )

    # Should have parent link
    assert plugin._elspeth_context.parent == parent_context
    assert plugin._elspeth_context.plugin_name == "test"
    assert plugin._elspeth_context.plugin_kind == "test_plugin"
    assert plugin._elspeth_context.security_level == "PROTECTED"


def test_create_plugin_creates_root_context(mock_registry):
    """Helper creates root context when no parent exists."""
    definition = {
        "name": "test",
        "options": {"value": "test_value"},
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


def test_create_plugin_rate_limiter_pattern():
    """Helper enforces explicit levels for rate_limiter pattern.

    ADR-002-B: Security level from factory, determinism_level required in config.
    """
    # Rate limiters are optional but must declare their own levels
    parent = PluginContext(
        plugin_name="experiment",
        plugin_kind="experiment",
        security_level="PROTECTED",
        determinism_level="high",
        provenance=("experiment:test",),
    )

    # Create registry with PROTECTED-level plugin
    protected_registry = BasePluginRegistry[MockPlugin]("test_plugin")
    protected_registry.register("test", create_mock_plugin, schema=None, declared_security_level="PROTECTED")

    # None definition - should return None
    plugin = create_plugin_with_inheritance(
        protected_registry,
        None,
        plugin_kind="rate_limiter",
        parent_context=parent,
        allow_none=True,
    )
    assert plugin is None

    # With definition missing determinism_level - should raise (ADR-002-B: determinism_level is REQUIRED)
    definition = {
        "name": "test",
        "options": {"rate": 100},
    }

    with pytest.raises(ConfigurationError, match="determinism_level must be declared"):
        create_plugin_with_inheritance(
            protected_registry,
            definition,
            plugin_kind="rate_limiter",
            parent_context=parent,
            allow_none=True,
        )

    # Providing explicit determinism_level allows instantiation (security_level from factory)
    definition.update({"determinism_level": "high"})
    plugin = create_plugin_with_inheritance(
        protected_registry,
        definition,
        plugin_kind="rate_limiter",
        parent_context=parent,
        allow_none=True,
    )

    assert plugin is not None
    assert plugin.rate == 100
    assert plugin._elspeth_context.security_level == "PROTECTED"  # From factory
    assert plugin._elspeth_context.determinism_level == "high"


def test_create_plugin_experiment_plugin_pattern():
    """Helper works with experiment plugin pattern (required, explicit security).

    ADR-002-B: Security level from factory registration, not config.
    """
    parent = PluginContext(
        plugin_name="experiment",
        plugin_kind="experiment",
        security_level="PROTECTED",
        determinism_level="high",
        provenance=("experiment:test",),
    )

    # Create registry with SECRET-level plugin
    secret_registry = BasePluginRegistry[MockPlugin]("test_plugin")
    secret_registry.register("test", create_mock_plugin, schema=None, declared_security_level="SECRET")

    definition = {
        "name": "test",
        "determinism_level": "high",
        "options": {"threshold": 0.5},
    }

    plugin = create_plugin_with_inheritance(
        secret_registry,
        definition,
        plugin_kind="row_plugin",
        parent_context=parent,
        allow_none=False,  # Required
    )

    assert plugin is not None
    assert plugin.threshold == 0.5
    assert plugin._elspeth_context.security_level == "SECRET"  # From factory, not inherited
    assert plugin._elspeth_context.determinism_level == "high"
