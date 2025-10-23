from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pytest

from elspeth.core.cli.job import execute_job_file
from elspeth.core.cli.single import maybe_write_artifacts_single, run_single


def test_maybe_write_artifacts_single_writes(tmp_path: Path):
    args = argparse.Namespace(artifacts_dir=tmp_path / "artifacts", signed_bundle=False, signing_key_env="ELSPETH_SIGNING_KEY")
    settings = argparse.Namespace(config_path=tmp_path / "settings.yaml")
    settings.config_path.write_text("key: value\n", encoding="utf-8")
    payload = {"results": [{"row": {"id": 1}}]}
    df = pd.DataFrame([{"id": 1}])

    maybe_write_artifacts_single(args, settings, payload, df)

    # Ensure results and settings snapshot were written
    out_dir = next((tmp_path / "artifacts").glob("*/"))
    results_file = out_dir / "single_results.json"
    settings_file = out_dir / "single_settings.yaml"
    assert results_file.exists() and settings_file.exists()


def test_execute_job_file_success(monkeypatch, tmp_path: Path):
    # Stub job runner
    def fake_run_job_file(path: Path):
        return {
            "results": [
                {
                    "row": {"appid": "1"},
                    "response": {"content": "ok", "metrics": {"score": 0.9}},
                    "retry": {"attempts": 1, "max_attempts": 3, "history": [{"delay": 0}]},
                }
            ]
        }

    import elspeth.core.experiments.job_runner as job_runner

    monkeypatch.setattr(job_runner, "run_job_file", fake_run_job_file)

    job_path = tmp_path / "job.yaml"
    job_path.write_text("job: {}\n", encoding="utf-8")

    payload, df = execute_job_file(job_path)
    assert payload["results"] and not df.empty
    assert "llm_content" in df.columns and "llm_content_metric_score" in df.columns
    assert "retry_attempts" in df.columns and df.loc[0, "retry_attempts"] == 1


def test_execute_job_file_raises_on_error(monkeypatch, tmp_path: Path):
    def bad_run_job_file(path: Path):  # noqa: D401
        raise ValueError("boom")

    import elspeth.core.experiments.job_runner as job_runner

    monkeypatch.setattr(job_runner, "run_job_file", bad_run_job_file)
    job_path = tmp_path / "job.yaml"
    job_path.write_text("job: {}\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        execute_job_file(job_path)


def test_run_single_writes_csv(monkeypatch, tmp_path: Path):
    # Fake orchestrator
    class FakeOrchestrator:
        def __init__(self, **kwargs):  # noqa: D401
            self.kwargs = kwargs

        def run(self):
            return {
                "results": [
                    {
                        "row": {"id": 1},
                        "response": {"content": "ok", "metrics": {"score": 0.2}},
                        "retry": {"attempts": 1, "max_attempts": 1, "history": []},
                    }
                ],
                "failures": [],
            }

    # Patch orchestrator used inside run_single
    import elspeth.core.orchestrator as orch

    monkeypatch.setattr(orch, "ExperimentOrchestrator", FakeOrchestrator)

    args = argparse.Namespace(output_csv=tmp_path / "out.csv", head=0, artifacts_dir=None, signed_bundle=False)
    settings = argparse.Namespace(
        datasource=object(),
        llm=object(),
        sinks=[],
        orchestrator_config=argparse.Namespace(),
        rate_limiter=None,
        cost_tracker=None,
        suite_root=None,
        config_path=None,
    )

    run_single(args, settings)
    assert (tmp_path / "out.csv").exists()


def test_run_single_strict_exits_on_failures(monkeypatch):
    class FailingOrchestrator:
        def __init__(self, **kwargs):  # noqa: D401
            pass

        def run(self):
            return {"results": [], "failures": [{"retry": {"attempts": 1}, "error": "x"}]}

    import elspeth.core.orchestrator as orch
    from elspeth.core.security.secure_mode import SecureMode
    import elspeth.core.security.secure_mode as sec

    monkeypatch.setattr(orch, "ExperimentOrchestrator", FailingOrchestrator)
    monkeypatch.setattr(sec, "get_secure_mode", lambda: SecureMode.STRICT)

    args = argparse.Namespace(output_csv=None, head=0, artifacts_dir=None, signed_bundle=False)
    settings = argparse.Namespace(
        datasource=object(),
        llm=object(),
        sinks=[],
        orchestrator_config=argparse.Namespace(),
        rate_limiter=None,
        cost_tracker=None,
        suite_root=None,
        config_path=None,
    )

    with pytest.raises(SystemExit):
        run_single(args, settings)


def test_run_single_prints_head(monkeypatch, tmp_path):
    class FakeOrchestrator:
        def __init__(self, **kwargs):  # noqa: D401
            pass

        def run(self):
            return {"results": [{"row": {"id": 1}}], "failures": []}

    import elspeth.core.orchestrator as orch

    monkeypatch.setattr(orch, "ExperimentOrchestrator", FakeOrchestrator)

    args = argparse.Namespace(output_csv=None, head=1, artifacts_dir=None, signed_bundle=False)
    settings = argparse.Namespace(
        datasource=object(),
        llm=object(),
        sinks=[],
        orchestrator_config=argparse.Namespace(),
        rate_limiter=None,
        cost_tracker=None,
        suite_root=None,
        config_path=None,
    )

    from io import StringIO
    import sys

    old = sys.stdout
    try:
        sys.stdout = StringIO()
        run_single(args, settings)
        out = sys.stdout.getvalue()
        assert "id" in out
    finally:
        sys.stdout = old
