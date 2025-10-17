from __future__ import annotations

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.utility import (
    create_named_utility,
    create_utility_plugin,
    register_utility_plugin,
    utility_plugin_registry,
)
from elspeth.core.validation import ConfigurationError


class DummyUtility:
    def __init__(self, *, context: PluginContext, options: dict[str, object]) -> None:
        self.plugin_context = context
        self.options = options


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

    try:
        plugin = create_utility_plugin(
            {
                "name": "dummy",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"foo": "bar"},
            }
        )

        assert isinstance(plugin, DummyUtility)
        assert plugin.options == {"foo": "bar"}
        assert plugin.plugin_context.plugin_name == "dummy"
        assert plugin.plugin_context.plugin_kind == "utility"
        assert plugin.plugin_context.security_level == "OFFICIAL"
        assert plugin.plugin_context.determinism_level == "guaranteed"
    finally:
        utility_plugin_registry.unregister("dummy")


def test_create_utility_plugin_conflicting_security_levels():
    register_utility_plugin("dummy", lambda options, context: DummyUtility(context=context, options=options))

    try:
        with pytest.raises(ConfigurationError):
            create_utility_plugin(
                {
                    "name": "dummy",
                    "security_level": "OFFICIAL",
                    "determinism_level": "guaranteed",
                    "options": {"security_level": "PROTECTED", "determinism_level": "guaranteed"},
                }
            )
    finally:
        utility_plugin_registry.unregister("dummy")


def test_create_named_utility_inherits_parent_context():
    register_utility_plugin("dummy", lambda options, context: DummyUtility(context=context, options=options))

    parent = PluginContext(plugin_name="suite", plugin_kind="suite", security_level="official", determinism_level="guaranteed")
    child = parent.derive(plugin_name="experiment", plugin_kind="experiment")

    try:
        plugin = create_named_utility("dummy", {"foo": "bar"}, parent_context=child)

        assert isinstance(plugin, DummyUtility)
        assert plugin.plugin_context.security_level == "OFFICIAL"  # Normalized from lowercase "official"
        assert plugin.plugin_context.determinism_level == "guaranteed"
        assert plugin.plugin_context.parent == child
        # Provenance should track that levels were inherited from parent
        assert plugin.plugin_context.provenance == (
            "utility:dummy.inherited.security_level",
            "utility:dummy.inherited.determinism_level",
        )
        assert plugin.options["foo"] == "bar"
    finally:
        utility_plugin_registry.unregister("dummy")


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

    try:
        with pytest.raises(ConfigurationError):
            create_utility_plugin(
                {
                    "name": "dummy",
                    "security_level": "OFFICIAL",
                    "determinism_level": "guaranteed",
                    "options": {},
                }
            )
    finally:
        utility_plugin_registry.unregister("dummy")
