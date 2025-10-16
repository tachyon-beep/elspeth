"""Validation utilities and error reporting helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import yaml

import elspeth.core.registries.middleware as llm_middleware_registry
from elspeth.core.controls import registry as controls_registry
from elspeth.core.experiments import plugin_registry as exp_registry
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.registries.llm import llm_registry as llm_reg
from elspeth.core.registries.sink import sink_registry
from elspeth.core.security import normalize_security_level
from elspeth.core.validation.base import (
    ConfigurationError,
    ValidationMessage,
    ValidationReport,
    validate_schema,
)


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

    _validate_primary_plugins(report, profile_data)

    sinks = profile_data.get("sinks")
    top_level_sinks_valid = _validate_top_level_sinks(report, sinks, profile)
    if not top_level_sinks_valid:
        prompt_packs_raw = profile_data.get("prompt_packs")
        suite_defaults_raw = profile_data.get("suite_defaults")
        if not _has_fallback_sinks(profile_data, prompt_packs_raw, suite_defaults_raw):
            report.add_error(
                "'sinks' must be provided either at the profile level, via prompt pack, or suite defaults",
                context=f"settings[{profile}]",
            )

    prompt_packs = _validate_prompt_pack_section(
        report,
        profile_data,
        profile,
    )

    _validate_middleware_list(
        report,
        profile_data.get("llm_middlewares"),
        llm_middleware_registry.validate_middleware_definition,
        context=f"settings[{profile}].middleware",
    )

    _validate_suite_defaults_section(
        report,
        profile_data.get("suite_defaults"),
        prompt_packs,
        profile,
    )

    _validate_additional_mappings(report, profile_data, profile)

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


def _validate_security_level_fields(
    report: ValidationReport,
    *,
    context: str,
    entry_level: Any,
    options_level: Any,
) -> str | None:
    """Ensure plugin definitions declare a consistent security level."""

    normalized_entry: str | None = None
    normalized_options: str | None = None

    entry_text = str(entry_level).strip() if entry_level is not None else ""
    options_text = str(options_level).strip() if options_level is not None else ""

    if entry_level is not None:
        if not entry_text:
            report.add_error("security_level must be non-empty", context=context)
        else:
            try:
                normalized_entry = normalize_security_level(entry_text)
            except ValueError as exc:
                report.add_error(str(exc), context=context)

    if options_level is not None:
        if not options_text:
            report.add_error("options.security_level must be non-empty", context=context)
        else:
            try:
                normalized_options = normalize_security_level(options_text)
            except ValueError as exc:
                report.add_error(str(exc), context=context)

    if normalized_entry and normalized_options and normalized_entry != normalized_options:
        report.add_error("Conflicting security_level values between definition and options", context=context)

    if not normalized_entry and not normalized_options:
        report.add_error("Plugin must declare a security_level", context=context)

    return normalized_entry or normalized_options


def _validate_plugin_reference(
    report: ValidationReport,
    entry: Any,
    *,
    kind: str,
    validator: Callable[[str, dict[str, Any] | None], None],
    require_security_level: bool = False,
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
    options_dict: dict[str, Any] | None
    options_level_raw = None
    options_determinism_raw = None
    if options is None:
        options_dict = None
    elif isinstance(options, Mapping):
        options_dict = dict(options)
        options_level_raw = options_dict.get("security_level")
        options_determinism_raw = options_dict.get("determinism_level")
    else:
        report.add_error("Options must be a mapping", context=f"{kind}:{plugin}")
        options_dict = {}

    context_label = f"{kind}:{plugin}" if plugin else kind

    if require_security_level:
        _validate_security_level_fields(
            report,
            context=context_label,
            entry_level=entry.get("security_level"),
            options_level=options_level_raw,
        )

    validation_options = dict(options_dict or {})
    if entry.get("security_level") is not None:
        validation_options.setdefault("security_level", entry.get("security_level"))
    elif options_level_raw is not None:
        validation_options.setdefault("security_level", options_level_raw)

    if entry.get("determinism_level") is not None:
        validation_options.setdefault("determinism_level", entry.get("determinism_level"))
    elif options_determinism_raw is not None:
        validation_options.setdefault("determinism_level", options_determinism_raw)

    try:
        validator(plugin, validation_options)
    except (ValueError, ConfigurationError) as exc:
        report.add_error(str(exc), context=f"{kind}:{plugin}")


def _validate_plugin_list(
    report: ValidationReport,
    entries: Any,
    validator: Callable[[str, dict[str, Any] | None], None],
    *,
    context: str,
    require_security_level: bool = False,
) -> None:
    """Validate a list of plugin references using ``validator``."""
    if entries is None:
        return
    if not isinstance(entries, list):
        report.add_error("Expected a list of plugin definitions", context=context)
        return
    for entry in entries:
        _validate_plugin_reference(
            report,
            entry,
            kind=context,
            validator=validator,
            require_security_level=require_security_level,
        )


def _validate_prompt_pack(
    report: ValidationReport,
    name: str,
    pack: Any,
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
        llm_middleware_registry.validate_middleware_definition,
        context=f"{context}.middleware",
    )
    _validate_plugin_list(
        report,
        pack.get("sinks"),
        sink_registry.validate,
        context=f"{context}.sink",
        require_security_level=True,
    )


def _validate_suite_defaults(
    report: ValidationReport,
    defaults: Mapping[str, Any],
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
        llm_middleware_registry.validate_middleware_definition,
        context="suite_defaults.middleware",
    )
    _validate_plugin_list(
        report,
        defaults.get("sinks"),
        sink_registry.validate,
        context="suite_defaults.sink",
        require_security_level=True,
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
    validator: Callable[[dict[str, Any]], None],
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
        options_obj = definition.get("options") if isinstance(definition.get("options"), Mapping) else None
        options_level = options_obj.get("security_level") if options_obj else None
        _validate_security_level_fields(
            report,
            context=context,
            entry_level=definition.get("security_level"),
            options_level=options_level,
        )
        try:
            prepared = dict(definition)
            if options_obj is not None:
                prepared_options = dict(options_obj)
                prepared_options.pop("security_level", None)
                prepared["options"] = prepared_options
            validator(prepared)
        except ConfigurationError as exc:
            report.add_error(str(exc), context=context)
        except ValueError as exc:
            report.add_error(str(exc), context=context)


def _validate_middleware_list(
    report: ValidationReport,
    entries: Any,
    validator: Callable[[dict[str, Any]], None],
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
        options_obj = definition.get("options") if isinstance(definition.get("options"), Mapping) else None
        options_level = options_obj.get("security_level") if options_obj else None
        _validate_security_level_fields(
            report,
            context=context,
            entry_level=definition.get("security_level"),
            options_level=options_level,
        )
        try:
            prepared = dict(definition)
            if options_obj is not None:
                prepared_options = dict(options_obj)
                prepared_options.pop("security_level", None)
                prepared["options"] = prepared_options
            validator(prepared)
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
            baseline_count += 1
            baseline_name = summary.name

    return summaries, all_names, baseline_name, baseline_count


def _calculate_preflight(
    summaries: Sequence[_ExperimentSummary],
    baseline_name: str | None,
    row_estimate: int,
    report: ValidationReport,
) -> dict[str, Any]:
    """Compute preflight metadata and register warnings on the report."""

    warnings: list[str] = []
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


def _validate_primary_plugins(
    report: ValidationReport,
    profile_data: Mapping[str, Any],
) -> None:
    """Validate datasource and llm entries for a settings profile."""

    _validate_plugin_reference(
        report,
        profile_data.get("datasource"),
        kind="datasource",
        validator=datasource_registry.validate,
        require_security_level=True,
    )
    _validate_plugin_reference(
        report,
        profile_data.get("llm"),
        kind="llm",
        validator=llm_reg.validate,
        require_security_level=True,
    )


def _validate_top_level_sinks(
    report: ValidationReport,
    sinks: Any,
    profile: str,
) -> bool:
    """Validate sinks defined directly on the profile."""

    if sinks is None:
        return False
    if not isinstance(sinks, list):
        report.add_error("'sinks' must be a list when provided", context=f"settings[{profile}]")
        return False
    if not sinks:
        return False

    for entry in sinks:
        _validate_plugin_reference(
            report,
            entry,
            kind="sink",
            validator=sink_registry.validate,
            require_security_level=True,
        )
    return True


def _has_fallback_sinks(
    profile_data: Mapping[str, Any],
    prompt_packs: Any,
    suite_defaults: Any,
) -> bool:
    """Return True when sinks are provided via prompt packs or suite defaults."""

    return _prompt_pack_provides_sinks(profile_data, prompt_packs) or _suite_defaults_provide_sinks(suite_defaults, prompt_packs)


def _validate_prompt_pack_section(
    report: ValidationReport,
    profile_data: Mapping[str, Any],
    profile: str,
) -> dict[str, Any]:
    """Validate prompt pack mappings and return a normalized dict."""

    prompt_packs_raw = profile_data.get("prompt_packs")
    if prompt_packs_raw is None:
        prompt_packs: dict[str, Any] = {}
    elif isinstance(prompt_packs_raw, Mapping):
        prompt_packs = dict(prompt_packs_raw)
    else:
        report.add_error("'prompt_packs' must be a mapping", context=f"settings[{profile}]")
        prompt_packs = {}

    for name, pack in prompt_packs.items():
        _validate_prompt_pack(report, name, pack)

    prompt_pack_name = profile_data.get("prompt_pack")
    if isinstance(prompt_pack_name, str) and prompt_pack_name and prompt_pack_name not in prompt_packs:
        available = ", ".join(sorted(prompt_packs)) or "<none>"
        report.add_error(
            f"Unknown prompt pack '{prompt_pack_name}'. Available prompt packs: {available}",
            context=f"settings[{profile}].prompt_pack",
        )

    return prompt_packs


def _validate_suite_defaults_section(
    report: ValidationReport,
    suite_defaults_raw: Any,
    prompt_packs: Mapping[str, Any],
    profile: str,
) -> Mapping[str, Any]:
    """Validate suite defaults ensuring they are mappings and sinks are resolvable."""

    if suite_defaults_raw is None:
        suite_defaults: Mapping[str, Any] = {}
    elif isinstance(suite_defaults_raw, Mapping):
        suite_defaults = suite_defaults_raw
    else:
        report.add_error("'suite_defaults' must be a mapping", context=f"settings[{profile}]")
        suite_defaults = {}

    _validate_suite_defaults(report, suite_defaults)

    suite_pack_name = suite_defaults.get("prompt_pack")
    if isinstance(suite_pack_name, str) and suite_pack_name and suite_pack_name not in prompt_packs:
        report.add_error(
            f"Suite defaults reference unknown prompt pack '{suite_pack_name}'",
            context=f"settings[{profile}].suite_defaults",
        )

    return suite_defaults


def _validate_additional_mappings(report: ValidationReport, profile_data: Mapping[str, Any], profile: str) -> None:
    """Validate ancillary mapping-based configuration sections."""

    for key in ("retry", "checkpoint", "concurrency"):
        value = profile_data.get(key)
        if value is not None and not isinstance(value, Mapping):
            report.add_error(f"'{key}' must be a mapping", context=f"settings[{profile}]")


def _prompt_pack_provides_sinks(profile_data: Mapping[str, Any], prompt_packs: Any) -> bool:
    """Inspect prompt pack configuration to see if sinks are defined."""

    prompt_pack_name = profile_data.get("prompt_pack")
    if not isinstance(prompt_packs, Mapping) or not isinstance(prompt_pack_name, str):
        return False

    pack_definition = prompt_packs.get(prompt_pack_name)
    if not isinstance(pack_definition, Mapping):
        return False

    pack_sinks = pack_definition.get("sinks")
    return isinstance(pack_sinks, list) and bool(pack_sinks)


def _suite_defaults_provide_sinks(suite_defaults: Any, prompt_packs: Any) -> bool:
    """Return True when suite defaults specify sinks directly or via prompt pack."""

    if not isinstance(suite_defaults, Mapping):
        return False

    defaults_sinks = suite_defaults.get("sinks")
    if isinstance(defaults_sinks, list) and defaults_sinks:
        return True

    suite_defaults_pack = suite_defaults.get("prompt_pack")
    if not isinstance(prompt_packs, Mapping) or not isinstance(suite_defaults_pack, str):
        return False

    pack_definition = prompt_packs.get(suite_defaults_pack)
    if not isinstance(pack_definition, Mapping):
        return False

    pack_sinks = pack_definition.get("sinks")
    return isinstance(pack_sinks, list) and bool(pack_sinks)


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
