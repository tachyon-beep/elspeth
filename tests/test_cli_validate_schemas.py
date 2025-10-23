from __future__ import annotations

import argparse
from types import SimpleNamespace

import pandas as pd
import pytest

import elspeth.cli as cli


class _DummyValidation:
    warnings: list = []

    def raise_if_errors(self):
        return None


def _make_settings_with_df(df: pd.DataFrame):
    return SimpleNamespace(
        datasource=SimpleNamespace(load=lambda: df),
        sinks=[],
        orchestrator_config=SimpleNamespace(
            llm_prompt={"system": "", "user": ""},
            prompt_fields=[],
            criteria=None,
            row_plugin_defs=None,
            aggregator_plugin_defs=None,
            sink_defs=None,
            prompt_pack=None,
            baseline_plugin_defs=None,
            retry_config=None,
            checkpoint_config=None,
            llm_middleware_defs=None,
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


@pytest.fixture(autouse=True)
def _patch_validation(monkeypatch):
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: _DummyValidation())
    monkeypatch.setattr(cli, "validate_suite", lambda *a, **k: SimpleNamespace(report=_DummyValidation(), preflight={}))


def test_validate_schemas_with_schema_attached(monkeypatch, capsys):
    df = pd.DataFrame({"a": [1]})

    class Schema:
        # __name__ is determined by Python and will be 'Schema'
        __annotations__ = {"a": int}

    df.attrs["schema"] = Schema
    settings = _make_settings_with_df(df)
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)

    args = argparse.Namespace(
        settings="unused.yaml",
        profile="default",
        validate_schemas=True,
        head=0,
        suite_root=None,
        single_run=False,
        live_outputs=False,
        disable_metrics=False,
        log_level="ERROR",
    )

    cli.run(args)
    out = capsys.readouterr().out
    assert "Schema validation successful" in out
    assert "Schema: Schema" in out


def test_validate_schemas_without_schema(monkeypatch, capsys):
    df = pd.DataFrame({"a": [1]})  # no df.attrs["schema"] set
    settings = _make_settings_with_df(df)
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)

    args = argparse.Namespace(
        settings="unused.yaml",
        profile="default",
        validate_schemas=True,
        head=0,
        suite_root=None,
        single_run=False,
        live_outputs=False,
        disable_metrics=False,
        log_level="ERROR",
    )

    cli.run(args)
    out = capsys.readouterr().out
    assert "No schema validation performed" in out


def test_validate_schemas_failure_raises(monkeypatch):
    class BadDatasource:
        def load(self):
            raise RuntimeError("boom")

    settings = _make_settings_with_df(pd.DataFrame())
    settings.datasource = BadDatasource()
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: settings)

    args = argparse.Namespace(
        settings="unused.yaml",
        profile="default",
        validate_schemas=True,
        head=0,
        suite_root=None,
        single_run=False,
        live_outputs=False,
        disable_metrics=False,
        log_level="ERROR",
    )

    with pytest.raises(SystemExit) as se:
        cli.run(args)
    assert se.value.code == 1
