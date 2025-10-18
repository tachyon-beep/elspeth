"""Covers CLI artifact publish branch with --artifact-sink-* flags.

Uses a temporary override for the azure_devops_artifact_repo sink to avoid
network calls and asserts that the sink receives the bundle path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from elspeth import cli
from elspeth.core.registries.sink import sink_registry


def test_cli_artifact_publish_dry_run(monkeypatch, tmp_path: Path) -> None:
    class DummyPublishSink:
        calls: list[tuple[dict, dict]] = []

        def __init__(self, **kwargs):  # noqa: D401
            # Accept any kwargs; context will be attached by registry
            self.kwargs = kwargs

        def write(self, results: dict, *, metadata: dict | None = None) -> None:  # noqa: D401
            DummyPublishSink.calls.append((results, metadata or {}))

    # Minimal input CSV
    input_csv = tmp_path / "input.csv"
    pd.DataFrame([{"payload": "x"}, {"payload": "y"}]).to_csv(input_csv, index=False)

    # Settings for a single-run with mock LLM and CSV sink
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
            "prompts": {
                "system": "System",
                "user": "User {{ payload }}",
            },
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

    # Artifact sink config with required security/determinism (registry requires context)
    cfg = {
        # Real sink would require org/project/repo but our dummy ignores
        "dry_run": True,
        "security_level": "OFFICIAL",
        "determinism_level": "guaranteed",
    }
    cfg_path = tmp_path / "artifact_sink.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    # Ensure signing key exists for reproducibility bundle creation
    monkeypatch.setenv("ELSPETH_SIGNING_KEY", "test-key")

    # Inject CLI flags via sys.argv (the publisher path parses argv directly)
    orig_argv = sys.argv[:]
    monkeypatch.setenv("PYTHONWARNINGS", "ignore")
    sys.argv = [
        "elspeth-cli-test",
        "--artifact-sink-plugin",
        "azure_devops_artifact_repo",
        "--artifact-sink-config",
        str(cfg_path),
    ]

    try:
        with sink_registry.temporary_override(
            "azure_devops_artifact_repo",
            lambda options, context: DummyPublishSink(**options),
            schema=None,
        ):
            parser = cli.build_parser()
            args = parser.parse_args(
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

    # Assert that the dummy publisher sink was invoked with the bundle path
    assert DummyPublishSink.calls, "expected artifact publisher sink to be called"
    results, metadata = DummyPublishSink.calls[-1]
    bundle_path = Path(metadata.get("path") or results.get("artifacts", [None])[0])
    assert bundle_path and bundle_path.exists(), "bundle path should exist on disk"
