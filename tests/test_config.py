import yaml

from dmp.config import load_settings


def test_load_settings(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: azure_blob
            options:
              config_path: config/blob_store.yaml
          llm:
            plugin: azure_openai
            options:
              config:
                api_version: 1
                deployment_env: TEST_DEPLOYMENT
          sinks:
            - plugin: csv
              options:
                path: outputs.csv
          prompts:
            system: sys
            user: user
          prompt_fields:
            - id
          criteria:
            - name: crit
              template: crit {id}
          rate_limiter:
            plugin: noop
          cost_tracker:
            plugin: noop
        """,
        encoding="utf-8",
    )

    import dmp.core.registry as registry_module

    # patch registry to return simple objects
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

    assert settings.datasource[0] == "datasource"
    assert settings.llm[0] == "llm"
    assert settings.sinks[0][0] == "sink"
    assert settings.orchestrator_config.llm_prompt["system"] == "sys"
    assert settings.orchestrator_config.prompt_fields == ["id"]
    assert settings.orchestrator_config.criteria[0]["name"] == "crit"
    assert settings.orchestrator_config.baseline_plugin_defs == []
    assert settings.orchestrator_config.retry_config is None
    assert settings.rate_limiter is not None
    assert settings.cost_tracker is not None
