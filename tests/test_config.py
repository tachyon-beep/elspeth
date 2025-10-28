from contextlib import ExitStack, contextmanager
from types import SimpleNamespace

from elspeth.config import load_settings
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.registries.llm import llm_registry
from elspeth.core.registries.sink import sink_registry


@contextmanager
def registry_overrides(overrides):
    """Temporarily override plugin registries without mutating global state."""
    with ExitStack() as stack:
        for registry, name, factory in overrides:
            stack.enter_context(registry.temporary_override(name, factory))
        yield


def test_load_settings(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: azure_blob
            determinism_level: guaranteed
            options:
              config_path: config/blob_store.yaml
          llm:
            plugin: azure_openai
            determinism_level: guaranteed
            options:
              config:
                api_version: 1
                deployment_env: TEST_DEPLOYMENT
          sinks:
            - plugin: csv
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
            determinism_level: guaranteed
          cost_tracker:
            plugin: noop
            determinism_level: guaranteed
        """,
        encoding="utf-8",
    )

    with registry_overrides(
        [
            (
                datasource_registry,
                "azure_blob",
                lambda options, context: SimpleNamespace(kind="datasource", options=options, context=context),
            ),
            (
                llm_registry,
                "azure_openai",
                lambda options, context: SimpleNamespace(kind="llm", options=options, context=context),
            ),
            (
                sink_registry,
                "csv",
                lambda options, context: SimpleNamespace(kind="sink", options=options, context=context),
            ),
        ]
    ):
        settings = load_settings(config_file)

    assert settings.datasource.kind == "datasource"
    assert settings.llm.kind == "llm"
    assert settings.sinks[0].kind == "sink"
    # ADR-002-B: security_level comes from plugin's declared_security_level
    # Mock overrides now inherit declared_security_level from original registration
    assert settings.datasource._elspeth_security_level == "UNOFFICIAL"  # azure_blob default
    assert settings.llm._elspeth_security_level == "PROTECTED"  # azure_openai default
    assert settings.sinks[0]._elspeth_security_level == "UNOFFICIAL"  # csv default
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
            determinism_level: guaranteed
            options:
              path: input.csv
          llm:
            plugin: mock
            determinism_level: guaranteed
          sinks: []
        """,
        encoding="utf-8",
    )

    with registry_overrides(
        [
            (
                datasource_registry,
                "local_csv",
                lambda options, context: SimpleNamespace(kind="ds", options=options, context=context),
            ),
            (
                llm_registry,
                "mock",
                lambda options, context: SimpleNamespace(kind="llm", options=options, context=context),
            ),
            (
                sink_registry,
                "csv",
                lambda options, context: SimpleNamespace(kind="sink", options=options, context=context),
            ),
        ]
    ):
        settings = load_settings(config_file)

    assert settings.orchestrator_config.llm_prompt.get("system", "") == ""
    assert settings.orchestrator_config.llm_prompt.get("user", "") == ""


def test_load_settings_prompt_pack_merges_overrides(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: local_csv
            determinism_level: guaranteed
            options:
              path: data.csv
          llm:
            plugin: mock
            determinism_level: guaranteed
          sinks:
            - plugin: csv
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
                  determinism_level: guaranteed
              aggregator_plugins:
                - name: pack_agg
                  determinism_level: guaranteed
          prompts:
            user: Inline {{ name }}
          row_plugins:
            - name: inline_row
              determinism_level: guaranteed
          aggregator_plugins:
            - name: inline_agg
              determinism_level: guaranteed
        """,
        encoding="utf-8",
    )

    with registry_overrides(
        [
            (
                datasource_registry,
                "local_csv",
                lambda options, context: SimpleNamespace(kind="ds", options=options, context=context),
            ),
            (
                llm_registry,
                "mock",
                lambda options, context: SimpleNamespace(kind="llm", options=options, context=context),
            ),
            (
                sink_registry,
                "csv",
                lambda options, context: SimpleNamespace(kind="sink", options=options, context=context),
            ),
        ]
    ):
        settings = load_settings(config_file, profile="default")

    assert settings.orchestrator_config.llm_prompt["system"] == "Sample sys"
    assert settings.orchestrator_config.llm_prompt["user"] == "Inline {{ name }}"
    assert settings.orchestrator_config.prompt_fields == ["id"]
    assert settings.orchestrator_config.row_plugin_defs == [
        {"name": "pack_row", "determinism_level": "guaranteed"},
        {"name": "inline_row", "determinism_level": "guaranteed"},
    ]
    assert settings.orchestrator_config.aggregator_plugin_defs == [
        {"name": "pack_agg", "determinism_level": "guaranteed"},
        {"name": "inline_agg", "determinism_level": "guaranteed"},
    ]


def test_load_settings_suite_defaults_inherit_pack(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(
        """
        default:
          datasource:
            plugin: local_csv
            determinism_level: guaranteed
            options:
              path: data.csv
          llm:
            plugin: mock
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
                  determinism_level: guaranteed
          suite_defaults:
            prompt_pack: base
            aggregator_plugins:
              - name: suite_agg
                determinism_level: guaranteed
        """,
        encoding="utf-8",
    )

    with registry_overrides(
        [
            (
                datasource_registry,
                "local_csv",
                lambda options, context: SimpleNamespace(kind="ds", options=options, context=context),
            ),
            (
                llm_registry,
                "mock",
                lambda options, context: SimpleNamespace(kind="llm", options=options, context=context),
            ),
        ]
    ):
        settings = load_settings(config_file)

    assert settings.suite_defaults["prompts"]["system"] == "Pack system"
    assert settings.suite_defaults["prompt_fields"] == ["id"]
    assert settings.suite_defaults["row_plugins"] == [{"name": "pack_row", "determinism_level": "guaranteed"}]
    assert settings.suite_defaults["aggregator_plugins"] == [
        {"name": "suite_agg", "determinism_level": "guaranteed"}
    ]
