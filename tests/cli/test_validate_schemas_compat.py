from __future__ import annotations

import argparse
from typing import Any, Mapping

import pandas as pd
import pytest

import elspeth.cli as cli
from elspeth.core.base.schema.base import DataFrameSchema
from elspeth.core.experiments.plugin_registry import register_row_plugin
from elspeth.core.orchestrator import OrchestratorConfig
from elspeth.core.validation import ValidationReport


def _make_settings(df: pd.DataFrame, row_plugins: list[dict[str, Any]] | None):
    class DummyDatasource:
        def __init__(self, df: pd.DataFrame) -> None:
            self._df = df

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


def test_validate_schemas_fails_on_incompatible_plugin_schema(monkeypatch):
    # Plugin requires column 'b' which is missing
    def factory_missing(options, context):
        class _Plugin:
            name = "require_b"

            def input_schema(self):  # noqa: D401
                class RequireBSchema(DataFrameSchema):  # noqa: N801
                    b: int

                return RequireBSchema

            def process_row(self, row, responses):  # noqa: D401
                return {}

        return _Plugin()

    register_row_plugin("require_b", factory_missing)

    df = pd.DataFrame({"x": [1]})

    # Attach datasource schema (x only)
    class DS(DataFrameSchema):  # noqa: N801
        x: int

    df.attrs["schema"] = DS

    settings = _make_settings(
        df,
        row_plugins=[{"name": "require_b", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
    )

    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())

    parser = cli.build_parser()
    args = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    with pytest.raises(SystemExit):
        cli.run(args)


def test_validate_schemas_succeeds_with_compatible_plugin_schema(monkeypatch, capsys):
    # Plugin requires column 'x' which is present
    def factory_ok(options, context):
        class _Plugin:
            name = "require_x"

            def input_schema(self):  # noqa: D401
                class RequireX(DataFrameSchema):  # noqa: N801
                    x: int

                return RequireX

            def process_row(self, row, responses):  # noqa: D401
                return {}

        return _Plugin()

    register_row_plugin("require_x", factory_ok)

    df = pd.DataFrame({"x": [1]})

    class DS(DataFrameSchema):  # noqa: N801
        x: int

    df.attrs["schema"] = DS

    settings = _make_settings(
        df,
        row_plugins=[{"name": "require_x", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
    )

    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())

    parser = cli.build_parser()
    args = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    cli.run(args)
    out = capsys.readouterr().out
    assert "Schema validation successful" in out
