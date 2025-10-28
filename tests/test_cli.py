import argparse
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import elspeth.cli as cli
from elspeth.core.experiments.plugin_registry import register_row_plugin
from elspeth.core.orchestrator import OrchestratorConfig
from elspeth.core.validation import SuiteValidationReport, ValidationReport
from elspeth.plugins.nodes.sinks.csv_file import CsvResultSink


@pytest.fixture
def mock_settings(monkeypatch):
    captured = {}

    class DummyDatasource:
        def load(self):
            captured["datasource"] = True
            return pd.DataFrame({"col": [1, 2, 3]})

    class DummyLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            captured.setdefault("llm_calls", []).append(user_prompt)
            return {"text": "ok"}

    class DummySink:
        def __init__(self):
            captured.setdefault("sink_calls", 0)
            self._elspeth_security_level = "official"

        def write(self, results, *, metadata=None):
            captured["sink_calls"] += 1

    class DummySettings:
        def __init__(self):
            self.datasource = DummyDatasource()
            self.llm = DummyLLM()
            self.sinks = [DummySink()]
            self.orchestrator_config = OrchestratorConfig(
                llm_prompt={"system": "sys", "user": "Prompt {col}"},
                prompt_fields=["col"],
                prompt_aliases=None,
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
            )
            self.suite_root = None
            self.suite_defaults = {}
            self.rate_limiter = None
            self.cost_tracker = None
            self.prompt_packs = {}
            self.prompt_pack = None
            self.config_path = None

    def fake_load_settings(path, profile="default"):
        captured["settings_path"] = path
        captured["profile"] = profile
        return DummySettings()

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "ExperimentOrchestrator", cli.ExperimentOrchestrator)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    monkeypatch.setattr(
        cli,
        "validate_suite",
        lambda *a, **k: SuiteValidationReport(report=ValidationReport(), preflight={}),
    )

    return captured


def test_build_parser_has_expected_arguments():
    parser = cli.build_parser()
    args = parser.parse_args([])
    assert args.settings == "config/settings.yaml"
    assert args.profile == "default"
    assert args.head == 5
    assert args.suite_root is None
    assert args.single_run is False
    assert args.live_outputs is False


def test_run_loads_and_writes(tmp_path, mock_settings, monkeypatch):
    output_file = tmp_path / "out.csv"

    args = argparse.Namespace(
        settings="settings.yaml",
        profile="prod",
        head=2,
        output_csv=output_file,
        log_level="INFO",
        suite_root=None,
        single_run=False,
        live_outputs=False,
        disable_metrics=False,
    )

    def fake_to_csv(self, path, index):
        mock_settings["path"] = Path(path)
        mock_settings["index"] = index

    monkeypatch.setattr(pd.DataFrame, "to_csv", fake_to_csv)

    cli.run(args)

    assert mock_settings["settings_path"] == "settings.yaml"
    assert mock_settings["profile"] == "prod"
    assert mock_settings["path"] == output_file
    assert mock_settings["index"] is False


def test_main_smoke(mock_settings, capsys):
    cli.main(["--settings", "cfg.yaml", "--profile", "dev", "--head", "1", "--single-run"])
    captured = capsys.readouterr()
    assert "col" in captured.out
    assert mock_settings["settings_path"] == "cfg.yaml"
    assert mock_settings["profile"] == "dev"


def test_single_run_output_csv_includes_metrics(tmp_path, monkeypatch):
    def make_row_plugin(options, context):
        class _Plugin:
            name = "single_run_row_plugin"

            def process_row(self, row, responses):
                return {"custom_metric": 9}

        return _Plugin()

    register_row_plugin("single_run_row_plugin", make_row_plugin, declared_security_level="OFFICIAL")

    output_file = tmp_path / "single.csv"
    sink_path = tmp_path / "sink.csv"

    class DummyDatasource:
        def __init__(self):
            self._elspeth_security_level = "official"  # Must match row plugin
            self._elspeth_determinism_level = "guaranteed"

        def load(self):
            return pd.DataFrame({"col": [1]})

    class DummyLLM:
        def __init__(self):
            self._elspeth_security_level = "official"  # Must match row plugin
            self._elspeth_determinism_level = "guaranteed"

        def generate(self, *, system_prompt, user_prompt, metadata=None):
            return {"content": user_prompt, "metrics": {"score": 0.5}}

    csv_sink = CsvResultSink(path=sink_path)
    setattr(csv_sink, "_elspeth_security_level", "official")
    setattr(csv_sink, "_elspeth_determinism_level", "guaranteed")
    setattr(csv_sink, "determinism_level", "guaranteed")

    settings = argparse.Namespace(
        datasource=DummyDatasource(),  # Now properly initialized with security level
        llm=DummyLLM(),  # Now properly initialized with security level
        sinks=[csv_sink],
        orchestrator_config=OrchestratorConfig(
            llm_prompt={"system": "sys", "user": "Prompt {col}"},
            prompt_fields=["col"],
            criteria=None,
            row_plugin_defs=[
                {
                    "name": "single_run_row_plugin",
                    "determinism_level": "guaranteed",
                }
            ],
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

    def fake_load_settings(path, profile="default"):
        return settings

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    monkeypatch.setattr(
        cli,
        "validate_suite",
        lambda *a, **k: SuiteValidationReport(report=ValidationReport(), preflight={}),
    )

    args = argparse.Namespace(
        settings="settings.yaml",
        profile="default",
        head=0,
        output_csv=output_file,
        log_level="INFO",
        suite_root=None,
        single_run=True,
        live_outputs=False,
        disable_metrics=False,
    )

    cli.run(args)

    assert output_file.exists()
    df = pd.read_csv(output_file)
    assert "llm_content" in df.columns
    assert "llm_content_metric_score" in df.columns
    assert "metric_custom_metric" in df.columns
    assert "retry_attempts" in df.columns
    assert "retry_history" in df.columns
    assert df.loc[0, "llm_content"].startswith("Prompt")
    assert df.loc[0, "llm_content_metric_score"] == 0.5
    assert df.loc[0, "metric_custom_metric"] == 9
    assert df.loc[0, "retry_attempts"] == 1
    assert isinstance(df.loc[0, "retry_history"], str)


def test_clone_suite_sinks_propagates_determinism(tmp_path):
    csv_path = tmp_path / "results.csv"
    csv_sink = CsvResultSink(path=str(csv_path))
    setattr(csv_sink, "_elspeth_security_level", "OFFICIAL")
    setattr(csv_sink, "_elspeth_determinism_level", "guaranteed")
    setattr(csv_sink, "determinism_level", "guaranteed")

    class DummySink:
        def __init__(self):
            self._elspeth_security_level = "OFFICIAL"
            self._elspeth_determinism_level = "low"
            self.determinism_level = "low"

    base_sinks = [csv_sink, DummySink()]
    clones = cli._clone_suite_sinks(base_sinks, "experiment")

    cloned_csv = clones[0]
    assert cloned_csv is not csv_sink
    assert cloned_csv.determinism_level == "guaranteed"
    assert getattr(cloned_csv, "_elspeth_determinism_level") == "guaranteed"
    assert Path(cloned_csv.path).name == "experiment_results.csv"

    passthrough_sink = clones[1]
    assert passthrough_sink is base_sinks[1]
    assert passthrough_sink.determinism_level == "low"
    assert getattr(passthrough_sink, "_elspeth_determinism_level") == "low"


def test_assemble_suite_defaults_merges_controls():
    orchestrator_config = SimpleNamespace(
        llm_prompt={"system": "sys", "user": "usr"},
        prompt_fields=["field"],
        criteria=None,
        row_plugin_defs=[{"name": "cfg_row"}],
        aggregator_plugin_defs=None,
        baseline_plugin_defs=None,
        validation_plugin_defs=None,
        sink_defs=None,
        prompt_pack="config_pack",
        llm_middleware_defs=None,
        prompt_defaults=None,
        concurrency_config=None,
        early_stop_plugin_defs=None,
        early_stop_config=None,
    )

    settings = SimpleNamespace(
        orchestrator_config=orchestrator_config,
        prompt_packs={"config_pack": {}, "suite_pack": {}},
        suite_defaults={
            "prompt_pack": "suite_pack",
            "row_plugins": [{"name": "suite_row"}],
            "rate_limiter": {"plugin": "fixed"},
            "cost_tracker": {"plugin": "cost"},
            "determinism_level": "high",
        },
        rate_limiter=SimpleNamespace(tag="rate"),
        cost_tracker=SimpleNamespace(tag="cost"),
    )

    defaults = cli._assemble_suite_defaults(settings)

    assert defaults["prompt_pack"] == "suite_pack"
    assert defaults["row_plugin_defs"] == [{"name": "suite_row"}]
    assert defaults["rate_limiter_def"] == {"plugin": "fixed"}
    assert defaults["cost_tracker_def"] == {"plugin": "cost"}
    assert defaults["rate_limiter"].tag == "rate"
    assert defaults["cost_tracker"].tag == "cost"
    assert defaults["determinism_level"] == "high"


def test_single_run_logs_failures(tmp_path, monkeypatch, caplog):
    output_file = tmp_path / "out.csv"

    class DummyDatasource:
        def load(self):
            return pd.DataFrame({"col": [1]})

    class FailingLLM:
        def generate(self, *, system_prompt, user_prompt, metadata=None):
            raise RuntimeError("llm boom")

    settings = argparse.Namespace(
        datasource=DummyDatasource(),
        llm=FailingLLM(),
        sinks=[],
        orchestrator_config=OrchestratorConfig(
            llm_prompt={"system": "sys", "user": "Prompt {col}"},
            prompt_fields=["col"],
            criteria=None,
            row_plugin_defs=None,
            aggregator_plugin_defs=None,
            sink_defs=None,
            prompt_pack=None,
            baseline_plugin_defs=None,
            retry_config={"max_attempts": 2, "initial_delay": 0},
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

    def fake_load_settings(path, profile="default"):
        return settings

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    monkeypatch.setattr(
        cli,
        "validate_suite",
        lambda *a, **k: SuiteValidationReport(report=ValidationReport(), preflight={}),
    )

    args = argparse.Namespace(
        settings="settings.yaml",
        profile="default",
        head=0,
        output_csv=output_file,
        log_level="INFO",
        suite_root=None,
        single_run=True,
        live_outputs=False,
        disable_metrics=False,
    )

    with caplog.at_level("ERROR"):
        cli.run(args)

    assert "Row processing failed" in caplog.text


def test_disable_metrics_strips_plugins(monkeypatch):
    captured = {}

    class DummyDatasource:
        def load(self):
            return pd.DataFrame({"col": [1]})

    class DummySettings:
        def __init__(self):
            self.datasource = DummyDatasource()
            self.llm = object()
            self.sinks = []
            self.orchestrator_config = OrchestratorConfig(
                llm_prompt={"system": "sys", "user": "Prompt {col}"},
                prompt_fields=["col"],
                criteria=None,
                row_plugin_defs=[{"name": "score_extractor", "determinism_level": "guaranteed"}],
                aggregator_plugin_defs=[{"name": "score_stats", "determinism_level": "guaranteed"}],
                sink_defs=None,
                prompt_pack=None,
                baseline_plugin_defs=[{"name": "score_delta", "determinism_level": "guaranteed"}],
                retry_config=None,
                checkpoint_config=None,
                llm_middleware_defs=None,
                prompt_defaults=None,
            )
            self.suite_root = None
            self.suite_defaults = {
                "row_plugins": [{"name": "score_extractor", "determinism_level": "guaranteed"}],
                "aggregator_plugins": [{"name": "score_stats", "determinism_level": "guaranteed"}],
                "baseline_plugins": [{"name": "score_delta", "determinism_level": "guaranteed"}],
            }
            self.rate_limiter = None
            self.cost_tracker = None
            self.prompt_packs = {
                "pack": {
                    "row_plugins": [{"name": "score_extractor", "determinism_level": "guaranteed"}],
                    "aggregator_plugins": [{"name": "score_stats", "determinism_level": "guaranteed"}],
                    "baseline_plugins": [{"name": "score_delta", "determinism_level": "guaranteed"}],
                }
            }
            self.prompt_pack = None
            self.config_path = None

    settings = DummySettings()

    def fake_load_settings(path, profile="default"):
        return settings

    class FakeOrchestrator:
        def __init__(self, *, config, **kwargs):
            captured["config"] = config

        def run(self):
            return {"results": []}

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "ExperimentOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(cli, "validate_settings", lambda *a, **k: ValidationReport())
    monkeypatch.setattr(
        cli,
        "validate_suite",
        lambda *a, **k: SuiteValidationReport(report=ValidationReport(), preflight={}),
    )

    args = argparse.Namespace(
        settings="settings.yaml",
        profile="default",
        head=0,
        output_csv=None,
        log_level="INFO",
        suite_root=None,
        single_run=True,
        live_outputs=False,
        disable_metrics=True,
    )

    cli.run(args)

    config = captured["config"]
    assert not config.row_plugin_defs
    assert not config.aggregator_plugin_defs
    assert not config.baseline_plugin_defs
    pack = settings.prompt_packs["pack"]
    assert not pack["row_plugins"]
    assert not pack["aggregator_plugins"]
    assert not pack["baseline_plugins"]
    defaults = settings.suite_defaults
    assert not defaults["row_plugins"]
    assert not defaults["aggregator_plugins"]
    assert not defaults["baseline_plugins"]
