"""Utilities for managing experiment suite assets."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml

from .config import ExperimentConfig, ExperimentSuite

DEFAULT_PROMPT_SYSTEM = "# System Prompt\n\nDefine the system prompt here."
DEFAULT_PROMPT_USER = "# User Prompt\n\nDefine the user prompt here."


def export_suite_configuration(suite: ExperimentSuite, output_path: str | Path) -> Path:
    """Export all experiment configurations to a single file."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    metadata = {
        "experiment_count": len(suite.experiments),
        "baseline": suite.baseline.name if suite.baseline else None,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = {
        "suite_metadata": metadata,
        "experiments": [exp.to_export_dict() for exp in suite.experiments],
    }

    if path.suffix.lower() in {".yaml", ".yml"}:
        path.write_text(yaml.dump(payload, default_flow_style=False), encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def create_experiment_template(
    suite: ExperimentSuite,
    name: str,
    *,
    base_experiment: str | None = None,
) -> Path:
    """Create a new experiment folder scaffolded from an existing configuration."""

    destination = suite.root / name
    if destination.exists():
        raise ValueError(f"Experiment '{name}' already exists at {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    base_config = _resolve_base_config(suite, base_experiment)
    config_payload: Dict[str, Any]

    if base_config and base_config.path:
        _copy_prompt_files(base_config, destination)
        config_payload = dict(base_config.to_export_dict())
    else:
        destination.joinpath("system_prompt.md").write_text(DEFAULT_PROMPT_SYSTEM, encoding="utf-8")
        destination.joinpath("user_prompt.md").write_text(DEFAULT_PROMPT_USER, encoding="utf-8")
        config_payload = {
            "description": "New experiment",
            "hypothesis": "To be defined",
            "author": "unknown",
            "tags": [],
            "expected_outcome": "To be defined",
            "temperature": 0.0,
            "max_tokens": 300,
            "enabled": False,
            "is_baseline": False,
        }

    config_payload["name"] = name
    config_payload["enabled"] = False
    config_payload["is_baseline"] = False
    config_payload["created_date"] = datetime.now(timezone.utc).isoformat()
    config_payload.pop("estimated_cost", None)

    (destination / "config.json").write_text(json.dumps(config_payload, indent=2), encoding="utf-8")
    return destination


def summarize_suite(suite: ExperimentSuite) -> Dict[str, Any]:
    """Return a lightweight summary of suite composition and estimated costs."""

    experiments = [exp.summary() for exp in suite.experiments]
    total_cost = sum(item["estimated_cost"]["estimated_total_cost"] for item in experiments)
    return {
        "total_experiments": len(experiments),
        "baseline": suite.baseline.name if suite.baseline else None,
        "experiments": experiments,
        "total_estimated_cost": total_cost,
    }


def _resolve_base_config(suite: ExperimentSuite, base_experiment: str | None) -> ExperimentConfig | None:
    if base_experiment:
        for exp in suite.experiments:
            if exp.name == base_experiment:
                return exp
    return suite.baseline


def _copy_prompt_files(source: ExperimentConfig, destination: Path) -> None:
    if not source.path:
        return
    for filename in ("system_prompt.md", "user_prompt.md"):
        src = source.path / filename
        dst = destination / filename
        if src.exists():
            shutil.copyfile(src, dst)
