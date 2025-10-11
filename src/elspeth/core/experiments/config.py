"""Configuration models for experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_INPUT_COST_PER_1K = 0.03
DEFAULT_OUTPUT_COST_PER_1K = 0.06
DEFAULT_AVG_INPUT_TOKENS = 2000
DEFAULT_ROW_COUNT = 100

from elspeth.core.config_schema import validate_experiment_config
from elspeth.core.experiments.plugin_registry import normalize_early_stop_definitions
from elspeth.core.validation import ConfigurationError


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
    validation_plugin_defs: List[Dict[str, Any]] = field(default_factory=list)
    prompt_defaults: Optional[Dict[str, Any]] = None
    llm_middleware_defs: List[Dict[str, Any]] = field(default_factory=list)
    concurrency_config: Dict[str, Any] | None = None
    security_level: str | None = None
    early_stop_plugin_defs: List[Dict[str, Any]] = field(default_factory=list)
    early_stop_config: Dict[str, Any] | None = None
    path: Path | None = None

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
            validation_plugin_defs=data.get("validation_plugins", []),
            prompt_defaults=data.get("prompt_defaults"),
            llm_middleware_defs=data.get("llm_middlewares", []),
            concurrency_config=data.get("concurrency"),
            security_level=data.get("security_level"),
            early_stop_plugin_defs=early_stop_plugin_defs,
            early_stop_config=data.get("early_stop"),
            path=folder,
        )

    def to_export_dict(self) -> Dict[str, Any]:
        payload = dict(self.options)
        payload.update(
            {
                "name": self.name,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "enabled": self.enabled,
                "is_baseline": self.is_baseline,
                "description": self.description,
                "hypothesis": self.hypothesis,
                "author": self.author,
                "tags": list(self.tags),
            }
        )
        if self.prompt_system:
            payload.setdefault("prompt_system", self.prompt_system)
        if self.prompt_template:
            payload.setdefault("prompt_template", self.prompt_template)
        if self.prompt_fields is not None:
            payload.setdefault("prompt_fields", list(self.prompt_fields))
        if self.criteria is not None:
            payload.setdefault("criteria", self.criteria)
        if self.rate_limiter_def:
            payload.setdefault("rate_limiter", self.rate_limiter_def)
        if self.cost_tracker_def:
            payload.setdefault("cost_tracker", self.cost_tracker_def)
        if self.llm_middleware_defs:
            payload.setdefault("llm_middlewares", self.llm_middleware_defs)
        if self.concurrency_config:
            payload.setdefault("concurrency", self.concurrency_config)
        if self.validation_plugin_defs:
            payload.setdefault("validation_plugins", self.validation_plugin_defs)
        if self.prompt_defaults:
            payload.setdefault("prompt_defaults", self.prompt_defaults)
        if self.sink_defs:
            payload.setdefault("sinks", self.sink_defs)
        payload.setdefault("estimated_cost", self.estimated_cost())
        return payload

    def estimated_cost(
        self,
        *,
        row_count: int = DEFAULT_ROW_COUNT,
        avg_input_tokens: int = DEFAULT_AVG_INPUT_TOKENS,
        input_cost_per_1k: float = DEFAULT_INPUT_COST_PER_1K,
        output_cost_per_1k: float = DEFAULT_OUTPUT_COST_PER_1K,
    ) -> Dict[str, float]:
        criteria_count = len(self.criteria or []) or 1
        total_requests = max(row_count, 1) * criteria_count
        total_input_tokens = total_requests * max(avg_input_tokens, 0)
        total_output_tokens = total_requests * max(self.max_tokens, 0)
        input_cost = (total_input_tokens / 1000.0) * input_cost_per_1k
        output_cost = (total_output_tokens / 1000.0) * output_cost_per_1k
        return {
            "estimated_requests": float(total_requests),
            "estimated_input_cost": float(input_cost),
            "estimated_output_cost": float(output_cost),
            "estimated_total_cost": float(input_cost + output_cost),
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "is_baseline": self.is_baseline,
            "tags": list(self.tags),
            "estimated_cost": self.estimated_cost(),
            "validation_plugins": self.validation_plugin_defs,
        }


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
