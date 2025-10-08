from pathlib import Path

from dmp.config import load_settings


def test_load_settings_with_suite(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    suite_root = tmp_path / "suite"

    config_file.write_text(
        """
        default:
          datasource:
            plugin: azure_blob
            options:
              config_path: config/blob_store.yaml
              profile: default
          llm:
            plugin: azure_openai
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

    import dmp.core.registry as registry_module

    orig_ds = registry_module.registry._datasources["azure_blob"]
    orig_llm = registry_module.registry._llms["azure_openai"]
    orig_sink = registry_module.registry._sinks["csv"]

    registry_module.registry._datasources["azure_blob"] = registry_module.PluginFactory(lambda options: ("datasource", options))
    registry_module.registry._llms["azure_openai"] = registry_module.PluginFactory(lambda options: ("llm", options))
    registry_module.registry._sinks["csv"] = registry_module.PluginFactory(lambda options: ("sink", options))

    try:
        settings = load_settings(config_file)
    finally:
        registry_module.registry._datasources["azure_blob"] = orig_ds
        registry_module.registry._llms["azure_openai"] = orig_llm
        registry_module.registry._sinks["csv"] = orig_sink

    assert settings.suite_root == suite_root
    assert settings.suite_defaults["prompt_fields"] == ["APPID"]
    assert settings.suite_defaults["rate_limiter"]["plugin"] == "fixed_window"
