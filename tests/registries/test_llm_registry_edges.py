import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.llm import create_llm_from_definition, llm_registry
from elspeth.core.validation.base import ConfigurationError


def test_static_llm_requires_content_and_respects_parent_levels():
    parent = PluginContext(
        plugin_name="root",
        plugin_kind="suite",
        security_level="OFFICIAL",
        determinism_level="high",
        provenance=("root",),
    )

    # Missing content -> ConfigurationError
    with pytest.raises(ConfigurationError):
        create_llm_from_definition({"plugin": "static_test", "options": {}}, parent_context=parent)

    # Provide content; should succeed and return plugin instance
    plugin = create_llm_from_definition(
        {"plugin": "static_test", "options": {"content": "ok"}}, parent_context=parent
    )
    assert plugin.generate(system_prompt="", user_prompt="")["content"] == "ok"


def test_create_llm_detects_conflicting_security_level():
    parent = PluginContext(
        plugin_name="root",
        plugin_kind="suite",
        security_level="OFFICIAL",
        determinism_level="high",
        provenance=("root",),
    )
    # Definition conflicts with parent security -> ConfigurationError
    with pytest.raises(ConfigurationError):
        create_llm_from_definition(
            {"plugin": "static_test", "security_level": "unofficial", "options": {"content": "x"}},
            parent_context=parent,
        )


def test_http_openai_endpoint_validation_rejects_unapproved():
    parent = PluginContext(
        plugin_name="root",
        plugin_kind="suite",
        security_level="UNOFFICIAL",
        determinism_level="low",
        provenance=("root",),
    )
    with pytest.raises(ConfigurationError):
        llm_registry.create(
            "http_openai",
            {"api_base": "https://evil.attacker.com/api", "model": "gpt"},
            parent_context=parent,
        )
