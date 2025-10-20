from __future__ import annotations

import argparse
from typing import Any, Mapping

import pandas as pd
import pytest

import elspeth.cli as cli
from elspeth.core.base.schema.base import DataFrameSchema
from elspeth.core.orchestrator import OrchestratorConfig
from elspeth.core.validation import ValidationReport


def _mk_settings(df: pd.DataFrame, *, prompt_fields: list[str] | None, sinks: list[Any] | None):
    class DummyDatasource:
        def __init__(self, df_: pd.DataFrame) -> None:
            self._df = df_

        def load(self):
            return self._df

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata: Mapping[str, Any] | None = None):  # noqa: D401
            return {"content": user_prompt, "metrics": {}}

    return argparse.Namespace(
        datasource=DummyDatasource(df),
        llm=DummyLLM(),
        sinks=sinks or [],
        orchestrator_config=OrchestratorConfig(
            llm_prompt={"system": "S", "user": "U {x}"},
            prompt_fields=prompt_fields,
            criteria=None,
            row_plugin_defs=None,
            aggregator_plugin_defs=None,
            validation_plugin_defs=None,
            prompt_defaults=None,
        ),
        suite_root=None,
        suite_defaults={},
        rate_limiter=None,
        cost_tracker=None,
        prompt_packs={},
        prompt_pack=None,
        config_path=None,
    )


def test_validate_schemas_fails_when_no_datasource_schema(monkeypatch):
    df = pd.DataFrame({"x": [1]})  # no attrs['schema'] attached
    settings = _mk_settings(df, prompt_fields=["x"], sinks=[])
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    parser = cli.build_parser()
    args = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    with pytest.raises(SystemExit):
        cli.run(args)


def test_validate_schemas_fails_on_missing_prompt_field(monkeypatch):
    # Datasource schema only has 'x'
    class DS(DataFrameSchema):  # noqa: N801
        x: int

    df = pd.DataFrame({"x": [1]})
    df.attrs["schema"] = DS
    settings = _mk_settings(df, prompt_fields=["x", "y"], sinks=[])
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    parser = cli.build_parser()
    args = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    with pytest.raises(SystemExit):
        cli.run(args)


def test_validate_schemas_enforces_sink_declarations(monkeypatch):
    class BadSink:
        # missing produces/consumes or wrong return type
        def produces(self):  # returns wrong type intentionally
            return None

        def consumes(self):
            return []

    # Valid datasource schema
    class DS(DataFrameSchema):  # noqa: N801
        x: int

    df = pd.DataFrame({"x": [1]})
    df.attrs["schema"] = DS
    settings = _mk_settings(df, prompt_fields=["x"], sinks=[BadSink()])
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    parser = cli.build_parser()
    args = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    with pytest.raises(SystemExit):
        cli.run(args)

