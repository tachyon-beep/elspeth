from __future__ import annotations

import pytest

from elspeth.core.plugins import PluginContext
from elspeth.core.utilities import create_named_utility, create_utility_plugin, register_utility_plugin
from elspeth.core.validation import ConfigurationError


class DummyUtility:
    def __init__(self, *, context: PluginContext, options: dict[str, object]) -> None:
        self.plugin_context = context
        self.options = options


@pytest.fixture(autouse=True)
def reset_registry():
    """Ensure registry state is isolated between tests."""

    from elspeth.core.utilities import plugin_registry

    original = dict(plugin_registry._utility_plugins)
    plugin_registry._utility_plugins.clear()
    try:
        yield
    finally:
        plugin_registry._utility_plugins.clear()
        plugin_registry._utility_plugins.update(original)


def test_create_utility_plugin_with_schema_validation():
    register_utility_plugin(
        "dummy",
        lambda options, context: DummyUtility(context=context, options=options),
        schema={
            "type": "object",
            "properties": {"foo": {"type": "string"}},
            "required": ["foo"],
            "additionalProperties": False,
        },
    )

    plugin = create_utility_plugin(
        {
            "name": "dummy",
            "security_level": "official",
            "options": {"foo": "bar"},
        }
    )

    assert isinstance(plugin, DummyUtility)
    assert plugin.options == {"foo": "bar"}
    assert plugin.plugin_context.plugin_name == "dummy"
    assert plugin.plugin_context.plugin_kind == "utility"
    assert plugin.plugin_context.security_level == "official"


def test_create_utility_plugin_conflicting_security_levels():
    register_utility_plugin("dummy", lambda options, context: DummyUtility(context=context, options=options))

    with pytest.raises(ConfigurationError):
        create_utility_plugin(
            {
                "name": "dummy",
                "security_level": "official",
                "options": {"security_level": "protected"},
            }
        )


def test_create_named_utility_inherits_parent_context():
    register_utility_plugin("dummy", lambda options, context: DummyUtility(context=context, options=options))

    parent = PluginContext(plugin_name="suite", plugin_kind="suite", security_level="official")
    child = parent.derive(plugin_name="experiment", plugin_kind="experiment")

    plugin = create_named_utility("dummy", {"foo": "bar"}, parent_context=child)

    assert isinstance(plugin, DummyUtility)
    assert plugin.plugin_context.security_level == "official"
    assert plugin.plugin_context.parent == child
    assert plugin.plugin_context.provenance == ("utility:dummy.resolved",)
    assert plugin.options["foo"] == "bar"


def test_create_utility_plugin_missing_required_field_raises():
    register_utility_plugin(
        "dummy",
        lambda options, context: DummyUtility(context=context, options=options),
        schema={
            "type": "object",
            "properties": {"foo": {"type": "string"}},
            "required": ["foo"],
        },
    )

    with pytest.raises(ConfigurationError):
        create_utility_plugin(
            {
                "name": "dummy",
                "security_level": "official",
                "options": {},
            }
        )
