"""Validation utilities and error reporting helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence, Tuple

import yaml


class ConfigurationError(RuntimeError):
    """Raised when configuration validation fails."""


@dataclass
class ValidationMessage:
    """Represents a single validation outcome with optional context."""

    message: str
    context: str | None = None

    def format(self) -> str:
        """Return a human-readable message suitable for user display."""

        if self.context:
            return f"{self.context}: {self.message}"
        return self.message


@dataclass
class ValidationReport:
    """Aggregates validation errors and warnings for a configuration."""

    errors: List[ValidationMessage] = field(default_factory=list)
    warnings: List[ValidationMessage] = field(default_factory=list)

    def add_error(self, message: str, context: str | None = None) -> None:
        """Record an error message with optional context."""

        self.errors.append(ValidationMessage(message=message, context=context))

    def add_warning(self, message: str, context: str | None = None) -> None:
        """Record a warning message with optional context."""

        self.warnings.append(ValidationMessage(message=message, context=context))

    def extend(self, other: "ValidationReport") -> None:
        """Merge another report into this one."""

        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def raise_if_errors(self) -> None:
        """Raise a ConfigurationError when the report contains errors."""

        if self.errors:
            formatted = "\n".join(msg.format() for msg in self.errors)
            raise ConfigurationError(formatted)

    def has_errors(self) -> bool:
        """Return True if the report contains errors."""

        return bool(self.errors)

    def has_warnings(self) -> bool:
        """Return True if the report contains warnings."""

        return bool(self.warnings)


def validate_schema(
    data: Mapping[str, object] | None,
    schema: Mapping[str, object],
    *,
    context: str | None = None,
) -> Iterable[ValidationMessage]:
    """Validate ``data`` against ``schema`` returning validation messages."""

    if data is None:
        yield ValidationMessage("value is missing", context=context)
        return

    errors: List[tuple[Tuple[object, ...], str]] = []
    _validate_node(data, schema, (), errors)
    for path, message in errors:
        pointer = _format_error_path(path)
        details = message
        if pointer:
            details = f"{details} (path: {pointer})"
        yield ValidationMessage(details, context=context)


def _validate_node(
    value: Any,
    schema: Mapping[str, Any],
    path: Tuple[object, ...],
    errors: List[tuple[Tuple[object, ...], str]],
) -> None:
    """Recursively validate ``value`` against ``schema`` accumulating errors."""

    if schema is None:
        return

    any_of = schema.get("anyOf")
    if any_of:
        for option in any_of:
            option_errors: List[tuple[Tuple[object, ...], str]] = []
            _validate_node(value, option, path, option_errors)
            if not option_errors:
                break
        else:
            errors.append((path, "did not match any allowed schemas"))

    expected_type = schema.get("type")
    if expected_type:
        if not _check_type(value, expected_type):
            errors.append((path, f"must be of type {expected_type}"))
            return

    if isinstance(value, Mapping):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append((path + (key,), "is a required property"))
        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in value:
                _validate_node(value[key], subschema, path + (key,), errors)

    if isinstance(value, list):
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_node(item, item_schema, path + (index,), errors)

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        errors.append((path, f"must be one of {enum}"))

    minimum = schema.get("minimum")
    if minimum is not None and _is_number(value) and value < minimum:
        errors.append((path, f"must be >= {minimum}"))

    exclusive_min = schema.get("exclusiveMinimum")
    if exclusive_min is not None and _is_number(value) and value <= exclusive_min:
        errors.append((path, f"must be > {exclusive_min}"))


def _check_type(value: Any, expected: str) -> bool:
    """Return True when ``value`` matches the schema ``expected`` type."""

    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return _is_number(value)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _is_number(value: Any) -> bool:
    """Return True for numeric values excluding booleans."""

    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_error_path(path: Iterable[object]) -> str:
    parts = []
    for item in path:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            if parts:
                parts.append(".")
            parts.append(str(item))
    return "".join(parts)


def validate_settings(path: str | Path, profile: str = "default") -> ValidationReport:
    """Validate a settings YAML profile and return accumulated messages."""

    report = ValidationReport()
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        report.add_error("Settings file not found", context=str(config_path))
        return report
    except yaml.YAMLError as exc:  # pragma: no cover - invalid yaml
        report.add_error(f"Invalid YAML: {exc}", context=str(config_path))
        return report

    profile_data = raw.get(profile)
    if profile_data is None:
        report.add_error(f"Profile '{profile}' not found", context=str(config_path))
        return report

    for message in validate_schema(profile_data, _SETTINGS_SCHEMA, context=f"settings[{profile}]"):
        report.errors.append(message)
    if report.has_errors():
        return report

    from elspeth.core import registry as core_registry  # pylint: disable=import-outside-toplevel
    from elspeth.core.controls import registry as controls_registry  # pylint: disable=import-outside-toplevel
    from elspeth.core.experiments import plugin_registry as exp_registry  # pylint: disable=import-outside-toplevel
    from elspeth.core.llm import registry as llm_registry  # pylint: disable=import-outside-toplevel

    registry = core_registry.registry

    _validate_plugin_reference(
        report,
        profile_data.get("datasource"),
        kind="datasource",
        validator=registry.validate_datasource,
    )
    _validate_plugin_reference(
        report,
        profile_data.get("llm"),
        kind="llm",
        validator=registry.validate_llm,
    )

    sinks = profile_data.get("sinks")
    has_top_level_sinks = isinstance(sinks, list) and bool(sinks)
    if sinks is not None and not isinstance(sinks, list):
        report.add_error("'sinks' must be a list when provided", context=f"settings[{profile}]")
    if has_top_level_sinks:
        for entry in sinks:
            _validate_plugin_reference(
                report,
                entry,
                kind="sink",
                validator=registry.validate_sink,
            )
    else:
        prompt_pack_name = profile_data.get("prompt_pack")
        prompt_packs_raw = profile_data.get("prompt_packs")
        fallback_from_prompt_pack = False
        if isinstance(prompt_packs_raw, Mapping) and prompt_pack_name:
            pack_definition = prompt_packs_raw.get(prompt_pack_name)
            if isinstance(pack_definition, Mapping):
                pack_sinks = pack_definition.get("sinks")
                if isinstance(pack_sinks, list) and pack_sinks:
                    fallback_from_prompt_pack = True

        suite_defaults_raw = profile_data.get("suite_defaults")
        fallback_from_suite_defaults = False
        if isinstance(suite_defaults_raw, Mapping):
            defaults_sinks = suite_defaults_raw.get("sinks")
            if isinstance(defaults_sinks, list) and defaults_sinks:
                fallback_from_suite_defaults = True
            else:
                suite_defaults_pack = suite_defaults_raw.get("prompt_pack")
                if isinstance(prompt_packs_raw, Mapping) and suite_defaults_pack:
                    pack_definition = prompt_packs_raw.get(suite_defaults_pack)
                    if isinstance(pack_definition, Mapping):
                        pack_sinks = pack_definition.get("sinks")
                        if isinstance(pack_sinks, list) and pack_sinks:
                            fallback_from_suite_defaults = True

        if not (fallback_from_prompt_pack or fallback_from_suite_defaults):
            report.add_error(
                "'sinks' must be provided either at the profile level, via prompt pack, or suite defaults",
                context=f"settings[{profile}]",
            )

    prompt_packs = profile_data.get("prompt_packs") or {}
    if not isinstance(prompt_packs, Mapping):
        report.add_error("'prompt_packs' must be a mapping", context=f"settings[{profile}]")
        prompt_packs = {}
    for name, pack in prompt_packs.items():
        _validate_prompt_pack(report, name, pack, registry, exp_registry, llm_registry)

    _validate_middleware_list(
        report,
        profile_data.get("llm_middlewares"),
        llm_registry.validate_middleware_definition,
        context=f"settings[{profile}].middleware",
    )

    prompt_pack_name = profile_data.get("prompt_pack")
    if prompt_pack_name and prompt_pack_name not in prompt_packs:
        available = ", ".join(sorted(prompt_packs)) or "<none>"
        report.add_error(
            f"Unknown prompt pack '{prompt_pack_name}'. Available prompt packs: {available}",
            context=f"settings[{profile}].prompt_pack",
        )

    suite_defaults = profile_data.get("suite_defaults") or {}
    if not isinstance(suite_defaults, Mapping):
        report.add_error("'suite_defaults' must be a mapping", context=f"settings[{profile}]")
        suite_defaults = {}
    _validate_suite_defaults(report, suite_defaults, registry, exp_registry, llm_registry, controls_registry)

    for key in ("retry", "checkpoint", "concurrency"):
        value = profile_data.get(key)
        if value is not None and not isinstance(value, Mapping):
            report.add_error(f"'{key}' must be a mapping", context=f"settings[{profile}]")

    return report


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

    from elspeth.core import registry as core_registry  # pylint: disable=import-outside-toplevel
    from elspeth.core.controls import registry as controls_registry  # pylint: disable=import-outside-toplevel
    from elspeth.core.experiments import plugin_registry as exp_registry  # pylint: disable=import-outside-toplevel
    from elspeth.core.llm import registry as llm_registry  # pylint: disable=import-outside-toplevel

    registry = core_registry.registry
    _ = defaults  # reserved for future suite default overrides

    summaries, names, baseline_name, baseline_count = _collect_suite_experiments(
        suite_path,
        report,
        registry,
        exp_registry,
        llm_registry,
        controls_registry,
    )

    if not summaries:
        report.add_error("No experiments found", context=str(suite_path))

    duplicates = _find_duplicates(names)
    for dup in duplicates:
        report.add_error(f"Duplicate experiment name '{dup}'", context="suite")

    if baseline_count == 0:
        report.add_error("No baseline experiment found", context="suite")

    preflight = _calculate_preflight(summaries, baseline_name, row_estimate, report)

    return SuiteValidationReport(report=report, preflight=preflight)


def _validate_plugin_reference(
    report: ValidationReport,
    entry: Any,
    *,
    kind: str,
    validator: Callable[[str, Dict[str, Any] | None], None],
) -> None:
    """Validate a single plugin reference entry."""
    if not isinstance(entry, Mapping):
        report.add_error(f"{kind} configuration must be a mapping", context=kind)
        return
    plugin = entry.get("plugin")
    if not plugin:
        report.add_error("Missing 'plugin'", context=kind)
        return
    if not isinstance(plugin, str):
        report.add_error("Plugin name must be a string", context=kind)
        return
    options = entry.get("options")
    options_dict: Dict[str, Any] | None
    if options is None:
        options_dict = None
    elif isinstance(options, Mapping):
        options_dict = dict(options)
    else:
        report.add_error("Options must be a mapping", context=f"{kind}:{plugin}")
        options_dict = {}
    try:
        validator(plugin, options_dict)
    except (ValueError, ConfigurationError) as exc:
        report.add_error(str(exc), context=f"{kind}:{plugin}")


def _validate_plugin_list(
    report: ValidationReport,
    entries: Any,
    validator: Callable[[str, Dict[str, Any] | None], None],
    *,
    context: str,
) -> None:
    """Validate a list of plugin references using ``validator``."""
    if entries is None:
        return
    if not isinstance(entries, list):
        report.add_error("Expected a list of plugin definitions", context=context)
        return
    for entry in entries:
        _validate_plugin_reference(report, entry, kind=context, validator=validator)


def _validate_prompt_pack(
    report: ValidationReport,
    name: str,
    pack: Any,
    registry,
    exp_registry,
    llm_registry,
) -> None:
    """Validate a prompt pack configuration entry."""
    context = f"prompt_pack:{name}"
    if not isinstance(pack, Mapping):
        report.add_error("Prompt pack must be a mapping", context=context)
        return
    prompts = pack.get("prompts")
    if prompts is not None:
        if not isinstance(prompts, Mapping):
            report.add_error("'prompts' must be a mapping", context=context)
        else:
            if "system" not in prompts or "user" not in prompts:
                report.add_error(
                    "Prompt pack prompts must include 'system' and 'user'",
                    context=context,
                )

    _validate_experiment_plugins(
        report,
        pack.get("row_plugins"),
        exp_registry.validate_row_plugin_definition,
        f"{context}.row_plugin",
    )
    _validate_experiment_plugins(
        report,
        pack.get("aggregator_plugins"),
        exp_registry.validate_aggregation_plugin_definition,
        f"{context}.aggregation_plugin",
    )
    _validate_experiment_plugins(
        report,
        pack.get("baseline_plugins"),
        exp_registry.validate_baseline_plugin_definition,
        f"{context}.baseline_plugin",
    )
    _validate_experiment_plugins(
        report,
        pack.get("validation_plugins"),
        exp_registry.validate_validation_plugin_definition,
        f"{context}.validation_plugin",
    )
    _validate_experiment_plugins(
        report,
        pack.get("early_stop_plugins"),
        exp_registry.validate_early_stop_plugin_definition,
        f"{context}.early_stop_plugin",
    )
    _validate_middleware_list(
        report,
        pack.get("llm_middlewares"),
        llm_registry.validate_middleware_definition,
        context=f"{context}.middleware",
    )
    _validate_plugin_list(report, pack.get("sinks"), registry.validate_sink, context=f"{context}.sink")


def _validate_suite_defaults(
    report: ValidationReport,
    defaults: Mapping[str, Any],
    registry,
    exp_registry,
    llm_registry,
    controls_registry,
) -> None:
    """Validate suite-level default configuration entries."""
    _validate_experiment_plugins(
        report,
        defaults.get("row_plugins"),
        exp_registry.validate_row_plugin_definition,
        "suite_defaults.row_plugin",
    )
    _validate_experiment_plugins(
        report,
        defaults.get("aggregator_plugins"),
        exp_registry.validate_aggregation_plugin_definition,
        "suite_defaults.aggregation_plugin",
    )
    _validate_experiment_plugins(
        report,
        defaults.get("baseline_plugins"),
        exp_registry.validate_baseline_plugin_definition,
        "suite_defaults.baseline_plugin",
    )
    _validate_experiment_plugins(
        report,
        defaults.get("validation_plugins"),
        exp_registry.validate_validation_plugin_definition,
        "suite_defaults.validation_plugin",
    )
    _validate_experiment_plugins(
        report,
        defaults.get("early_stop_plugins"),
        exp_registry.validate_early_stop_plugin_definition,
        "suite_defaults.early_stop_plugin",
    )
    _validate_middleware_list(
        report,
        defaults.get("llm_middlewares"),
        llm_registry.validate_middleware_definition,
        context="suite_defaults.middleware",
    )
    _validate_plugin_list(
        report,
        defaults.get("sinks"),
        registry.validate_sink,
        context="suite_defaults.sink",
    )
    try:
        controls_registry.validate_rate_limiter(defaults.get("rate_limiter"))
    except ConfigurationError as exc:
        report.add_error(str(exc), context="suite_defaults.rate_limiter")
    try:
        controls_registry.validate_cost_tracker(defaults.get("cost_tracker"))
    except ConfigurationError as exc:
        report.add_error(str(exc), context="suite_defaults.cost_tracker")


def _validate_experiment_plugins(
    report: ValidationReport,
    entries: Any,
    validator: Callable[[Dict[str, Any]], None],
    context: str,
) -> None:
    """Validate experiment plugin definitions using ``validator``."""

    if entries is None:
        return
    if not isinstance(entries, list):
        report.add_error("Expected a list of plugin definitions", context=context)
        return
    for definition in entries:
        if not isinstance(definition, Mapping):
            report.add_error("Plugin definition must be a mapping", context=context)
            continue
        try:
            validator(dict(definition))
        except ConfigurationError as exc:
            report.add_error(str(exc), context=context)
        except ValueError as exc:
            report.add_error(str(exc), context=context)


def _validate_middleware_list(
    report: ValidationReport,
    entries: Any,
    validator: Callable[[Dict[str, Any]], None],
    *,
    context: str,
) -> None:
    """Validate middleware entries using ``validator``."""
    if entries is None:
        return
    if not isinstance(entries, list):
        report.add_error("Expected a list of middleware definitions", context=context)
        return
    for definition in entries:
        if not isinstance(definition, Mapping):
            report.add_error("Middleware definition must be a mapping", context=context)
            continue
        try:
            validator(dict(definition))
        except ConfigurationError as exc:
            report.add_error(str(exc), context=context)
        except ValueError as exc:
            report.add_error(str(exc), context=context)


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


def _find_duplicates(items: Iterable[str]) -> List[str]:
    """Return the list of duplicate items found in ``items``."""
    counts: Dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return [item for item, count in counts.items() if count > 1]


def _load_experiment_summary(
    folder: Path,
    report: ValidationReport,
    registry,
    exp_registry,
    llm_registry,
    controls_registry,
) -> _ExperimentSummary | None:
    """Load and validate an experiment directory returning its summary."""

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
        except json.JSONDecodeError as exc:
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
    for message in validate_schema(data, _EXPERIMENT_SCHEMA, context=experiment_context):
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
        llm_registry.validate_middleware_definition,
        context=f"{experiment_context}.middleware",
    )
    _validate_plugin_list(
        report,
        data.get("sinks"),
        registry.validate_sink,
        context=f"{experiment_context}.sink",
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
    registry,
    exp_registry,
    llm_registry,
    controls_registry,
) -> tuple[List[_ExperimentSummary], List[str], str | None, int]:
    """Collect and validate experiment summaries from the suite directory."""

    summaries: List[_ExperimentSummary] = []
    enabled_names: List[str] = []
    baseline_name: str | None = None
    baseline_count = 0

    folders = sorted(p for p in suite_path.iterdir() if p.is_dir() and not p.name.startswith("."))
    for folder in folders:
        summary = _load_experiment_summary(folder, report, registry, exp_registry, llm_registry, controls_registry)
        if summary is None:
            continue
        summaries.append(summary)
        if summary.enabled:
            enabled_names.append(summary.name)
            if summary.is_baseline:
                baseline_count += 1
                baseline_name = summary.name

    return summaries, enabled_names, baseline_name, baseline_count


def _calculate_preflight(
    summaries: Sequence[_ExperimentSummary],
    baseline_name: str | None,
    row_estimate: int,
    report: ValidationReport,
) -> Dict[str, Any]:
    """Compute preflight metadata and register warnings on the report."""

    warnings: List[str] = []
    enabled = [summary for summary in summaries if summary.enabled]

    for summary in enabled:
        if summary.temperature > 1.5:
            warning = f"High temperature ({summary.temperature}) for experiment '{summary.name}'"
            warnings.append(warning)
            report.add_warning(warning, context="suite")
        if summary.max_tokens > 2000:
            warning = f"High max_tokens ({summary.max_tokens}) for experiment '{summary.name}'"
            warnings.append(warning)
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


__all__ = [
    "ConfigurationError",
    "ValidationMessage",
    "ValidationReport",
    "validate_schema",
    "validate_settings",
    "SuiteValidationReport",
    "validate_suite",
]


_PLUGIN_REFERENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "plugin": {"type": "string"},
        "options": {"type": "object"},
    },
    "required": ["plugin"],
    "additionalProperties": True,
}

_MIDDLEWARE_DEF_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "plugin": {"type": "string"},
        "options": {"type": "object"},
    },
    "anyOf": [
        {"required": ["name"]},
        {"required": ["plugin"]},
    ],
    "additionalProperties": True,
}

_PLUGIN_DEF_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "options": {"type": "object"},
    },
    "required": ["name"],
    "additionalProperties": True,
}

_SETTINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "datasource": _PLUGIN_REFERENCE_SCHEMA,
        "llm": _PLUGIN_REFERENCE_SCHEMA,
        "sinks": {
            "type": "array",
            "items": _PLUGIN_REFERENCE_SCHEMA,
        },
        "prompt_packs": {"type": "object"},
        "suite_defaults": {"type": "object"},
        "retry": {"type": "object"},
        "checkpoint": {"type": "object"},
        "concurrency": {"type": "object"},
        "early_stop": {"type": "object"},
        "early_stop_plugins": {"type": "array", "items": _PLUGIN_DEF_SCHEMA},
        "validation_plugins": {"type": "array", "items": _PLUGIN_DEF_SCHEMA},
    },
    "required": ["datasource", "llm"],
    "additionalProperties": True,
}

_EXPERIMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "temperature": {"type": "number"},
        "max_tokens": {"type": "integer", "minimum": 1},
        "enabled": {"type": "boolean"},
        "is_baseline": {"type": "boolean"},
        "prompt_pack": {"type": "string"},
        "criteria": {"type": "array"},
        "row_plugins": {"type": "array", "items": _PLUGIN_DEF_SCHEMA},
        "aggregator_plugins": {"type": "array", "items": _PLUGIN_DEF_SCHEMA},
        "baseline_plugins": {"type": "array", "items": _PLUGIN_DEF_SCHEMA},
        "validation_plugins": {"type": "array", "items": _PLUGIN_DEF_SCHEMA},
        "llm_middlewares": {"type": "array", "items": _MIDDLEWARE_DEF_SCHEMA},
        "sinks": {"type": "array", "items": _PLUGIN_REFERENCE_SCHEMA},
        "rate_limiter": {"type": "object"},
        "cost_tracker": {"type": "object"},
        "prompt_defaults": {"type": "object"},
        "concurrency": {"type": "object"},
        "early_stop_plugins": {"type": "array", "items": _PLUGIN_DEF_SCHEMA},
    },
    "required": ["temperature", "max_tokens"],
    "additionalProperties": True,
}


@dataclass
class SuiteValidationReport:
    """Convenience wrapper bundling validation results with preflight data."""

    report: ValidationReport
    preflight: Dict[str, Any] = field(default_factory=dict)

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
