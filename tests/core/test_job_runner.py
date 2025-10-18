from __future__ import annotations

from pathlib import Path

import pandas as pd

from elspeth.core.experiments.job_runner import run_job_config, run_job_file


def _make_csv(tmp_path: Path) -> Path:
    df = pd.DataFrame(
        [
            {"APPID": "A1", "title": "T1", "summary": "S1"},
            {"APPID": "A2", "title": "T2", "summary": "S2"},
        ]
    )
    path = tmp_path / "input.csv"
    df.to_csv(path, index=False)
    return path


def test_job_runner_with_llm_and_csv_sink(tmp_path: Path) -> None:
    csv_path = _make_csv(tmp_path)
    out_path = tmp_path / "out.csv"
    job = {
        "name": "test_job",
        "security_level": "OFFICIAL",
        "datasource": {
            "plugin": "local_csv",
            "security_level": "OFFICIAL",
            "options": {"path": str(csv_path), "retain_local": True},
        },
        "llm": {
            "plugin": "mock",
            "security_level": "OFFICIAL",
            "options": {"seed": 1},
        },
        "prompt": {
            "system": "sys",
            "user": "Summarize {{ summary }}",
            "fields": ["APPID", "title", "summary"],
        },
        "sinks": [
            {
                "plugin": "csv",
                "security_level": "OFFICIAL",
                "options": {"path": str(out_path), "overwrite": True},
            }
        ],
    }

    payload = run_job_config(job)
    assert isinstance(payload, dict)
    assert len(payload.get("results", [])) == 2
    assert out_path.exists()
    # File should not be empty
    assert out_path.stat().st_size > 0


def test_job_runner_identity_without_llm(tmp_path: Path) -> None:
    csv_path = _make_csv(tmp_path)
    out_path = tmp_path / "out.csv"
    job = {
        "name": "identity_job",
        "datasource": {
            "plugin": "local_csv",
            "security_level": "OFFICIAL",
            "options": {"path": str(csv_path), "retain_local": True},
        },
        "sinks": [
            {
                "plugin": "csv",
                "security_level": "OFFICIAL",
                "options": {"path": str(out_path), "overwrite": True},
            }
        ],
    }

    payload = run_job_config(job)
    assert isinstance(payload, dict)
    assert len(payload.get("results", [])) == 2
    assert out_path.exists()


def test_run_job_file(tmp_path: Path) -> None:
    csv_path = _make_csv(tmp_path)
    out_path = tmp_path / "out.csv"
    job_yaml = tmp_path / "job.yaml"
    job_yaml.write_text(
        f"""
job:
  datasource:
    plugin: local_csv
    security_level: OFFICIAL
    options:
      path: {csv_path}
      retain_local: true
  sinks:
    - plugin: csv
      security_level: OFFICIAL
      options:
        path: {out_path}
        overwrite: true
""",
        encoding="utf-8",
    )

    payload = run_job_file(job_yaml)
    assert isinstance(payload, dict)
    assert len(payload.get("results", [])) == 2
    assert out_path.exists()
