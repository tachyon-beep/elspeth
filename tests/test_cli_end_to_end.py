"""Integration coverage for CLI workflow."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from elspeth import cli


def test_cli_generates_suite_outputs(tmp_path: Path, monkeypatch) -> None:
    input_csv = tmp_path / "input.csv"
    pd.DataFrame([{"payload": "alpha"}, {"payload": "beta"}]).to_csv(input_csv, index=False)

    settings_data = {
        "default": {
            "datasource": {
                "plugin": "local_csv",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"path": str(input_csv)},
            },
            "llm": {
                "plugin": "mock",
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
                "options": {"seed": 123},
            },
            "sinks": [
                {
                    "plugin": "csv",
                    "security_level": "OFFICIAL",
                    "determinism_level": "guaranteed",
                    "options": {"path": str(tmp_path / "latest_results.csv")},
                }
            ],
            "prompts": {
                "system": "System prompt",
                "user": "User prompt {{ payload }}",
            },
            "prompt_fields": ["payload"],
        }
    }
    tmp_settings = tmp_path / "settings.yaml"
    tmp_settings.write_text(yaml.safe_dump(settings_data), encoding="utf-8")

    export_path = tmp_path / "suite_export.json"
    reports_dir = tmp_path / "reports"

    suite_root = tmp_path / "suite"
    baseline_dir = suite_root / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_config = {
        "name": "baseline",
        "enabled": True,
        "is_baseline": True,
        "temperature": 0.0,
        "max_tokens": 64,
        "prompt_system": "Baseline system",
        "prompt_template": "Echo {{ payload }}",
    }
    (baseline_dir / "config.json").write_text(json.dumps(baseline_config), encoding="utf-8")

    def _fake_report_generate(self, output_root: Path | str) -> None:
        root = Path(output_root)
        consolidated = root / "consolidated"
        consolidated.mkdir(parents=True, exist_ok=True)
        (consolidated / "analysis_config.json").write_text("{}", encoding="utf-8")
        (consolidated / "comparative_analysis.json").write_text("{}", encoding="utf-8")
        baseline_dir = root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "stats.json").write_text(json.dumps({"experiment": "baseline"}), encoding="utf-8")

    monkeypatch.setattr(cli.SuiteReportGenerator, "generate_all_reports", _fake_report_generate)

    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "--settings",
            str(tmp_settings),
            "--profile",
            "default",
            "--suite-root",
            str(suite_root),
            "--head",
            "0",
            "--export-suite-config",
            str(export_path),
            "--reports-dir",
            str(reports_dir),
            "--log-level",
            "ERROR",
        ]
    )

    cli.run(args)

    csv_outputs = sorted(tmp_path.glob("*latest_results.csv"))
    assert csv_outputs, "expected per-experiment CSV outputs"
    df = pd.read_csv(csv_outputs[0])
    assert not df.empty

    assert export_path.exists()
    export_payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert "experiments" in export_payload

    consolidated = reports_dir / "consolidated"
    assert (consolidated / "analysis_config.json").exists()
    assert (consolidated / "comparative_analysis.json").exists()
    # Individual experiment stats are emitted per experiment folder.
    baseline_stats = reports_dir / "baseline" / "stats.json"
    assert baseline_stats.exists()
    baseline_payload = json.loads(baseline_stats.read_text(encoding="utf-8"))
    assert baseline_payload["experiment"] == "baseline"
