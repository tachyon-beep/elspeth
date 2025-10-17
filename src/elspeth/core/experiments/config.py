"""Configuration models for experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from elspeth.core.config.schema import validate_experiment_config
from elspeth.core.experiments.plugin_registry import normalize_early_stop_definitions
from elspeth.core.validation.base import ConfigurationError

DEFAULT_INPUT_COST_PER_1K = 0.03
DEFAULT_OUTPUT_COST_PER_1K = 0.06
DEFAULT_AVG_INPUT_TOKENS = 2000
DEFAULT_ROW_COUNT = 100


class ExperimentConfig(BaseModel):
    """Runtime configuration for a single experiment run.

    This Pydantic model provides runtime validation and serialization
    for experiment configurations loaded from JSON files and prompt files.
    """

    # Required fields
    name: str
    temperature: float
    max_tokens: int

    # Boolean flags
    enabled: bool = True
    is_baseline: bool = False

    # Metadata
    description: str = ""
    hypothesis: str = ""
    author: str = "unknown"
    tags: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)

    # Prompts
    prompt_system: str = ""
    prompt_template: str = ""
    prompt_fields: list[str] | None = None
    criteria: list[dict[str, Any]] | None = None

    # Plugin definitions
    row_plugin_defs: list[dict[str, Any]] = Field(default_factory=list)
    aggregator_plugin_defs: list[dict[str, Any]] = Field(default_factory=list)
    sink_defs: list[dict[str, Any]] = Field(default_factory=list)
    baseline_plugin_defs: list[dict[str, Any]] = Field(default_factory=list)
    validation_plugin_defs: list[dict[str, Any]] = Field(default_factory=list)
    early_stop_plugin_defs: list[dict[str, Any]] = Field(default_factory=list)
    llm_middleware_defs: list[dict[str, Any]] = Field(default_factory=list)

    # Control definitions
    rate_limiter_def: dict[str, Any] | None = None
    cost_tracker_def: dict[str, Any] | None = None

    # Configuration options
    prompt_pack: str | None = None
    prompt_defaults: dict[str, Any] | None = None
    concurrency_config: dict[str, Any] | None = None
    security_level: str | None = None
    determinism_level: str | None = None
    early_stop_config: dict[str, Any] | None = None

    # Metadata
    path: Path | None = None

    model_config = ConfigDict(
        # Allow assignment after creation (mutable config objects)
        frozen=False,
        # Validate on assignment
        validate_assignment=True,
        # Allow arbitrary types (Path, etc.)
        arbitrary_types_allowed=True,
        # Be strict about extra fields
        extra="forbid",
    )

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Validate temperature is within reasonable bounds."""
        if not 0 <= v <= 2:
            raise ValueError(f"Temperature must be between 0 and 2, got {v}")
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        """Validate max_tokens is positive."""
        if v <= 0:
            raise ValueError(f"max_tokens must be positive, got {v}")
        return v

    @classmethod
    def from_file(cls, path: Path) -> "ExperimentConfig":
        """Construct an experiment config by reading JSON plus prompt overrides.

        This method loads configuration from:
        1. config.json - Primary configuration
        2. system_prompt.md - System prompt (if not in JSON)
        3. user_prompt.md - User prompt template (if not in JSON)

        Pydantic v2 automatically validates all fields during construction.
        """
        config_path = path
        data = json.loads(path.read_text(encoding="utf-8"))

        # Legacy JSON schema validation (will be replaced by Pydantic in future)
        try:
            validate_experiment_config(data)
        except ConfigurationError as exc:
            raise ValueError(f"Invalid experiment config '{config_path}': {exc}") from exc

        folder = path.parent

        # Load prompts from files if not in JSON
        prompt_system = data.get("prompt_system")
        if not prompt_system:
            system_path = folder / "system_prompt.md"
            prompt_system = system_path.read_text(encoding="utf-8") if system_path.exists() else ""

        prompt_template = data.get("prompt_template")
        if not prompt_template:
            user_path = folder / "user_prompt.md"
            prompt_template = user_path.read_text(encoding="utf-8") if user_path.exists() else ""

        # Normalize early stop definitions
        early_stop_plugin_defs = normalize_early_stop_definitions(data.get("early_stop_plugins")) or []
        if not early_stop_plugin_defs and data.get("early_stop"):
            early_stop_plugin_defs = normalize_early_stop_definitions(data.get("early_stop"))

        # Build config dict with defaults
        config_data = {
            "name": data.get("name", path.parent.name),
            "temperature": data.get("temperature", 0.7),
            "max_tokens": data.get("max_tokens", 512),
            "enabled": data.get("enabled", True),
            "is_baseline": data.get("is_baseline", False),
            "description": data.get("description", ""),
            "hypothesis": data.get("hypothesis", ""),
            "author": data.get("author", "unknown"),
            "tags": data.get("tags", []),
            "options": data,
            "prompt_system": prompt_system,
            "prompt_template": prompt_template,
            "prompt_fields": data.get("prompt_fields"),
            "criteria": data.get("criteria"),
            "row_plugin_defs": data.get("row_plugins", []),
            "aggregator_plugin_defs": data.get("aggregator_plugins", []),
            "sink_defs": data.get("sinks", []),
            "rate_limiter_def": data.get("rate_limiter"),
            "cost_tracker_def": data.get("cost_tracker"),
            "prompt_pack": data.get("prompt_pack"),
            "baseline_plugin_defs": data.get("baseline_plugins", []),
            "validation_plugin_defs": data.get("validation_plugins", []),
            "prompt_defaults": data.get("prompt_defaults"),
            "llm_middleware_defs": data.get("llm_middlewares", []),
            "concurrency_config": data.get("concurrency"),
            "security_level": data.get("security_level"),
            "determinism_level": data.get("determinism_level"),
            "early_stop_plugin_defs": early_stop_plugin_defs,
            "early_stop_config": data.get("early_stop"),
            "path": folder,
        }

        # Use Pydantic v2's model_validate for runtime validation
        return cls.model_validate(config_data)

    def to_export_dict(self) -> dict[str, Any]:
        """Serialize the configuration back into a JSON-compatible mapping.

        Uses Pydantic v2's model_dump() for efficient serialization,
        then merges with options and adds estimated cost.
        """
        # Start with options dict (contains original JSON data)
        payload = dict(self.options)

        # Use Pydantic's model_dump to get all fields (excludes None and defaults)
        model_data = self.model_dump(
            exclude={"options", "path"},  # Don't duplicate options, exclude Path
            exclude_none=True,  # Skip None values
            mode="python",  # Python objects, not JSON
        )

        # Update with model data (model fields override options)
        payload.update(model_data)

        # Add computed field
        payload["estimated_cost"] = self.estimated_cost()

        return payload

    def estimated_cost(
        self,
        *,
        row_count: int = DEFAULT_ROW_COUNT,
        avg_input_tokens: int = DEFAULT_AVG_INPUT_TOKENS,
        input_cost_per_1k: float = DEFAULT_INPUT_COST_PER_1K,
        output_cost_per_1k: float = DEFAULT_OUTPUT_COST_PER_1K,
    ) -> dict[str, float]:
        """Estimate token consumption and cost for a representative run."""

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

    def summary(self) -> dict[str, Any]:
        """Provide high-level metadata for reporting and dashboards."""

        return {
            "name": self.name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "is_baseline": self.is_baseline,
            "tags": list(self.tags),
            "estimated_cost": self.estimated_cost(),
            "validation_plugins": self.validation_plugin_defs,
        }


class ExperimentSuite(BaseModel):
    """Materialized experiment suite with baseline metadata.

    This Pydantic model represents a complete suite of experiments
    loaded from a directory structure.
    """

    root: Path
    experiments: list[ExperimentConfig]
    baseline: ExperimentConfig | None

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    @classmethod
    def load(cls, root: Path) -> "ExperimentSuite":
        """Load all experiment configs under ``root`` and select a baseline.

        Scans the directory for experiment folders, loads their configs,
        and automatically selects a baseline experiment.
        """
        experiments: list[ExperimentConfig] = []
        baseline: ExperimentConfig | None = None

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

        # Use Pydantic v2's model_validate for validation
        return cls.model_validate(
            {
                "root": root,
                "experiments": experiments,
                "baseline": baseline,
            }
        )
