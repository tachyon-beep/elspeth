from __future__ import annotations

import argparse
from typing import Any, Mapping

import pandas as pd
import pytest

import elspeth.cli as cli
from elspeth.core.base.schema.base import DataFrameSchema
from elspeth.core.experiments.plugin_registry import (
    register_row_plugin,
    register_aggregation_plugin,
    register_validation_plugin,
)
from elspeth.core.orchestrator import OrchestratorConfig
from elspeth.core.validation import ValidationReport


def _mk_settings(
    df: pd.DataFrame,
    row_plugins: list[dict[str, Any]] | None = None,
    *,
    agg_plugins: list[dict[str, Any]] | None = None,
    val_plugins: list[dict[str, Any]] | None = None,
):
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
        sinks=[],
        orchestrator_config=OrchestratorConfig(
            llm_prompt={"system": "S", "user": "U {x}"},
            prompt_fields=["x"],
            criteria=None,
            row_plugin_defs=row_plugins,
            aggregator_plugin_defs=agg_plugins,
            validation_plugin_defs=val_plugins,
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


def test_plugin_requires_input_schema_but_missing(monkeypatch):
    # Register a row plugin that signals it requires input schema but returns None
    def factory(options, context):
        class _Plugin:
            name = "needs_schema"

            def input_schema(self):  # noqa: D401
                return None

            def process_row(self, row, responses):  # noqa: D401
                return {}

        return _Plugin()

    register_row_plugin("needs_schema", factory, requires_input_schema=True)

    class DS(DataFrameSchema):  # noqa: N801
        x: int

    df = pd.DataFrame({"x": [1]})
    df.attrs["schema"] = DS

    settings = _mk_settings(
        df,
        row_plugins=[{"name": "needs_schema", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
    )
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())

    parser = cli.build_parser()
    args = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    with pytest.raises(SystemExit):
        cli.run(args)


def test_plugin_requires_input_schema_and_provides(monkeypatch, capsys):
    def factory(options, context):
        class _Plugin:
            name = "has_schema"

            def input_schema(self):  # noqa: D401
                class RequireX(DataFrameSchema):  # noqa: N801
                    x: int

                return RequireX

            def process_row(self, row, responses):  # noqa: D401
                return {}

        return _Plugin()

    register_row_plugin("has_schema", factory, requires_input_schema=True)

    class DS(DataFrameSchema):  # noqa: N801
        x: int

    df = pd.DataFrame({"x": [1]})
    df.attrs["schema"] = DS

    settings = _mk_settings(
        df,
        row_plugins=[{"name": "has_schema", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
    )
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())

    parser = cli.build_parser()
    args = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    cli.run(args)
    assert "Schema validation successful" in capsys.readouterr().out


def test_agg_plugin_requires_input_schema(monkeypatch):
    def factory_missing(options, context):
        class _Agg:
            name = "agg_needs_schema"

            def input_schema(self):  # noqa: D401
                return None

            def finalize(self, records):  # noqa: D401
                return {}

        return _Agg()

    def factory_ok(options, context):
        class _Agg:
            name = "agg_has_schema"

            def input_schema(self):  # noqa: D401
                class RequireX(DataFrameSchema):  # noqa: N801
                    x: int

                return RequireX

            def finalize(self, records):  # noqa: D401
                return {}

        return _Agg()

    register_aggregation_plugin("agg_needs_schema", factory_missing, requires_input_schema=True)
    register_aggregation_plugin("agg_has_schema", factory_ok, requires_input_schema=True)

    class DS(DataFrameSchema):  # noqa: N801
        x: int

    df = pd.DataFrame({"x": [1]})
    df.attrs["schema"] = DS

    # Missing case
    settings = _mk_settings(df, agg_plugins=[{"name": "agg_needs_schema", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}])
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    parser = cli.build_parser()
    args = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    with pytest.raises(SystemExit):
        cli.run(args)

    # Providing schema succeeds
    settings_ok = _mk_settings(
        df, agg_plugins=[{"name": "agg_has_schema", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}]
    )
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings_ok)
    args_ok = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    cli.run(args_ok)


def test_validation_plugin_requires_input_schema(monkeypatch):
    def factory_missing(options, context):
        class _V:
            name = "val_needs_schema"

            def input_schema(self):  # noqa: D401
                return None

            def validate(self, response, context=None, metadata=None):  # noqa: D401
                return None

        return _V()

    def factory_ok(options, context):
        class _V:
            name = "val_has_schema"

            def input_schema(self):  # noqa: D401
                class RequireX(DataFrameSchema):  # noqa: N801
                    x: int

                return RequireX

            def validate(self, response, context=None, metadata=None):  # noqa: D401
                return None

        return _V()

    register_validation_plugin("val_needs_schema", factory_missing, requires_input_schema=True)
    register_validation_plugin("val_has_schema", factory_ok, requires_input_schema=True)

    class DS(DataFrameSchema):  # noqa: N801
        x: int

    df = pd.DataFrame({"x": [1]})
    df.attrs["schema"] = DS

    settings_missing = _mk_settings(
        df, val_plugins=[{"name": "val_needs_schema", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}]
    )
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings_missing)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    parser = cli.build_parser()
    args = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    with pytest.raises(SystemExit):
        cli.run(args)

    settings_ok = _mk_settings(
        df, val_plugins=[{"name": "val_has_schema", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}]
    )
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings_ok)
    args_ok = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    cli.run(args_ok)
