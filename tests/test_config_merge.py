"""Configuration and prompt loading coverage."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from elspeth import cli
from elspeth.config import load_settings
from elspeth.core.prompts.loader import load_template, load_template_pair
from elspeth.core.validation import validate_settings


def test_load_settings_merges_prompt_pack_and_defaults(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    pd.DataFrame([{"value": "alpha"}]).to_csv(input_csv, index=False)

    settings_payload = {
        "default": {
            "datasource": {
                "plugin": "local_csv",
                "security_level": "OFFICIAL", "determinism_level": "guaranteed",
                "options": {"path": str(input_csv)},
            },
            "llm": {
                "plugin": "mock",
                "security_level": "OFFICIAL", "determinism_level": "guaranteed",
                "options": {"seed": 1},
            },
            "prompt_pack": "packA",
            "prompt_packs": {
                "packA": {
                    "prompts": {
                        "system": "Pack system prompt",
                        "user": "Pack user {{ value }}",
                    },
                    "prompt_defaults": {"tone": "warm"},
                    "row_plugins": [{"name": "score_extractor", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
                    "aggregator_plugins": [{"name": "score_stats", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
                    "sinks": [
                        {
                            "plugin": "csv",
                            "security_level": "OFFICIAL", "determinism_level": "guaranteed",
                            "options": {"path": str(tmp_path / "pack_results.csv")},
                        }
                    ],
                }
            },
            "prompts": {"user": "Override user {{ value }}"},
            "suite_defaults": {
                "prompt_pack": "packA",
                "sinks": [
                    {
                        "plugin": "csv",
                        "security_level": "OFFICIAL", "determinism_level": "guaranteed",
                        "options": {"path": str(tmp_path / "suite_results.csv")},
                    }
                ],
                "security_level": "SECRET", "determinism_level": "guaranteed",
            },
        }
    }
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")

    settings = load_settings(settings_path, profile="default")
    config = settings.orchestrator_config

    assert config.llm_prompt["system"] == "Pack system prompt"
    assert config.llm_prompt["user"] == "Override user {{ value }}"
    assert config.prompt_defaults["tone"] == "warm"
    assert config.prompt_pack == "packA"
    # Prompt pack sinks are used when profile-level sinks are absent.
    assert len(settings.sinks) == 1
    assert getattr(settings.sinks[0], "path") == tmp_path / "pack_results.csv"

    defaults = cli._assemble_suite_defaults(settings)
    assert defaults["prompt_pack"] == "packA"
    assert defaults["row_plugin_defs"][0] == {
        "name": "score_extractor",
        "security_level": "OFFICIAL", "determinism_level": "guaranteed",
    }
    assert "sink_defs" in defaults
    assert settings.suite_defaults["security_level"] == "SECRET"
    assert settings.suite_defaults["determinism_level"] == "guaranteed"


def test_validate_settings_flags_missing_profile(tmp_path: Path) -> None:
    settings_path = tmp_path / "empty.yaml"
    settings_path.write_text("{}", encoding="utf-8")
    report = validate_settings(settings_path, profile="ghost")
    assert report.has_errors()
    assert any("Profile 'ghost' not found" in message.format() for message in report.errors)


def test_prompt_loader_helpers(tmp_path: Path) -> None:
    system_path = tmp_path / "system.txt"
    user_path = tmp_path / "user.txt"
    system_path.write_text("System for {{ audience|default('all') }}", encoding="utf-8")
    user_path.write_text("Hello {{ name }}", encoding="utf-8")

    system_template = load_template(system_path, defaults={"audience": "developers"})
    rendered_system = system_template.render()
    assert "developers" in rendered_system

    system, user = load_template_pair(system_path, user_path)
    assert system.name == "system_prompt"
    assert user.render(context={"name": "ELSPETH"}) == "Hello ELSPETH"
