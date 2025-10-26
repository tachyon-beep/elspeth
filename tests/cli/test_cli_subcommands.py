from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

import elspeth.cli as cli
from elspeth.core.validation import SuiteValidationReport, ValidationReport


def _stub_settings_df() -> argparse.Namespace:
    class DummyDatasource:
        def load(self):
            df = pd.DataFrame({"col": [1, 2]})
            # Attach a trivial schema marker so validate-schemas prints details if needed
            df.attrs["schema"] = type("Schema", (), {"__name__": "DummySchema", "__annotations__": {"col": int}})
            return df

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):  # noqa: D401
            return {"content": user_prompt, "metrics": {"score": 0.1}}

    return argparse.Namespace(
        datasource=DummyDatasource(),
        llm=DummyLLM(),
        sinks=[],
        orchestrator_config=argparse.Namespace(
            llm_prompt={"system": "S", "user": "U {col}"},
            prompt_fields=["col"],
            criteria=None,
            row_plugin_defs=None,
            aggregator_plugin_defs=None,
            sink_defs=None,
            validation_plugin_defs=None,
            early_stop_plugin_defs=None,
            early_stop_config=None,
            llm_middleware_defs=None,
            retry_config=None,
            checkpoint_config=None,
            concurrency_config=None,
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


def test_subcommand_validate_schemas_smoke(monkeypatch):
    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: _stub_settings_df())
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    parser = cli.build_parser()
    args = parser.parse_args(["validate-schemas", "--settings", "cfg.yaml", "--profile", "default"])
    cli.run(args)  # Should not raise


def test_subcommand_run_single_dispatch(monkeypatch):
    called = {"run_single": False}

    def _fake_run_single(a, s):
        called["run_single"] = True

    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: _stub_settings_df())
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    monkeypatch.setattr(cli, "_run_single", _fake_run_single)

    parser = cli.build_parser()
    args = parser.parse_args(["run-single", "--settings", "cfg.yaml", "--profile", "default"])
    cli.run(args)
    assert called["run_single"] is True


def test_subcommand_run_suite_dispatch(monkeypatch, tmp_path: Path):
    called = {"run_suite": False}

    def _fake_run_suite(args, settings, suite_root, *, preflight=None, suite=None):  # noqa: D401
        called["run_suite"] = True

    monkeypatch.setattr(cli, "load_settings", lambda *a, **k: _stub_settings_df())
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    monkeypatch.setattr(
        cli,
        "validate_suite",
        lambda *a, **k: SuiteValidationReport(report=ValidationReport(), preflight={}),
    )
    monkeypatch.setattr(cli, "_run_suite", _fake_run_suite)

    parser = cli.build_parser()
    args = parser.parse_args(["run-suite", "--settings", "cfg.yaml", "--profile", "default", "--suite-root", str(tmp_path)])
    cli.run(args)
    assert called["run_suite"] is True


def test_subcommand_run_job_dispatch(monkeypatch, tmp_path: Path):
    # Minimal source data
    input_csv = tmp_path / "input.csv"
    pd.DataFrame([{"payload": "a"}]).to_csv(input_csv, index=False)

    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        """
job:
  name: adhoc
  datasource:
    plugin: local_csv
    determinism_level: guaranteed
    options:
      path: INPUT
      retain_local: false
  sinks:
    - plugin: csv
      determinism_level: guaranteed
      options:
        path: OUTPUT
        """.replace("INPUT", str(input_csv)).replace("OUTPUT", str(tmp_path / "results.csv")),
        encoding="utf-8",
    )

    parser = cli.build_parser()
    args = parser.parse_args(["run-job", "--job-config", str(job_yaml), "--head", "0"])
    cli.run(args)
    assert (tmp_path / "results.csv").exists()
