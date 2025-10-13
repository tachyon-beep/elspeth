"""Tests for base registry framework."""

import pytest

from elspeth.core.plugins import PluginContext
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
        security_level="internal",
        determinism_level="deterministic",
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

    with pytest.raises(ConfigurationError, match="value.*required"):
        factory.validate({"number": 42}, context="test:mock")


def test_factory_validation_extra_properties(simple_schema):
    """Factory rejects extra properties when schema disallows them."""
    factory = BasePluginFactory(
        create=create_mock_plugin,
        schema=simple_schema,
        plugin_type="test",
    )

    with pytest.raises(ConfigurationError):
        factory.validate(
            {"value": "test", "extra": "not_allowed"},
            context="test:mock"
        )


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
            "security_level": "confidential",
            "determinism_level": "deterministic",
        },
        require_security=True,
        require_determinism=True,
    )

    assert isinstance(plugin, MockPlugin)
    assert plugin.value == "test"
    assert plugin.number == 100
    assert plugin._elspeth_context is not None
    assert plugin._elspeth_context.security_level == "confidential"
    assert plugin._elspeth_context.determinism_level == "deterministic"


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
    assert plugin._elspeth_context.security_level == "internal"


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
                "security_level": "internal",
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
            "security_level": "internal",
            "determinism_level": "deterministic",
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
            "security_level": "internal",
            "determinism_level": "deterministic",
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
            "security_level": "internal",
            "determinism_level": "deterministic",
        },
    )
