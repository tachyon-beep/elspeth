from types import SimpleNamespace

from elspeth.config import load_settings


def test_load_settings(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: azure_blob
            security_level: official
            options:
              config_path: config/blob_store.yaml
          llm:
            plugin: azure_openai
            security_level: official
            options:
              config:
                api_version: 1
                deployment_env: TEST_DEPLOYMENT
          sinks:
            - plugin: csv
              security_level: official
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
            security_level: official
          cost_tracker:
            plugin: noop
            security_level: official
        """,
        encoding="utf-8",
    )

    import elspeth.core.registry as registry_module

    # patch registry to return simple objects
    orig_ds = registry_module.registry._datasources["azure_blob"]
    orig_llm = registry_module.registry._llms["azure_openai"]
    orig_sink = registry_module.registry._sinks["csv"]

    registry_module.registry._datasources["azure_blob"] = registry_module.PluginFactory(
        lambda options: SimpleNamespace(kind="datasource", options=options)
    )
    registry_module.registry._llms["azure_openai"] = registry_module.PluginFactory(
        lambda options: SimpleNamespace(kind="llm", options=options)
    )
    registry_module.registry._sinks["csv"] = registry_module.PluginFactory(lambda options: SimpleNamespace(kind="sink", options=options))

    try:
        settings = load_settings(config_file)
    finally:
        registry_module.registry._datasources["azure_blob"] = orig_ds
        registry_module.registry._llms["azure_openai"] = orig_llm
        registry_module.registry._sinks["csv"] = orig_sink

    assert settings.datasource.kind == "datasource"
    assert settings.llm.kind == "llm"
    assert settings.sinks[0].kind == "sink"
    assert settings.datasource._elspeth_security_level == "official"
    assert settings.llm._elspeth_security_level == "official"
    assert settings.sinks[0]._elspeth_security_level == "official"
    assert settings.orchestrator_config.llm_prompt["system"] == "sys"
    assert settings.orchestrator_config.prompt_fields == ["id"]
    assert settings.orchestrator_config.criteria[0]["name"] == "crit"
    assert settings.orchestrator_config.baseline_plugin_defs == []
    assert settings.orchestrator_config.retry_config is None
    assert settings.rate_limiter is not None
    assert settings.cost_tracker is not None


def test_load_settings_missing_prompts_defaults_to_blank(tmp_path):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: local_csv
            security_level: official
            options:
              path: input.csv
          llm:
            plugin: mock
            security_level: official
          sinks: []
        """,
        encoding="utf-8",
    )

    import elspeth.core.registry as registry_module

    orig_ds = registry_module.registry._datasources.get("local_csv")
    orig_llm = registry_module.registry._llms.get("mock")
    orig_sink = registry_module.registry._sinks.get("csv")

    registry_module.registry._datasources["local_csv"] = registry_module.PluginFactory(
        lambda options: SimpleNamespace(kind="ds", options=options)
    )
    registry_module.registry._llms["mock"] = registry_module.PluginFactory(lambda options: SimpleNamespace(kind="llm", options=options))
    registry_module.registry._sinks["csv"] = registry_module.PluginFactory(lambda options: SimpleNamespace(kind="sink", options=options))

    try:
        settings = load_settings(config_file)
    finally:
        if orig_ds is not None:
            registry_module.registry._datasources["local_csv"] = orig_ds
        if orig_llm is not None:
            registry_module.registry._llms["mock"] = orig_llm
        if orig_sink is not None:
            registry_module.registry._sinks["csv"] = orig_sink

    assert settings.orchestrator_config.llm_prompt.get("system", "") == ""
    assert settings.orchestrator_config.llm_prompt.get("user", "") == ""


def test_load_settings_prompt_pack_merges_overrides(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: local_csv
            security_level: official
            options:
              path: data.csv
          llm:
            plugin: mock
            security_level: official
          sinks:
            - plugin: csv
              security_level: official
              options:
                path: outputs/latest.csv
          prompt_pack: sample
          prompt_packs:
            sample:
              prompts:
                system: Sample sys
                user: Sample user {id}
              prompt_fields: ["id"]
              row_plugins:
                - name: pack_row
                  security_level: official
              aggregator_plugins:
                - name: pack_agg
                  security_level: official
          prompts:
            user: Inline {{ name }}
          row_plugins:
            - name: inline_row
              security_level: official
          aggregator_plugins:
            - name: inline_agg
              security_level: official
        """,
        encoding="utf-8",
    )

    import elspeth.core.registry as registry_module

    orig_ds = registry_module.registry._datasources.get("local_csv")
    orig_llm = registry_module.registry._llms.get("mock")
    orig_sink = registry_module.registry._sinks.get("csv")

    registry_module.registry._datasources["local_csv"] = registry_module.PluginFactory(
        lambda options: SimpleNamespace(kind="ds", options=options)
    )
    registry_module.registry._llms["mock"] = registry_module.PluginFactory(lambda options: SimpleNamespace(kind="llm", options=options))
    registry_module.registry._sinks["csv"] = registry_module.PluginFactory(lambda options: SimpleNamespace(kind="sink", options=options))

    try:
        settings = load_settings(config_file, profile="default")
    finally:
        if orig_ds is not None:
            registry_module.registry._datasources["local_csv"] = orig_ds
        if orig_llm is not None:
            registry_module.registry._llms["mock"] = orig_llm
        if orig_sink is not None:
            registry_module.registry._sinks["csv"] = orig_sink

    assert settings.orchestrator_config.llm_prompt["system"] == "Sample sys"
    assert settings.orchestrator_config.llm_prompt["user"] == "Inline {{ name }}"
    assert settings.orchestrator_config.prompt_fields == ["id"]
    assert settings.orchestrator_config.row_plugin_defs == [
        {"name": "pack_row", "security_level": "official"},
        {"name": "inline_row", "security_level": "official"},
    ]
    assert settings.orchestrator_config.aggregator_plugin_defs == [
        {"name": "pack_agg", "security_level": "official"},
        {"name": "inline_agg", "security_level": "official"},
    ]


def test_load_settings_suite_defaults_inherit_pack(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: local_csv
            security_level: official
            options:
              path: data.csv
          llm:
            plugin: mock
            security_level: official
          sinks: []
          prompt_packs:
            base:
              prompts:
                system: Pack system
                user: Pack user {{ id }}
              prompt_fields: ["id"]
              row_plugins:
                - name: pack_row
                  security_level: official
          suite_defaults:
            prompt_pack: base
            aggregator_plugins:
              - name: suite_agg
                security_level: official
        """,
        encoding="utf-8",
    )

    import elspeth.core.registry as registry_module

    orig_ds = registry_module.registry._datasources.get("local_csv")
    orig_llm = registry_module.registry._llms.get("mock")

    registry_module.registry._datasources["local_csv"] = registry_module.PluginFactory(
        lambda options: SimpleNamespace(kind="ds", options=options)
    )
    registry_module.registry._llms["mock"] = registry_module.PluginFactory(lambda options: SimpleNamespace(kind="llm", options=options))

    try:
        settings = load_settings(config_file)
    finally:
        if orig_ds is not None:
            registry_module.registry._datasources["local_csv"] = orig_ds
        if orig_llm is not None:
            registry_module.registry._llms["mock"] = orig_llm

    assert settings.suite_defaults["prompts"]["system"] == "Pack system"
    assert settings.suite_defaults["prompt_fields"] == ["id"]
    assert settings.suite_defaults["row_plugins"] == [{"name": "pack_row", "security_level": "official"}]
    assert settings.suite_defaults["aggregator_plugins"] == [{"name": "suite_agg", "security_level": "official"}]
