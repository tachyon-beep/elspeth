"""Settings profile validation entrypoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

import elspeth.core.registries.middleware as llm_middleware_registry
from elspeth.core.controls import registry as controls_registry
from elspeth.core.experiments import plugin_registry as exp_registry
from elspeth.core.registry import central_registry
from elspeth.core.validation.base import ConfigurationError, ValidationReport, validate_schema

from .rules import (
    _validate_experiment_plugins,
    _validate_middleware_list,
    _validate_plugin_list,
    _validate_plugin_reference,
)
from .schemas import SETTINGS_SCHEMA


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

    for message in validate_schema(profile_data, SETTINGS_SCHEMA, context=f"settings[{profile}]"):
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


def _validate_primary_plugins(
    report: ValidationReport,
    profile_data: Mapping[str, Any],
) -> None:
    """Validate datasource and llm entries for a settings profile."""

    datasource_registry = central_registry.get_registry("datasource")
    llm_registry = central_registry.get_registry("llm")

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
        validator=llm_registry.validate,
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

    sink_registry = central_registry.get_registry("sink")
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


def _validate_prompt_pack(
    report: ValidationReport,
    name: str,
    pack: Any,
) -> None:
    """Validate a prompt pack configuration entry."""

    sink_registry = central_registry.get_registry("sink")
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

    sink_registry = central_registry.get_registry("sink")
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


__all__ = ["validate_settings"]
