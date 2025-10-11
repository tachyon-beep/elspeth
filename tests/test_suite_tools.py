import json
from pathlib import Path

import pytest
import yaml

from elspeth.core.experiments.config import ExperimentSuite
from elspeth.core.experiments.tools import create_experiment_template, export_suite_configuration, summarize_suite


def _write_experiment(root: Path, name: str, *, enabled: bool = True, is_baseline: bool = False) -> Path:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    config = {
        "name": name,
        "temperature": 0.5,
        "max_tokens": 256,
        "enabled": enabled,
        "is_baseline": is_baseline,
        "tags": ["demo"],
        "criteria": [{"name": "quality"}],
    }
    (folder / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (folder / "system_prompt.md").write_text("System prompt", encoding="utf-8")
    (folder / "user_prompt.md").write_text("User prompt", encoding="utf-8")
    return folder


@pytest.fixture()
def suite(tmp_path: Path) -> ExperimentSuite:
    _write_experiment(tmp_path, "baseline", is_baseline=True)
    _write_experiment(tmp_path, "variant")
    return ExperimentSuite.load(tmp_path)


def test_export_suite_configuration_creates_payload(tmp_path: Path, suite: ExperimentSuite) -> None:
    output = tmp_path / "export.json"
    export_suite_configuration(suite, output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["suite_metadata"]["experiment_count"] == 2
    assert payload["suite_metadata"]["baseline"] == "baseline"
    experiment_names = {entry["name"] for entry in payload["experiments"]}
    assert experiment_names == {"baseline", "variant"}


def test_create_experiment_template_from_baseline(suite: ExperimentSuite, tmp_path: Path) -> None:
    destination = create_experiment_template(suite, "new_experiment")
    config = json.loads((destination / "config.json").read_text(encoding="utf-8"))
    assert config["name"] == "new_experiment"
    assert config["enabled"] is False
    assert config["is_baseline"] is False
    assert (destination / "system_prompt.md").exists()
    assert (destination / "user_prompt.md").exists()


def test_create_experiment_template_raises_when_exists(suite: ExperimentSuite) -> None:
    create_experiment_template(suite, "demo")
    with pytest.raises(ValueError):
        create_experiment_template(suite, "demo")


def test_summarize_suite_includes_estimated_costs(suite: ExperimentSuite) -> None:
    summary = summarize_suite(suite)
    assert summary["total_experiments"] == 2
    assert summary["baseline"] == "baseline"
    assert summary["total_estimated_cost"] >= 0
    assert len(summary["experiments"]) == 2


def test_export_suite_configuration_yaml(tmp_path: Path, suite: ExperimentSuite) -> None:
    output = tmp_path / "export.yaml"
    export_suite_configuration(suite, output)
    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert data["suite_metadata"]["baseline"] == "baseline"
    assert {item["name"] for item in data["experiments"]} == {"baseline", "variant"}


def test_create_experiment_template_with_base_experiment(tmp_path: Path) -> None:
    baseline_folder = _write_experiment(tmp_path, "baseline", is_baseline=True)
    (baseline_folder / "config.json").write_text(
        json.dumps(
            {
                "name": "baseline",
                "temperature": 0.3,
                "max_tokens": 128,
                "enabled": True,
                "is_baseline": True,
                "tags": ["root"],
            }
        ),
        encoding="utf-8",
    )
    suite = ExperimentSuite.load(tmp_path)
    destination = create_experiment_template(suite, "clone", base_experiment="baseline")
    config = json.loads((destination / "config.json").read_text(encoding="utf-8"))
    assert config["name"] == "clone"
    assert config["enabled"] is False
    assert config["is_baseline"] is False
    assert config["tags"] == ["root"]
    assert (destination / "system_prompt.md").read_text(encoding="utf-8") == "System prompt"
    assert (destination / "user_prompt.md").read_text(encoding="utf-8") == "User prompt"


def test_create_experiment_template_defaults_when_no_base(tmp_path: Path) -> None:
    suite = ExperimentSuite(root=tmp_path, experiments=[], baseline=None)
    destination = create_experiment_template(suite, "fresh")
    config = json.loads((destination / "config.json").read_text(encoding="utf-8"))
    assert config["name"] == "fresh"
    assert config["temperature"] == 0.0
    assert (destination / "system_prompt.md").exists()
    assert (destination / "user_prompt.md").exists()
