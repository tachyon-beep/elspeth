from types import SimpleNamespace

import pytest

from elspeth.config import load_settings


def test_load_settings_with_suite(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    suite_root = tmp_path / "suite"

    config_file.write_text(
        """
        default:
          datasource:
            plugin: azure_blob
            security_level: OFFICIAL
            determinism_level: guaranteed
            options:
              config_path: config/blob_store.yaml
              profile: default
          llm:
            plugin: azure_openai
            security_level: OFFICIAL
            determinism_level: guaranteed
            options:
              config: {}
          sinks: []
          prompts: { system: sys, user: user }
          suite_root: "SUITE_ROOT"
          suite_defaults:
            prompt_fields: ["APPID"]
            rate_limiter:
              plugin: fixed_window
              options: {requests: 1, per_seconds: 1}
            cost_tracker:
              plugin: fixed_price
              options: {prompt_token_price: 0.01}
        """.replace("SUITE_ROOT", suite_root.as_posix()),
        encoding="utf-8",
    )

    import elspeth.core.registry as registry_module

    orig_ds = registry_module.registry._datasources["azure_blob"]
    orig_llm = registry_module.registry._llms["azure_openai"]
    orig_sink = registry_module.registry._sinks["csv"]

    registry_module.registry._datasources["azure_blob"] = registry_module.PluginFactory(
        lambda options, context: SimpleNamespace(kind="datasource", options=options, context=context)
    )
    registry_module.registry._llms["azure_openai"] = registry_module.PluginFactory(
        lambda options, context: SimpleNamespace(kind="llm", options=options, context=context)
    )
    registry_module.registry._sinks["csv"] = registry_module.PluginFactory(
        lambda options, context: SimpleNamespace(kind="sink", options=options, context=context)
    )

    try:
        settings = load_settings(config_file)
    finally:
        registry_module.registry._datasources["azure_blob"] = orig_ds
        registry_module.registry._llms["azure_openai"] = orig_llm
        registry_module.registry._sinks["csv"] = orig_sink

    assert settings.suite_root == suite_root
    assert settings.suite_defaults["prompt_fields"] == ["APPID"]
    assert settings.suite_defaults["rate_limiter"]["plugin"] == "fixed_window"


def test_suite_defaults_override_prompt_pack_when_missing(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    suite_root = tmp_path / "suite"

    config_file.write_text(
        """
        default:
          datasource:
            plugin: local_csv
            security_level: OFFICIAL
            determinism_level: guaranteed
            options:
              path: input.csv
          llm:
            plugin: mock
            security_level: OFFICIAL
            determinism_level: guaranteed
          sinks: []
          prompt_packs:
            sample:
              prompts:
                system: Sample sys
                user: Sample user {{ id }}
              prompt_fields: ["id"]
          suite_root: "SUITE_ROOT"
          suite_defaults:
            prompt_pack: sample
            prompts:
              system: Inline system
        """.replace("SUITE_ROOT", suite_root.as_posix()),
        encoding="utf-8",
    )

    import elspeth.core.registry as registry_module

    orig_ds = registry_module.registry._datasources.get("local_csv")
    orig_llm = registry_module.registry._llms.get("mock")

    registry_module.registry._datasources["local_csv"] = registry_module.PluginFactory(
        lambda options, context: SimpleNamespace(kind="ds", options=options, context=context)
    )
    registry_module.registry._llms["mock"] = registry_module.PluginFactory(
        lambda options, context: SimpleNamespace(kind="llm", options=options, context=context)
    )

    try:
        settings = load_settings(config_file)
    finally:
        if orig_ds is not None:
            registry_module.registry._datasources["local_csv"] = orig_ds
        if orig_llm is not None:
            registry_module.registry._llms["mock"] = orig_llm
    assert settings.suite_defaults["prompts"]["system"] == "Inline system"
    assert settings.suite_defaults["prompt_fields"] == ["id"]


def test_load_settings_unknown_datasource_plugin_raises(tmp_path):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: missing_source
            security_level: OFFICIAL
            determinism_level: guaranteed
          llm:
            plugin: mock
            security_level: OFFICIAL
            determinism_level: guaranteed
          sinks: []
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_settings(config_file)
