from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
import yaml

from elspeth import cli


def test_cli_strict_mode_exits_on_sink_failure(monkeypatch, tmp_path: Path):
    # Security note: this test simulates production STRICT mode to assert the
    # CLI fails closed when a sink raises. We scope the mode change to this test
    # via environment, never by relaxing production code.
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
            # LLM required in STRICT: use azure_openai type to pass validation; we'll monkeypatch the factory
            "llm": {
                "plugin": "azure_openai",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {
                    "deployment": "dummy",
                    "config": {
                        # Minimal config to satisfy schema; instantiation is monkeypatched
                        "azure_endpoint": "https://example.openai.azure.com",
                        "api_version": "2024-05-01",
                    },
                },
            },
            "prompts": {"system": "S", "user": "U {{ payload }}"},
            "prompt_fields": ["payload"],
            "sinks": [
                {
                    "plugin": "csv",
                    "security_level": "OFFICIAL",
                    "determinism_level": "guaranteed",
                    "options": {"path": str(tmp_path / "out.csv")},
                },
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

    # Monkeypatch LLM factory to return a no-op client
    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": "ok", "raw": {}, "metadata": metadata or {}}

    from elspeth.core.registries import llm as llm_reg_mod

    monkeypatch.setattr(
        llm_reg_mod, "llm_registry", type("R", (), {"create": staticmethod(lambda name, opts, parent_context=None: DummyLLM())})()
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
            "--log-level",
            "ERROR",
        ]
    )

    with pytest.raises(SystemExit) as se:
        cli.run(args)
    assert se.value.code == 1
