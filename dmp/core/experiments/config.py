"""Configuration models for experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from dmp.core.config_schema import validate_experiment_config
from dmp.core.validation import ConfigurationError
from dmp.core.experiments.plugin_registry import normalize_early_stop_definitions


@dataclass
class ExperimentConfig:
    name: str
    temperature: float
    max_tokens: int
    enabled: bool = True
    is_baseline: bool = False
    description: str = ""
    hypothesis: str = ""
    author: str = "unknown"
    tags: List[str] = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)
    prompt_system: str = ""
    prompt_template: str = ""
    prompt_fields: Optional[List[str]] = None
    criteria: Optional[List[Dict[str, Any]]] = None
    row_plugin_defs: List[Dict[str, Any]] = field(default_factory=list)
    aggregator_plugin_defs: List[Dict[str, Any]] = field(default_factory=list)
    sink_defs: List[Dict[str, Any]] = field(default_factory=list)
    rate_limiter_def: Optional[Dict[str, Any]] = None
    cost_tracker_def: Optional[Dict[str, Any]] = None
    prompt_pack: Optional[str] = None
    baseline_plugin_defs: List[Dict[str, Any]] = field(default_factory=list)
    prompt_defaults: Optional[Dict[str, Any]] = None
    llm_middleware_defs: List[Dict[str, Any]] = field(default_factory=list)
    concurrency_config: Dict[str, Any] | None = None
    security_level: str | None = None
    early_stop_plugin_defs: List[Dict[str, Any]] = field(default_factory=list)
    early_stop_config: Dict[str, Any] | None = None

    @classmethod
    def from_file(cls, path: Path) -> "ExperimentConfig":
        config_path = path
        data = json.loads(path.read_text(encoding="utf-8"))
        try:
            validate_experiment_config(data)
        except ConfigurationError as exc:
            raise ValueError(f"Invalid experiment config '{config_path}': {exc}") from exc
        folder = path.parent

        prompt_system = data.get("prompt_system")
        if not prompt_system:
            system_path = folder / "system_prompt.md"
            prompt_system = system_path.read_text(encoding="utf-8") if system_path.exists() else ""

        prompt_template = data.get("prompt_template")
        if not prompt_template:
            user_path = folder / "user_prompt.md"
            prompt_template = user_path.read_text(encoding="utf-8") if user_path.exists() else ""

        early_stop_plugin_defs = normalize_early_stop_definitions(data.get("early_stop_plugins")) or []
        if not early_stop_plugin_defs and data.get("early_stop"):
            early_stop_plugin_defs = normalize_early_stop_definitions(data.get("early_stop"))

        return cls(
            name=data.get("name", path.parent.name),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 512),
            enabled=data.get("enabled", True),
            is_baseline=data.get("is_baseline", False),
            description=data.get("description", ""),
            hypothesis=data.get("hypothesis", ""),
            author=data.get("author", "unknown"),
            tags=data.get("tags", []),
            options=data,
            prompt_system=prompt_system,
            prompt_template=prompt_template,
            prompt_fields=data.get("prompt_fields"),
            criteria=data.get("criteria"),
            row_plugin_defs=data.get("row_plugins", []),
            aggregator_plugin_defs=data.get("aggregator_plugins", []),
            sink_defs=data.get("sinks", []),
            rate_limiter_def=data.get("rate_limiter"),
            cost_tracker_def=data.get("cost_tracker"),
            prompt_pack=data.get("prompt_pack"),
            baseline_plugin_defs=data.get("baseline_plugins", []),
            prompt_defaults=data.get("prompt_defaults"),
            llm_middleware_defs=data.get("llm_middlewares", []),
            concurrency_config=data.get("concurrency"),
            security_level=data.get("security_level"),
            early_stop_plugin_defs=early_stop_plugin_defs,
            early_stop_config=data.get("early_stop"),
        )


@dataclass
class ExperimentSuite:
    root: Path
    experiments: List[ExperimentConfig]
    baseline: Optional[ExperimentConfig]

    @classmethod
    def load(cls, root: Path) -> "ExperimentSuite":
        experiments: List[ExperimentConfig] = []
        baseline: Optional[ExperimentConfig] = None

        for folder in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
            config_path = folder / "config.json"
            if not config_path.exists():
                continue
            cfg = ExperimentConfig.from_file(config_path)
            if cfg.enabled:
                experiments.append(cfg)
                if cfg.is_baseline and baseline is None:
                    baseline = cfg

        if baseline is None and experiments:
            baseline = experiments[0]

        return cls(root=root, experiments=experiments, baseline=baseline)
