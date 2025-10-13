import json
from pathlib import Path

import pandas as pd

from elspeth.core.experiments import plugin_registry
from elspeth.core.experiments.config import ExperimentSuite
from elspeth.core.experiments.runner import ExperimentRunner
from elspeth.core.experiments.suite_runner import ExperimentSuiteRunner
from elspeth.plugins.llms.mock import MockLLMClient
from elspeth.plugins.outputs.csv_file import CsvResultSink
from elspeth.plugins.outputs.local_bundle import LocalBundleSink


def test_end_to_end_local_pipeline(tmp_path, assert_sanitized_artifact):
    data = pd.DataFrame({"APPID": ["1", "2"], "value": ["low", "high"]})
    bundle_dir = tmp_path / "bundles"
    csv_path = tmp_path / "results.csv"

    bundle_sink = LocalBundleSink(base_path=bundle_dir, timestamped=False, write_json=True, write_csv=True)
    setattr(bundle_sink, "_elspeth_security_level", "official")
    csv_sink = CsvResultSink(path=csv_path, overwrite=True)
    setattr(csv_sink, "_elspeth_security_level", "official")

    runner = ExperimentRunner(
        llm_client=MockLLMClient(seed=7),
        sinks=[bundle_sink, csv_sink],
        prompt_system="Rate the submission",
        prompt_template="Value: {{ value }}",
        prompt_fields=["value"],
        prompt_defaults={"audience": "quality"},
        row_plugins=[plugin_registry.create_row_plugin({"name": "score_extractor", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})],
        aggregator_plugins=[plugin_registry.create_aggregation_plugin({"name": "score_stats", "security_level": "OFFICIAL", "determinism_level": "guaranteed"})],
        validation_plugins=[
            plugin_registry.create_validation_plugin(
                {"name": "regex_match", "security_level": "OFFICIAL", "determinism_level": "guaranteed", "options": {"pattern": r"(?s).*\[mock\].*"}}
            )
        ],
        experiment_name="local_pipeline",
    )

    results = runner.run(data)

    assert results["results"], "runner should return per-row results"
    assert results["aggregates"]["score_stats"]["overall"]["count"] == len(data)
    assert csv_path.exists()

    manifest_matches = list(bundle_dir.glob("*/manifest.json"))
    assert manifest_matches, "local bundle sink should emit a manifest"
    manifest = json.loads(manifest_matches[0].read_text(encoding="utf-8"))
    assert manifest["rows"] == len(data)
    assert "value" in manifest.get("columns", [])
    assert manifest["sanitization"] == {"enabled": True, "guard": "'"}

    assert_sanitized_artifact(csv_path)


def _write_experiment(root: Path, name: str, *, is_baseline: bool = False, prompt_pack: str | None = None) -> None:
    exp_dir = root / name
    exp_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": name,
        "enabled": True,
        "is_baseline": is_baseline,
        "temperature": 0.0,
        "max_tokens": 32,
    }
    if prompt_pack:
        payload["prompt_pack"] = prompt_pack
    (exp_dir / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    (exp_dir / "system_prompt.md").write_text("System for " + name, encoding="utf-8")
    (exp_dir / "user_prompt.md").write_text("User prompt {{ value }}", encoding="utf-8")


def test_suite_runner_end_to_end_without_azure(tmp_path, assert_sanitized_artifact):
    suite_root = tmp_path / "suite"
    bundle_root = tmp_path / "suite_bundles"

    _write_experiment(suite_root, "baseline", is_baseline=True, prompt_pack="base_pack")
    _write_experiment(suite_root, "variant", prompt_pack="variant_pack")

    suite = ExperimentSuite.load(suite_root)
    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=MockLLMClient(seed=13),
        sinks=[],
    )

    defaults = {
        "prompt_system": "Evaluate response",
        "prompt_template": "Provide feedback for {{ value }}",
        "prompt_fields": ["value"],
        "prompt_defaults": {"audience": "review"},
        "row_plugin_defs": [{"name": "score_extractor", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
        "aggregator_plugin_defs": [{"name": "score_stats", "security_level": "OFFICIAL", "determinism_level": "guaranteed"}],
        "validation_plugin_defs": [{"name": "regex_match", "security_level": "OFFICIAL", "determinism_level": "guaranteed", "options": {"pattern": r"(?s).*\[mock\].*"}}],
        "sink_defs": [
            {
                "plugin": "local_bundle",
                "security_level": "OFFICIAL", "determinism_level": "guaranteed",
                "options": {
                    "base_path": bundle_root.as_posix(),
                    "timestamped": False,
                    "write_json": True,
                    "write_csv": True,
                },
            }
        ],
        "prompt_packs": {
            "base_pack": {
                "prompts": {
                    "system": "Base system",
                    "user": "Base prompt {{ value }}",
                }
            },
            "variant_pack": {
                "prompts": {
                    "system": "Variant system",
                    "user": "Variant prompt {{ value }}",
                },
                "prompt_defaults": {"audience": "executive"},
            },
        },
    }

    df = pd.DataFrame({"value": ["alpha", "beta"]})
    results = runner.run(df, defaults=defaults)

    assert set(results.keys()) == {"baseline", "variant"}
    baseline_payload = results["baseline"]["payload"]
    variant_payload = results["variant"]["payload"]

    assert baseline_payload["aggregates"]["score_stats"]["overall"]["count"] == len(df)
    assert variant_payload["aggregates"]["score_stats"]["overall"]["count"] == len(df)

    manifest_files = sorted(bundle_root.glob("**/manifest.json"))
    assert manifest_files, "local bundle sink should emit a manifest"

    manifest_path = manifest_files[-1]
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["rows"] == len(df)
    assert manifest_data["sanitization"] == {"enabled": True, "guard": "'"}

    csv_artifact = manifest_path.parent / "results.csv"
    if csv_artifact.exists():
        assert_sanitized_artifact(csv_artifact)
