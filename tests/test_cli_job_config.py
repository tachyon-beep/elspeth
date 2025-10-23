from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

import elspeth.cli as cli


def test_run_with_job_config_identity_pipeline(tmp_path: Path):
    # Minimal source data
    input_csv = tmp_path / "input.csv"
    pd.DataFrame([{"payload": "a"}, {"payload": "b"}]).to_csv(input_csv, index=False)

    # Ad-hoc job with no LLM (identity write) and a CSV sink
    job = {
        "job": {
            "name": "adhoc",
            "datasource": {
                "plugin": "local_csv",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"path": str(input_csv), "retain_local": False},
            },
            "sinks": [
                {
                    "plugin": "csv",
                    "security_level": "OFFICIAL",
                    "determinism_level": "guaranteed",
                    "options": {"path": str(tmp_path / "results.csv")},
                }
            ],
        }
    }
    job_path = tmp_path / "job.yaml"
    job_path.write_text(yaml.safe_dump(job), encoding="utf-8")

    args = argparse.Namespace(
        job_config=job_path,
        head=0,
        artifacts_dir=None,
        signed_bundle=False,
        signing_key_env="ELSPETH_SIGNING_KEY",
        log_level="ERROR",
        # Unused by job path
        settings=None,
        profile="default",
        suite_root=None,
        single_run=True,
        live_outputs=False,
        disable_metrics=False,
        export_suite_config=None,
        create_experiment_template=None,
        template_base=None,
        reports_dir=None,
        output_csv=None,
        validate_schemas=False,
        artifact_sink_plugin=None,
        artifact_sink_config=None,
    )

    cli.run(args)

    out_csvs = list(tmp_path.glob("results.csv"))
    assert out_csvs, "expected job sink output file"
