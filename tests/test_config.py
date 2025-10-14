from types import SimpleNamespace

from elspeth.config import load_settings
from elspeth.core.datasource_registry import datasource_registry
from elspeth.core.llm_registry import llm_registry
from elspeth.core.sink_registry import sink_registry
from elspeth.core.registry.base import BasePluginFactory


def test_load_settings(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: azure_blob
            security_level: OFFICIAL
            determinism_level: guaranteed
            options:
              config_path: config/blob_store.yaml
          llm:
            plugin: azure_openai
            security_level: OFFICIAL
            determinism_level: guaranteed
            options:
              config:
                api_version: 1
                deployment_env: TEST_DEPLOYMENT
          sinks:
            - plugin: csv
              security_level: OFFICIAL
              determinism_level: guaranteed
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
            security_level: OFFICIAL
            determinism_level: guaranteed
          cost_tracker:
            plugin: noop
            security_level: OFFICIAL
            determinism_level: guaranteed
        """,
        encoding="utf-8",
    )

    # patch registries to return simple objects
    orig_ds = datasource_registry._plugins["azure_blob"]
    orig_llm = llm_registry._plugins["azure_openai"]
    orig_sink = sink_registry._plugins["csv"]

    datasource_registry._plugins["azure_blob"] = BasePluginFactory(
        lambda options, context: SimpleNamespace(kind="datasource", options=options, context=context)
    )
    llm_registry._plugins["azure_openai"] = BasePluginFactory(
        lambda options, context: SimpleNamespace(kind="llm", options=options, context=context)
    )
    sink_registry._plugins["csv"] = BasePluginFactory(
        lambda options, context: SimpleNamespace(kind="sink", options=options, context=context)
    )

    try:
        settings = load_settings(config_file)
    finally:
        datasource_registry._plugins["azure_blob"] = orig_ds
        llm_registry._plugins["azure_openai"] = orig_llm
        sink_registry._plugins["csv"] = orig_sink

    assert settings.datasource.kind == "datasource"
    assert settings.llm.kind == "llm"
    assert settings.sinks[0].kind == "sink"
    assert settings.datasource._elspeth_security_level == "OFFICIAL"
    assert settings.llm._elspeth_security_level == "OFFICIAL"
    assert settings.sinks[0]._elspeth_security_level == "OFFICIAL"
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
            security_level: OFFICIAL
            determinism_level: guaranteed
            options:
              path: input.csv
          llm:
            plugin: mock
            security_level: OFFICIAL
            determinism_level: guaranteed
          sinks: []
        """,
        encoding="utf-8",
    )

    orig_ds = datasource_registry._plugins.get("local_csv")
    orig_llm = llm_registry._plugins.get("mock")
    orig_sink = sink_registry._plugins.get("csv")

    datasource_registry._plugins["local_csv"] = BasePluginFactory(
        lambda options, context: SimpleNamespace(kind="ds", options=options, context=context)
    )
    llm_registry._plugins["mock"] = BasePluginFactory(
        lambda options, context: SimpleNamespace(kind="llm", options=options, context=context)
    )
    sink_registry._plugins["csv"] = BasePluginFactory(
        lambda options, context: SimpleNamespace(kind="sink", options=options, context=context)
    )

    try:
        settings = load_settings(config_file)
    finally:
        if orig_ds is not None:
            datasource_registry._plugins["local_csv"] = orig_ds
        if orig_llm is not None:
            llm_registry._plugins["mock"] = orig_llm
        if orig_sink is not None:
            sink_registry._plugins["csv"] = orig_sink

    assert settings.orchestrator_config.llm_prompt.get("system", "") == ""
    assert settings.orchestrator_config.llm_prompt.get("user", "") == ""


def test_load_settings_prompt_pack_merges_overrides(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: local_csv
            security_level: OFFICIAL
            determinism_level: guaranteed
            options:
              path: data.csv
          llm:
            plugin: mock
            security_level: OFFICIAL
            determinism_level: guaranteed
          sinks:
            - plugin: csv
              security_level: OFFICIAL
              determinism_level: guaranteed
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
                  security_level: OFFICIAL
                  determinism_level: guaranteed
              aggregator_plugins:
                - name: pack_agg
                  security_level: OFFICIAL
                  determinism_level: guaranteed
          prompts:
            user: Inline {{ name }}
          row_plugins:
            - name: inline_row
              security_level: OFFICIAL
              determinism_level: guaranteed
          aggregator_plugins:
            - name: inline_agg
              security_level: OFFICIAL
              determinism_level: guaranteed
        """,
        encoding="utf-8",
    )

    orig_ds = datasource_registry._plugins.get("local_csv")
    orig_llm = llm_registry._plugins.get("mock")
    orig_sink = sink_registry._plugins.get("csv")

    datasource_registry._plugins["local_csv"] = BasePluginFactory(
        lambda options, context: SimpleNamespace(kind="ds", options=options, context=context)
    )
    llm_registry._plugins["mock"] = BasePluginFactory(
        lambda options, context: SimpleNamespace(kind="llm", options=options, context=context)
    )
    sink_registry._plugins["csv"] = BasePluginFactory(
        lambda options, context: SimpleNamespace(kind="sink", options=options, context=context)
    )

    try:
        settings = load_settings(config_file, profile="default")
    finally:
        if orig_ds is not None:
            datasource_registry._plugins["local_csv"] = orig_ds
        if orig_llm is not None:
            llm_registry._plugins["mock"] = orig_llm
        if orig_sink is not None:
            sink_registry._plugins["csv"] = orig_sink

    assert settings.orchestrator_config.llm_prompt["system"] == "Sample sys"
    assert settings.orchestrator_config.llm_prompt["user"] == "Inline {{ name }}"
    assert settings.orchestrator_config.prompt_fields == ["id"]
    assert settings.orchestrator_config.row_plugin_defs == [
        {"name": "pack_row", "security_level": "OFFICIAL", "determinism_level": "guaranteed"},
        {"name": "inline_row", "security_level": "OFFICIAL", "determinism_level": "guaranteed"},
    ]
    assert settings.orchestrator_config.aggregator_plugin_defs == [
        {"name": "pack_agg", "security_level": "OFFICIAL", "determinism_level": "guaranteed"},
        {"name": "inline_agg", "security_level": "OFFICIAL", "determinism_level": "guaranteed"},
    ]


def test_load_settings_suite_defaults_inherit_pack(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: local_csv
            security_level: OFFICIAL
            determinism_level: guaranteed
            options:
              path: data.csv
          llm:
            plugin: mock
            security_level: OFFICIAL
            determinism_level: guaranteed
          sinks: []
          prompt_packs:
            base:
              prompts:
                system: Pack system
                user: Pack user {{ id }}
              prompt_fields: ["id"]
              row_plugins:
                - name: pack_row
                  security_level: OFFICIAL
                  determinism_level: guaranteed
          suite_defaults:
            prompt_pack: base
            aggregator_plugins:
              - name: suite_agg
                security_level: OFFICIAL
                determinism_level: guaranteed
        """,
        encoding="utf-8",
    )

    orig_ds = datasource_registry._plugins.get("local_csv")
    orig_llm = llm_registry._plugins.get("mock")

    datasource_registry._plugins["local_csv"] = BasePluginFactory(
        lambda options, context: SimpleNamespace(kind="ds", options=options, context=context)
    )
    llm_registry._plugins["mock"] = BasePluginFactory(
        lambda options, context: SimpleNamespace(kind="llm", options=options, context=context)
    )

    try:
        settings = load_settings(config_file)
    finally:
        if orig_ds is not None:
            datasource_registry._plugins["local_csv"] = orig_ds
        if orig_llm is not None:
            llm_registry._plugins["mock"] = orig_llm

    assert settings.suite_defaults["prompts"]["system"] == "Pack system"
    assert settings.suite_defaults["prompt_fields"] == ["id"]
    assert settings.suite_defaults["row_plugins"] == [{"name": "pack_row", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}]
    assert settings.suite_defaults["aggregator_plugins"] == [
        {"name": "suite_agg", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}
    ]
