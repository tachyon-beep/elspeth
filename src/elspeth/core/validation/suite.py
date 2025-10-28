"""Suite directory validation and preflight utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import elspeth.core.registries.middleware as llm_middleware_registry
from elspeth.core.controls import registry as controls_registry
from elspeth.core.experiments import plugin_registry as exp_registry
from elspeth.core.registry import central_registry
from elspeth.core.validation.base import ConfigurationError, ValidationReport, validate_schema

from .rules import (
    _validate_experiment_plugins,
    _validate_middleware_list,
    _validate_plugin_list,
)
from .schemas import EXPERIMENT_SCHEMA


@dataclass
class SuiteValidationReport:
    """Convenience wrapper bundling validation results with preflight data."""

    report: ValidationReport
    preflight: dict[str, Any] = field(default_factory=dict)

    def raise_if_errors(self) -> None:
        """Raise ``ConfigurationError`` if any validation errors exist."""

        self.report.raise_if_errors()


@dataclass
class _ExperimentSummary:
    """Lightweight summary of experiment configuration for suite reporting."""

    name: str
    enabled: bool
    is_baseline: bool
    criteria_count: int
    temperature: float
    max_tokens: int


def validate_suite(
    suite_root: str | Path,
    *,
    defaults: Mapping[str, Any] | None = None,
    row_estimate: int = 100,
) -> SuiteValidationReport:
    """Validate suite configuration folders and compute preflight metadata."""

    report = ValidationReport()
    suite_path = Path(suite_root)
    if not suite_path.exists():
        report.add_error("Suite root does not exist", context=str(suite_path))
        return SuiteValidationReport(report=report)

    _ = defaults  # reserved for future suite default overrides

    summaries, all_names, baseline_name, baseline_count = _collect_suite_experiments(
        suite_path,
        report,
    )

    if not summaries:
        report.add_error("No experiments found", context=str(suite_path))

    duplicates = _find_duplicates(all_names)
    for dup in duplicates:
        report.add_error(f"Duplicate experiment name '{dup}'", context="suite")

    if baseline_count == 0:
        report.add_error("No baseline experiment found", context="suite")

    preflight = _calculate_preflight(summaries, baseline_name, row_estimate, report)

    return SuiteValidationReport(report=report, preflight=preflight)


def _validate_prompt_files(report: ValidationReport, folder: Path, name: str, config: Mapping[str, Any]) -> None:
    """Ensure file-based prompts are present when inline definitions are absent."""

    if config.get("prompt_pack") or config.get("prompt_system") or config.get("prompt_template"):
        return
    system_path = folder / "system_prompt.md"
    user_path = folder / "user_prompt.md"
    if not system_path.exists() or not system_path.read_text(encoding="utf-8").strip():
        report.add_error("Missing or empty system prompt", context=f"experiment:{name}")
    if not user_path.exists() or not user_path.read_text(encoding="utf-8").strip():
        report.add_error("Missing or empty user prompt", context=f"experiment:{name}")


def _find_duplicates(items: Iterable[str]) -> list[str]:
    """Return the list of duplicate items found in ``items``."""

    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return [item for item, count in counts.items() if count > 1]


def _load_experiment_summary(
    folder: Path,
    report: ValidationReport,
) -> _ExperimentSummary | None:
    """Load and validate an experiment directory returning its summary."""

    sink_registry = central_registry.get_registry("sink")
    config_path = folder / "config.json"
    if not config_path.exists():
        return None

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.add_error(f"Invalid JSON: {exc}", context=str(config_path))
        return None

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            report.add_error(
                f"Profile data in {config_path} is a string but not valid JSON",
                context=str(config_path),
            )
            return None

    if not isinstance(data, dict):
        report.add_error(
            f"Experiment config must be a mapping, got {type(data).__name__}",
            context=str(config_path),
        )
        return None

    experiment_context = f"experiment:{folder.name}"
    for message in validate_schema(data, EXPERIMENT_SCHEMA, context=experiment_context):
        report.errors.append(message)

    name = str(data.get("name") or folder.name)
    enabled = bool(data.get("enabled", True))
    is_baseline = bool(data.get("is_baseline", False))

    _validate_experiment_plugins(
        report,
        data.get("row_plugins"),
        exp_registry.validate_row_plugin_definition,
        f"{experiment_context}.row_plugin",
    )
    _validate_experiment_plugins(
        report,
        data.get("aggregator_plugins"),
        exp_registry.validate_aggregation_plugin_definition,
        f"{experiment_context}.aggregation_plugin",
    )
    _validate_experiment_plugins(
        report,
        data.get("baseline_plugins"),
        exp_registry.validate_baseline_plugin_definition,
        f"{experiment_context}.baseline_plugin",
    )
    _validate_experiment_plugins(
        report,
        data.get("validation_plugins"),
        exp_registry.validate_validation_plugin_definition,
        f"{experiment_context}.validation_plugin",
    )
    _validate_experiment_plugins(
        report,
        data.get("early_stop_plugins"),
        exp_registry.validate_early_stop_plugin_definition,
        f"{experiment_context}.early_stop_plugin",
    )
    _validate_middleware_list(
        report,
        data.get("llm_middlewares"),
        llm_middleware_registry.validate_middleware_definition,
        context=f"{experiment_context}.middleware",
    )
    _validate_plugin_list(
        report,
        data.get("sinks"),
        sink_registry.validate,
        context=f"{experiment_context}.sink",
        require_security_level=True,
    )

    try:
        controls_registry.validate_rate_limiter(data.get("rate_limiter"))
    except ConfigurationError as exc:
        report.add_error(str(exc), context=f"{experiment_context}.rate_limiter")
    try:
        controls_registry.validate_cost_tracker(data.get("cost_tracker"))
    except ConfigurationError as exc:
        report.add_error(str(exc), context=f"{experiment_context}.cost_tracker")

    concurrency = data.get("concurrency")
    if concurrency is not None and not isinstance(concurrency, Mapping):
        report.add_error("'concurrency' must be a mapping", context=experiment_context)

    _validate_prompt_files(report, folder, name, data)

    criteria = data.get("criteria") or []
    criteria_count = len(criteria)
    temperature = float(data.get("temperature", 0.0) or 0.0)
    max_tokens = int(data.get("max_tokens", 0) or 0)

    return _ExperimentSummary(
        name=name,
        enabled=enabled,
        is_baseline=is_baseline,
        criteria_count=criteria_count,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _collect_suite_experiments(
    suite_path: Path,
    report: ValidationReport,
) -> tuple[list[_ExperimentSummary], list[str], str | None, int]:
    """Collect and validate experiment summaries from the suite directory."""

    summaries: list[_ExperimentSummary] = []
    all_names: list[str] = []
    baseline_name: str | None = None
    baseline_count = 0

    folders = sorted(p for p in suite_path.iterdir() if p.is_dir() and not p.name.startswith("."))
    for folder in folders:
        summary = _load_experiment_summary(folder, report)
        if summary is None:
            continue
        summaries.append(summary)
        all_names.append(summary.name)
        if summary.enabled and summary.is_baseline:
            baseline_name = summary.name
            baseline_count += 1

    return summaries, all_names, baseline_name, baseline_count


def _calculate_preflight(
    summaries: Sequence[_ExperimentSummary],
    baseline_name: str | None,
    row_estimate: int,
    report: ValidationReport,
) -> dict[str, Any]:
    """Compute preflight metrics for suite execution."""

    enabled = [summary for summary in summaries if summary.enabled]
    if baseline_name and not any(summary.name == baseline_name for summary in enabled):
        report.add_warning("Baseline experiment is disabled", context="suite")

    warnings: list[str] = []
    if any(summary.temperature > 0 for summary in enabled):
        warnings.append("High temperature experiments detected (non-deterministic)")
    if any(summary.max_tokens <= 0 for summary in enabled):
        warnings.append("Some experiments have max_tokens <= 0")
    if any(summary.max_tokens > 4096 for summary in enabled):
        warnings.append("High max_tokens detected (consider tighter limits)")

    if warnings:
        for warning in warnings:
            report.add_warning(warning, context="suite")

    criteria_counts = [max(summary.criteria_count, 1) for summary in enabled]
    estimated_calls = sum(row_estimate * count for count in criteria_counts)
    estimated_time_minutes = estimated_calls / 60 if estimated_calls else 0

    return {
        "experiment_count": len(enabled),
        "baseline": baseline_name,
        "estimated_api_calls": estimated_calls,
        "estimated_time_minutes": estimated_time_minutes,
        "warnings": warnings,
    }


__all__ = ["SuiteValidationReport", "validate_suite"]
