import argparse
import json
from pathlib import Path

import pandas as pd
import pytest

import dmp.cli as cli
from dmp.core.orchestrator import OrchestratorConfig
from dmp.plugins.outputs.csv_file import CsvResultSink
from dmp.core.validation import ValidationReport, SuiteValidationReport


def create_suite(root: Path):
    (root / "exp1").mkdir(parents=True)
    (root / "exp2").mkdir(parents=True)
    (root / "exp1" / "config.json").write_text(
        '{"name": "exp1", "enabled": true, "temperature": 0.5, "max_tokens": 128}',
        encoding="utf-8",
    )
    (root / "exp1" / "system_prompt.md").write_text("System", encoding="utf-8")
    (root / "exp1" / "user_prompt.md").write_text("Exp1 {APPID}", encoding="utf-8")
    (root / "exp2" / "config.json").write_text(
        '{"name": "exp2", "enabled": true, "temperature": 0.7, "max_tokens": 256}',
        encoding="utf-8",
    )
    (root / "exp2" / "system_prompt.md").write_text("System", encoding="utf-8")
    (root / "exp2" / "user_prompt.md").write_text("Exp2 {APPID}", encoding="utf-8")


def test_cli_suite_execution(tmp_path, monkeypatch):
    suite_root = tmp_path / "suite"
    create_suite(suite_root)

    output_base = tmp_path / "outputs" / "latest_results.csv"
    output_base.parent.mkdir(parents=True, exist_ok=True)

    class DummyDatasource:
        def load(self):
            return pd.DataFrame({"APPID": ["1"]})

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": user_prompt}

    settings_obj = argparse.Namespace(
        datasource=DummyDatasource(),
        llm=DummyLLM(),
        sinks=[CsvResultSink(path=output_base)],
        orchestrator_config=OrchestratorConfig(
            llm_prompt={"system": "sys", "user": "unused"},
            prompt_fields=["APPID"],
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
        suite_root=suite_root,
        suite_defaults={},
        rate_limiter=None,
        cost_tracker=None,
        prompt_packs={},
        prompt_pack=None,
    )

    def fake_load_settings(path, profile="default"):
        return settings_obj

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "ExperimentSuite", cli.ExperimentSuite)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    monkeypatch.setattr(
        cli,
        "validate_suite",
        lambda *a, **k: SuiteValidationReport(report=ValidationReport(), preflight={}),
    )

    cli.main(["--settings", str(tmp_path / "settings.yaml"), "--profile", "default", "--head", "0"])

    exp1_path = output_base.with_name(f"exp1_{output_base.name}")
    exp2_path = output_base.with_name(f"exp2_{output_base.name}")
    assert exp1_path.exists()
    assert exp2_path.exists()

    df1 = pd.read_csv(exp1_path)
    assert df1["llm_content"].iloc[0] == "Exp1 1"


def test_cli_suite_prompt_pack_override(tmp_path, monkeypatch):
    suite_root = tmp_path / "suite"
    exp_dir = suite_root / "exp"
    exp_dir.mkdir(parents=True)
    (exp_dir / "config.json").write_text(
        '{"name": "exp", "enabled": true, "temperature": 0.0, "max_tokens": 32, "prompt_pack": "pack"}',
        encoding="utf-8",
    )

    class DummyDatasource:
        def load(self):
            return pd.DataFrame({"APPID": ["1"]})

    class DummyLLM:
        def __init__(self):
            self.calls = []

        def generate(self, *, system_prompt, user_prompt, metadata=None):
            self.calls.append((system_prompt, user_prompt, metadata))
            return {"content": user_prompt}

    llm = DummyLLM()

    settings_obj = argparse.Namespace(
        datasource=DummyDatasource(),
        llm=llm,
        sinks=[],
        orchestrator_config=OrchestratorConfig(
            llm_prompt={"system": "", "user": ""},
            prompt_fields=["APPID"],
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
        suite_root=suite_root,
        suite_defaults={},
        rate_limiter=None,
        cost_tracker=None,
        prompt_packs={
            "pack": {
                "prompts": {
                    "system": "Pack System",
                    "user": "Pack User {APPID}",
                }
            }
        },
        prompt_pack=None,
    )

    def fake_load_settings(path, profile="default"):
        return settings_obj

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "ExperimentSuite", cli.ExperimentSuite)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    monkeypatch.setattr(
        cli,
        "validate_suite",
        lambda *a, **k: SuiteValidationReport(report=ValidationReport(), preflight={}),
    )

    cli.main(["--settings", str(tmp_path / "settings.yaml"), "--suite-root", str(suite_root), "--head", "0"])

    assert llm.calls
    system_prompt, user_prompt, _ = llm.calls[0]
    assert system_prompt == "Pack System"
    assert user_prompt == "Pack User 1"


def test_cli_suite_management_flags(tmp_path, monkeypatch):
    suite_root = tmp_path / "suite"
    create_suite(suite_root)
    exp1_config = suite_root / "exp1" / "config.json"
    exp1_data = json.loads(exp1_config.read_text(encoding="utf-8"))
    exp1_data["is_baseline"] = True
    exp1_config.write_text(json.dumps(exp1_data), encoding="utf-8")

    class DummyDatasource:
        def load(self):
            return pd.DataFrame({"APPID": ["1"]})

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": user_prompt}

    output_base = tmp_path / "outputs" / "latest_results.csv"
    settings_obj = argparse.Namespace(
        datasource=DummyDatasource(),
        llm=DummyLLM(),
        sinks=[CsvResultSink(path=output_base)],
        orchestrator_config=OrchestratorConfig(
            llm_prompt={"system": "sys", "user": "unused"},
            prompt_fields=["APPID"],
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
        suite_root=suite_root,
        suite_defaults={},
        rate_limiter=None,
        cost_tracker=None,
        prompt_packs={},
        prompt_pack=None,
    )

    def fake_load_settings(path, profile="default"):
        return settings_obj

    generated_paths = []

    class Recorder:
        def __init__(self, suite, results):
            self.suite = suite
            self.results = results

        def generate_all_reports(self, path):
            generated_paths.append(Path(path))

    monkeypatch.setattr(cli, "SuiteReportGenerator", Recorder)
    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "ExperimentSuite", cli.ExperimentSuite)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    monkeypatch.setattr(
        cli,
        "validate_suite",
        lambda *a, **k: SuiteValidationReport(report=ValidationReport(), preflight={}),
    )

    export_path = tmp_path / "suite_export.json"
    reports_dir = tmp_path / "reports"
    cli.main(
        [
            "--settings",
            str(tmp_path / "settings.yaml"),
            "--suite-root",
            str(suite_root),
            "--create-experiment-template",
            "new_template",
            "--export-suite-config",
            str(export_path),
            "--reports-dir",
            str(reports_dir),
            "--head",
            "0",
        ]
    )

    assert (suite_root / "new_template" / "config.json").exists()
    assert export_path.exists()
    assert generated_paths and generated_paths[0] == reports_dir
