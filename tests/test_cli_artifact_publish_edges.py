from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from elspeth import cli
from elspeth.core.registries.sink import sink_registry


def _basic_settings(tmp_path: Path, input_csv: Path) -> Path:
    settings_data = {
        "default": {
            "datasource": {
                "plugin": "local_csv",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"path": str(input_csv), "retain_local": False},
            },
            "llm": {
                "plugin": "mock",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"seed": 1},
            },
            "prompts": {"system": "S", "user": "U {{ payload }}"},
            "prompt_fields": ["payload"],
            "sinks": [
                {
                    "plugin": "csv",
                    "security_level": "OFFICIAL",
                    "determinism_level": "guaranteed",
                    "options": {"path": str(tmp_path / "results.csv")},
                }
            ],
        }
    }
    tmp_settings = tmp_path / "settings.yaml"
    tmp_settings.write_text(yaml.safe_dump(settings_data), encoding="utf-8")
    return tmp_settings


def test_publish_missing_plugin_name(monkeypatch, tmp_path: Path):
    input_csv = tmp_path / "input.csv"
    pd.DataFrame([{"payload": "x"}]).to_csv(input_csv, index=False)
    tmp_settings = _basic_settings(tmp_path, input_csv)

    class DummyPublishSink:
        calls: list = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def write(self, results, *, metadata=None):
            DummyPublishSink.calls.append((results, metadata))

    # Bad argv: missing plugin name after flag
    orig_argv = sys.argv[:]
    sys.argv = ["elspeth-cli", "--artifact-sink-plugin"]
    monkeypatch.setenv("ELSPETH_SIGNING_KEY", "test-key")

    try:
        with sink_registry.temporary_override(
            "azure_devops_artifact_repo",
            lambda options, context: DummyPublishSink(**options),
            schema=None,
        ):
            args = cli.build_parser().parse_args(
                [
                    "--settings",
                    str(tmp_settings),
                    "--profile",
                    "default",
                    "--head",
                    "0",
                    "--single-run",
                    "--artifacts-dir",
                    str(tmp_path / "artifacts"),
                    "--signed-bundle",
                    "--log-level",
                    "ERROR",
                ]
            )
            cli.run(args)
    finally:
        sys.argv = orig_argv

    assert not DummyPublishSink.calls, "no publish expected when plugin arg missing"


def test_publish_bad_config_path(monkeypatch, tmp_path: Path):
    input_csv = tmp_path / "input.csv"
    pd.DataFrame([{"payload": "x"}]).to_csv(input_csv, index=False)
    tmp_settings = _basic_settings(tmp_path, input_csv)

    class DummyPublishSink:
        calls: list = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def write(self, results, *, metadata=None):
            DummyPublishSink.calls.append((results, metadata))

    # argv: plugin present, config path invalid
    orig_argv = sys.argv[:]
    sys.argv = [
        "elspeth-cli",
        "--artifact-sink-plugin",
        "azure_devops_artifact_repo",
        "--artifact-sink-config",
        str(tmp_path / "does-not-exist.yaml"),
    ]
    monkeypatch.setenv("ELSPETH_SIGNING_KEY", "test-key")

    try:
        with sink_registry.temporary_override(
            "azure_devops_artifact_repo",
            lambda options, context: DummyPublishSink(**options),
            schema=None,
        ):
            args = cli.build_parser().parse_args(
                [
                    "--settings",
                    str(tmp_settings),
                    "--profile",
                    "default",
                    "--head",
                    "0",
                    "--single-run",
                    "--artifacts-dir",
                    str(tmp_path / "artifacts"),
                    "--signed-bundle",
                    "--log-level",
                    "ERROR",
                ]
            )
            cli.run(args)
    finally:
        sys.argv = orig_argv

    # With invalid config the CLI skips publish gracefully
    assert not DummyPublishSink.calls, "no publish expected when config path invalid"
