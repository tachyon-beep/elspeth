from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
import yaml

from elspeth import cli


def test_cli_strict_mode_exits_on_sink_failure(monkeypatch, tmp_path: Path):
    # STRICT mode
    monkeypatch.setenv("ELSPETH_SECURE_MODE", "strict")

    # Minimal input
    input_csv = tmp_path / "input.csv"
    pd.DataFrame([{"payload": "x"}]).to_csv(input_csv, index=False)

    settings_data = {
        "default": {
            "datasource": {
                "plugin": "local_csv",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"path": str(input_csv), "retain_local": True},
            },
            # No LLM → identity flow
            "sinks": [
                {"plugin": "csv", "security_level": "OFFICIAL", "determinism_level": "guaranteed", "options": {"path": str(tmp_path / "out.csv")}},
            ],
        }
    }
    tmp_settings = tmp_path / "settings.yaml"
    tmp_settings.write_text(yaml.safe_dump(settings_data), encoding="utf-8")

    # Patch csv sink to fail
    class BoomCsv:
        def __init__(self, **kwargs):
            pass

        def write(self, payload, *, metadata=None):
            raise RuntimeError("boom")

    from elspeth.plugins.nodes.sinks import csv_file as csv_mod

    monkeypatch.setattr(csv_mod, "CsvResultSink", BoomCsv)

    args = cli.build_parser().parse_args(
        [
            "--settings",
            str(tmp_settings),
            "--profile",
            "default",
            "--head",
            "0",
            "--single-run",
            "--log-level",
            "ERROR",
        ]
    )

    with pytest.raises(SystemExit) as se:
        cli.run(args)
    assert se.value.code == 1

