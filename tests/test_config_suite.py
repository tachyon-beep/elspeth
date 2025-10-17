from contextlib import ExitStack, contextmanager
from types import SimpleNamespace

import pytest

from elspeth.config import load_settings
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.registries.llm import llm_registry
from elspeth.core.registries.sink import sink_registry


@contextmanager
def registry_overrides(overrides):
    with ExitStack() as stack:
        for registry, name, factory in overrides:
            stack.enter_context(registry.temporary_override(name, factory))
        yield


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
