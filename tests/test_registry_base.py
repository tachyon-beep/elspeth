"""Tests for base registry framework."""

import pytest

from elspeth.core.plugin_context import PluginContext
from elspeth.core.registry import BasePluginFactory, BasePluginRegistry
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
    factory.validate({"value": "test", "number": 42}, context="test:mock")


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
    factory.validate({"value": "test", "extra": "allowed"}, context="test:mock")


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

    registry.register("mock", create_mock_plugin, schema=None)

    assert "mock" in registry.list_plugins()


def test_registry_validate(simple_schema):
    """Registry validates plugin options."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=simple_schema)

    # Valid options
    registry.validate("mock", {"value": "test", "number": 42})

    # Invalid options
    with pytest.raises(ConfigurationError):
        registry.validate("mock", {"number": 42})  # missing required 'value'


def test_registry_create():
    """Registry creates plugin with context."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=None)

    plugin = registry.create(
        name="mock",
        options={
            "value": "test",
            "number": 100,
            "security_level": "PROTECTED",
            "determinism_level": "high",
        },
        require_security=True,
        require_determinism=True,
    )

    assert isinstance(plugin, MockPlugin)
    assert plugin.value == "test"
    assert plugin.number == 100
    assert plugin._elspeth_context is not None
    assert plugin._elspeth_context.security_level == "PROTECTED"
    assert plugin._elspeth_context.determinism_level == "high"


def test_registry_create_with_parent_context(plugin_context):
    """Registry creates plugin inheriting from parent context."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=None)

    plugin = registry.create(
        name="mock",
        options={"value": "test"},
        parent_context=plugin_context,
        require_security=False,  # inherit from parent
        require_determinism=False,
    )

    assert isinstance(plugin, MockPlugin)
    assert plugin._elspeth_context is not None
    # Should inherit security level from parent
    assert plugin._elspeth_context.security_level == "OFFICIAL"


def test_registry_create_unknown_plugin():
    """Registry raises error for unknown plugin."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    with pytest.raises(ValueError, match="Unknown test_plugin plugin 'nonexistent'"):
        registry.create(
            name="nonexistent",
            options={"value": "test"},
        )


def test_registry_create_missing_security_level():
    """Registry raises error when security_level required but missing."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=None)

    with pytest.raises(ConfigurationError, match="security_level is required"):
        registry.create(
            name="mock",
            options={"value": "test"},  # no security_level
            require_security=True,
        )


def test_registry_create_missing_determinism_level():
    """Registry raises error when determinism_level required but missing."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=None)

    with pytest.raises(ConfigurationError, match="determinism_level is required"):
        registry.create(
            name="mock",
            options={
                "value": "test",
                "security_level": "OFFICIAL",
            },  # no determinism_level
            require_determinism=True,
        )


def test_registry_list_plugins():
    """Registry lists registered plugin names."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    assert registry.list_plugins() == []

    registry.register("plugin_a", create_mock_plugin)
    registry.register("plugin_c", create_mock_plugin)
    registry.register("plugin_b", create_mock_plugin)

    # Should be sorted
    assert registry.list_plugins() == ["plugin_a", "plugin_b", "plugin_c"]


def test_registry_provenance_tracking():
    """Registry tracks provenance sources correctly."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=None)

    plugin = registry.create(
        name="mock",
        options={
            "value": "test",
            "security_level": "OFFICIAL",
            "determinism_level": "high",
        },
        provenance=["custom.source"],
    )

    assert plugin._elspeth_context is not None
    assert "test_plugin:mock.options.security_level" in plugin._elspeth_context.provenance
    assert "custom.source" in plugin._elspeth_context.provenance


def test_registry_strips_framework_keys():
    """Registry strips security/determinism levels before passing to factory."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    # Create factory that checks it doesn't receive framework keys
    def strict_factory(options, context):
        assert "security_level" not in options, "Factory should not receive security_level"
        assert "determinism_level" not in options, "Factory should not receive determinism_level"
        return MockPlugin(**options)

    registry.register("mock", strict_factory, schema=None)

    # Should not raise assertion error
    plugin = registry.create(
        name="mock",
        options={
            "value": "test",
            "security_level": "OFFICIAL",
            "determinism_level": "high",
        },
    )

    assert plugin.value == "test"


def test_registry_validation_strips_framework_keys(simple_schema):
    """Registry validation strips framework keys before validation."""
    # Schema does not include security_level or determinism_level
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=simple_schema)

    # Should not raise even though schema has additionalProperties: false
    registry.validate(
        "mock",
        {
            "value": "test",
            "security_level": "OFFICIAL",
            "determinism_level": "high",
        },
    )


# Test helper methods


def test_registry_unregister():
    """Registry unregister removes a plugin."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")
    registry.register("mock", create_mock_plugin, schema=None)

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
    registry.register("plugin_a", create_mock_plugin)
    registry.register("plugin_b", create_mock_plugin)
    registry.register("plugin_c", create_mock_plugin)

    assert len(registry.list_plugins()) == 3

    registry.clear()

    assert len(registry.list_plugins()) == 0


def test_registry_temporary_override():
    """Registry temporary_override temporarily replaces a plugin."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    # Register original plugin
    registry.register("mock", create_mock_plugin, schema=None)

    # Create mock factory that returns different value
    def mock_factory(options, context):
        plugin = MockPlugin(**options)
        plugin.mocked = True
        return plugin

    # Original plugin works
    plugin = registry.create("mock", {"value": "original", "security_level": "OFFICIAL", "determinism_level": "high"})
    assert plugin.value == "original"
    assert not hasattr(plugin, "mocked")

    # Override temporarily
    with registry.temporary_override("mock", mock_factory):
        plugin = registry.create("mock", {"value": "overridden", "security_level": "OFFICIAL", "determinism_level": "high"})
        assert plugin.value == "overridden"
        assert plugin.mocked is True

    # Original restored
    plugin = registry.create("mock", {"value": "restored", "security_level": "OFFICIAL", "determinism_level": "high"})
    assert plugin.value == "restored"
    assert not hasattr(plugin, "mocked")


def test_registry_temporary_override_new_plugin():
    """Registry temporary_override works for new plugins."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    def temp_factory(options, context):
        return MockPlugin(**options)

    # Plugin doesn't exist initially
    assert "temp_plugin" not in registry.list_plugins()

    # Override creates it temporarily
    with registry.temporary_override("temp_plugin", temp_factory):
        assert "temp_plugin" in registry.list_plugins()
        plugin = registry.create("temp_plugin", {"value": "temp", "security_level": "OFFICIAL", "determinism_level": "high"})
        assert plugin.value == "temp"

    # Plugin removed after context
    assert "temp_plugin" not in registry.list_plugins()


def test_registry_temporary_override_exception_handling():
    """Registry temporary_override restores original even on exception."""
    registry = BasePluginRegistry[MockPlugin]("test_plugin")

    # Register original
    registry.register("mock", create_mock_plugin, schema=None)

    def mock_factory(options, context):
        plugin = MockPlugin(**options)
        plugin.mocked = True
        return plugin

    # Override and raise exception
    with pytest.raises(ValueError):
        with registry.temporary_override("mock", mock_factory):
            # Override is active
            plugin = registry.create("mock", {"value": "test", "security_level": "OFFICIAL", "determinism_level": "high"})
            assert plugin.mocked is True
            # Raise exception
            raise ValueError("Test exception")

    # Original still restored despite exception
    plugin = registry.create("mock", {"value": "restored", "security_level": "OFFICIAL", "determinism_level": "high"})
    assert not hasattr(plugin, "mocked")
