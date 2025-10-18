from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from elspeth import cli


def test_cli_signed_bundle_write_failure(monkeypatch, tmp_path: Path, caplog):
    # Minimal input
    input_csv = tmp_path / "input.csv"
    pd.DataFrame([{"payload": "x"}]).to_csv(input_csv, index=False)

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

    # Patch ReproducibilityBundleSink to raise at write
    class BoomSink:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def write(self, payload, *, metadata=None):  # noqa: D401
            raise RuntimeError("boom")

    monkeypatch.setitem(
        cli.__dict__,
        "ReproducibilityBundleSink",
        BoomSink,
    )

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

    # Should not raise; error is logged and run completes
    cli.run(args)
    assert any("Failed to create reproducibility bundle" in rec.message for rec in caplog.records)
