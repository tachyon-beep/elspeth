"""Shared validation helpers used across settings and suite validators."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from elspeth.core.security import ensure_security_level
from elspeth.core.validation.base import ConfigurationError, ValidationReport


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
                normalized_entry = ensure_security_level(entry_text).value
            except ValueError as exc:
                report.add_error(str(exc), context=context)

    if options_level is not None:
        if not options_text:
            report.add_error("options.security_level must be non-empty", context=context)
        else:
            try:
                normalized_options = ensure_security_level(options_text).value
            except ValueError as exc:
                report.add_error(str(exc), context=context)

    if normalized_entry and normalized_options and normalized_entry != normalized_options:
        report.add_error("Conflicting security_level values between definition and options", context=context)

    # ADR-002-B: security_level is OPTIONAL (defaults to UNOFFICIAL if not provided)
    # Removed check that required security_level to be declared

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
        except (ConfigurationError, ValueError) as exc:
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
        except (ConfigurationError, ValueError) as exc:
            report.add_error(str(exc), context=context)


__all__ = [
    "_validate_security_level_fields",
    "_validate_plugin_reference",
    "_validate_plugin_list",
    "_validate_experiment_plugins",
    "_validate_middleware_list",
]
