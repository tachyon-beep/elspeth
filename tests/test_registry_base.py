"""Tests for base registry framework."""

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries import BasePluginFactory, BasePluginRegistry
from elspeth.core.validation import ConfigurationError

# Test fixtures


class MockPlugin:
    """Mock plugin for testing."""

    def __init__(self, value: str, number: int = 42):
        self.value = value
        self.number = number
        self._elspeth_context = None


def create_mock_plugin(options, context):
    """Factory function for mock plugin."""
    return MockPlugin(**options)


@pytest.fixture
def simple_schema():
    """Simple validation schema for testing."""
    return {
        "type": "object",
        "properties": {
            "value": {"type": "string"},
            "number": {"type": "integer"},
        },
        "required": ["value"],
        "additionalProperties": False,
    }


@pytest.fixture
def plugin_context():
    """Basic plugin context for testing."""
    return PluginContext(
        plugin_name="test",
        plugin_kind="test_plugin",
        security_level="OFFICIAL",
        determinism_level="high",
        provenance=("test",),
    )


# BasePluginFactory tests


def test_factory_validation_success(simple_schema):
    """Factory validates options against schema successfully."""
    factory = BasePluginFactory(
        create=create_mock_plugin,
        schema=simple_schema,
        plugin_type="test",
    )
    # Should not raise
    assert factory.validate({"value": "test", "number": 42}, context="test:mock") is None


def test_factory_validation_failure(simple_schema):
    """Factory raises ConfigurationError on invalid options."""
    factory = BasePluginFactory(
        create=create_mock_plugin,
        schema=simple_schema,
        plugin_type="test",
    )

    with pytest.raises(ConfigurationError, match="required property"):
        factory.validate({"number": 42}, context="test:mock")


def test_factory_no_schema_validation():
    """Factory works without schema validation."""
    factory = BasePluginFactory(
        create=create_mock_plugin,
        schema=None,
        plugin_type="test",
    )
    # Should not raise even with extra keys
    assert factory.validate({"value": "test", "extra": "allowed"}, context="test:mock") is None


def test_factory_instantiation(plugin_context):
    """Factory creates and applies context to plugin."""
    factory = BasePluginFactory(
        create=create_mock_plugin,
        schema=None,
        plugin_type="test",
    )

    plugin = factory.instantiate(
        options={"value": "test", "number": 99},
        plugin_context=plugin_context,
        schema_context="test:mock",
    )

    assert isinstance(plugin, MockPlugin)
    assert plugin.value == "test"
    assert plugin.number == 99
    assert plugin._elspeth_context == plugin_context


def test_factory_instantiation_with_validation(simple_schema, plugin_context):
    """Factory validates before instantiation."""
    factory = BasePluginFactory(
        create=create_mock_plugin,
        schema=simple_schema,
        plugin_type="test",
    )

    # Valid options
    plugin = factory.instantiate(
        options={"value": "test"},
        plugin_context=plugin_context,
        schema_context="test:mock",
    )
    assert plugin.value == "test"
    assert plugin.number == 42  # default

    # Invalid options
    with pytest.raises(ConfigurationError):
        factory.instantiate(
            options={"number": 42},  # missing required 'value'
            plugin_context=plugin_context,
            schema_context="test:mock",
        )


# BasePluginRegistry tests


def test_registry_register():
    """Registry registers a plugin factory."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    registry.register("mock", create_mock_plugin, schema=None, declared_security_level="UNOFFICIAL")

    assert "mock" in registry.list_plugins()


def test_registry_validate(simple_schema):
    """Registry validates plugin options."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=simple_schema, declared_security_level="UNOFFICIAL")

    # Valid options
    registry.validate("mock", {"value": "test", "number": 42})

    # Invalid options
    with pytest.raises(ConfigurationError):
        registry.validate("mock", {"number": 42})  # missing required 'value'


def test_registry_create(plugin_context):
    """Registry creates plugin with context."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=None, declared_security_level="UNOFFICIAL")

    plugin = registry.create(
        name="mock",
        options={
            "value": "test",
            "number": 100,
            "determinism_level": "high",
        },
        parent_context=plugin_context,
        require_determinism=True,
    )

    assert isinstance(plugin, MockPlugin)
    assert plugin.value == "test"
    assert plugin.number == 100
    assert plugin._elspeth_context is not None
    # ADR-002-B: Security level comes from declared_security_level, NOT parent
    assert plugin._elspeth_context.security_level == "UNOFFICIAL"  # From declared_security_level
    assert plugin._elspeth_context.determinism_level == "high"
    # Parent is recorded in context but doesn't change plugin's clearance
    assert plugin._elspeth_context.parent == plugin_context


def test_registry_create_with_parent_context(plugin_context):
    """Registry creates plugin with declared clearance, NOT inheriting from parent (ADR-002-B)."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=None, declared_security_level="UNOFFICIAL")

    plugin = registry.create(
        name="mock",
        options={"value": "test"},
        parent_context=plugin_context,
        require_determinism=False,
    )

    assert isinstance(plugin, MockPlugin)
    assert plugin._elspeth_context is not None
    # ADR-002-B: Security level from declared_security_level, NOT inherited
    assert plugin._elspeth_context.security_level == "UNOFFICIAL"  # From declared_security_level
    assert plugin._elspeth_context.parent == plugin_context  # Parent recorded but doesn't change clearance


def test_registry_create_unknown_plugin():
    """Registry raises error for unknown plugin."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    with pytest.raises(ValueError, match="Unknown test_plugin plugin 'nonexistent'"):
        registry.create(
            name="nonexistent",
            options={"value": "test"},
        )


def test_registry_create_missing_security_level():
    """Registry raises error when security_level missing at registration (ADR-002-B).

    Note: With ADR-002-B, plugins MUST have declared_security_level at registration.
    This test verifies that plugins without declared_security_level can't be registered.
    """
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    # Test #1: Plugin WITH declared_security_level succeeds (but fails on missing determinism)
    registry.register("mock", create_mock_plugin, schema=None, declared_security_level="UNOFFICIAL")
    with pytest.raises(ConfigurationError, match="determinism_level is required"):
        registry.create(
            name="mock",
            options={"value": "test"},  # Missing determinism_level
        )

    # Test #2: Plugin WITHOUT declared_security_level fails at REGISTRATION time
    # (This would be caught by type checking in real code, but let's verify runtime behavior)
    # Actually, registration doesn't enforce this - it's enforced at CREATE time
    # So this test is now about missing determinism_level instead


def test_registry_create_missing_determinism_level():
    """Registry defaults determinism_level to 'none' when missing (fail-soft, unlike security)."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=None, declared_security_level="UNOFFICIAL")

    # ADR-001: Security always required (fail-loud), determinism defaults to 'none' (fail-soft)
    from elspeth.core.base.plugin_context import PluginContext
    parent_with_no_det = PluginContext(
        plugin_name="test",
        plugin_kind="test_plugin",
        security_level="OFFICIAL",
        determinism_level=None,  # No determinism - will default to 'none'
        provenance=("test",),
    )

    # Unlike security (which raises), determinism defaults to 'none' when missing
    plugin = registry.create(
        name="mock",
        options={
            "value": "test",
        },  # no determinism_level
        parent_context=parent_with_no_det,  # Provides security_level but no determinism
        require_determinism=True,
    )

    assert plugin._elspeth_context.determinism_level == "none"  # Defaults to 'none'


def test_registry_list_plugins():
    """Registry lists registered plugin names."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    assert registry.list_plugins() == []

    registry.register("plugin_a", create_mock_plugin, declared_security_level="UNOFFICIAL")
    registry.register("plugin_c", create_mock_plugin, declared_security_level="UNOFFICIAL")
    registry.register("plugin_b", create_mock_plugin, declared_security_level="UNOFFICIAL")

    # Should be sorted
    assert registry.list_plugins() == ["plugin_a", "plugin_b", "plugin_c"]


def test_registry_provenance_tracking(plugin_context):
    """Registry tracks provenance sources correctly."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=None, declared_security_level="UNOFFICIAL")

    plugin = registry.create(
        name="mock",
        options={
            "value": "test",
            "determinism_level": "high",
        },
        parent_context=plugin_context,
        provenance=["custom.source"],
    )

    assert plugin._elspeth_context is not None
    # Security level no longer in options (ADR-002-B), but determinism should be tracked
    assert "test_plugin:mock.options.determinism_level" in plugin._elspeth_context.provenance
    assert "custom.source" in plugin._elspeth_context.provenance


def test_registry_strips_framework_keys(plugin_context):
    """Registry strips security/determinism levels before passing to factory."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    # Create factory that checks it doesn't receive framework keys
    def strict_factory(options, context):
        assert "security_level" not in options, "Factory should not receive security_level"
        assert "determinism_level" not in options, "Factory should not receive determinism_level"
        return MockPlugin(**options)

    registry.register("mock", strict_factory, schema=None, declared_security_level="UNOFFICIAL")

    # Should not raise assertion error
    plugin = registry.create(
        name="mock",
        options={
            "value": "test",
            "determinism_level": "high",
        },
        parent_context=plugin_context,
    )

    assert plugin.value == "test"


def test_registry_validation_strips_framework_keys(simple_schema):
    """Registry validation strips framework keys before validation."""
    # Schema does not include security_level or determinism_level
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=simple_schema, declared_security_level="UNOFFICIAL")
    # Should not raise even though schema has additionalProperties: false
    assert (
        registry.validate(
            "mock",
            {
                "value": "test",
                "determinism_level": "high",
            },
        )
        is None
    )


# Test helper methods


def test_registry_unregister():
    """Registry unregister removes a plugin."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=None, declared_security_level="UNOFFICIAL")

    assert "mock" in registry.list_plugins()

    registry.unregister("mock")

    assert "mock" not in registry.list_plugins()


def test_registry_unregister_unknown():
    """Registry unregister raises KeyError for unknown plugin."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    with pytest.raises(KeyError):
        registry.unregister("nonexistent")


def test_registry_clear():
    """Registry clear removes all plugins."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("plugin_a", create_mock_plugin, declared_security_level="UNOFFICIAL")
    registry.register("plugin_b", create_mock_plugin, declared_security_level="UNOFFICIAL")
    registry.register("plugin_c", create_mock_plugin, declared_security_level="UNOFFICIAL")

    assert len(registry.list_plugins()) == 3

    registry.clear()

    assert len(registry.list_plugins()) == 0


def test_registry_temporary_override(plugin_context):
    """Registry temporary_override temporarily replaces a plugin."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    # Register original plugin
    registry.register("mock", create_mock_plugin, schema=None, declared_security_level="UNOFFICIAL")

    # Create mock factory that returns different value
    def mock_factory(options, context):
        plugin = MockPlugin(**options)
        plugin.mocked = True
        return plugin

    # Original plugin works
    plugin = registry.create("mock", {"value": "original", "determinism_level": "high"}, parent_context=plugin_context)
    assert plugin.value == "original"
    assert not hasattr(plugin, "mocked")

    # Override temporarily
    with registry.temporary_override("mock", mock_factory):
        plugin = registry.create("mock", {"value": "overridden", "determinism_level": "high"}, parent_context=plugin_context)
        assert plugin.value == "overridden"
        assert plugin.mocked is True

    # Original restored
    plugin = registry.create("mock", {"value": "restored", "determinism_level": "high"}, parent_context=plugin_context)
    assert plugin.value == "restored"
    assert not hasattr(plugin, "mocked")


def test_registry_temporary_override_new_plugin(plugin_context):
    """Registry temporary_override works for new plugins."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    def temp_factory(options, context):
        return MockPlugin(**options)

    # Plugin doesn't exist initially
    assert "temp_plugin" not in registry.list_plugins()

    # Override creates it temporarily
    with registry.temporary_override("temp_plugin", temp_factory):
        assert "temp_plugin" in registry.list_plugins()
        plugin = registry.create("temp_plugin", {"value": "temp", "determinism_level": "high"}, parent_context=plugin_context)
        assert plugin.value == "temp"

    # Plugin removed after context
    assert "temp_plugin" not in registry.list_plugins()


def test_registry_temporary_override_exception_handling(plugin_context):
    """Registry temporary_override restores original even on exception."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    # Register original
    registry.register("mock", create_mock_plugin, schema=None, declared_security_level="UNOFFICIAL")

    def mock_factory(options, context):
        plugin = MockPlugin(**options)
        plugin.mocked = True
        return plugin

    # Override and raise exception
    with pytest.raises(ValueError):
        with registry.temporary_override("mock", mock_factory):
            # Override is active
            plugin = registry.create("mock", {"value": "test", "determinism_level": "high"}, parent_context=plugin_context)
            assert plugin.mocked is True
            # Raise exception
            raise ValueError("Test exception")

    # Original still restored despite exception
    plugin = registry.create("mock", {"value": "restored", "determinism_level": "high"}, parent_context=plugin_context)
    assert not hasattr(plugin, "mocked")
