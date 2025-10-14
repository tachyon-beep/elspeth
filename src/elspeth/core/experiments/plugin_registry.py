"""Experiment plugin registry for row and aggregation plugins.

NOTE: This registry has been migrated to use BasePluginRegistry framework (Phase 2).
The actual plugin registrations are in individual registry files:
- row_plugin_registry.py
- aggregation_plugin_registry.py
- validation_plugin_registry.py
- baseline_plugin_registry.py
- early_stop_plugin_registry.py

This module now provides facade functions that delegate to the new registries while
preserving the existing API and special handling for experiment plugin patterns.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib import import_module
from typing import Any, Callable, Sequence

from elspeth.core.experiments.aggregation_plugin_registry import aggregation_plugin_registry
from elspeth.core.experiments.baseline_plugin_registry import baseline_plugin_registry
from elspeth.core.experiments.early_stop_plugin_registry import early_stop_plugin_registry
from elspeth.plugins.orchestrators.experiment.protocols import (
    AggregationExperimentPlugin,
    BaselineComparisonPlugin,
    EarlyStopPlugin,
    RowExperimentPlugin,
    ValidationPlugin,
)
from elspeth.core.experiments.row_plugin_registry import row_plugin_registry
from elspeth.core.experiments.validation_plugin_registry import validation_plugin_registry
from elspeth.core.plugins import PluginContext
from elspeth.core.security import coalesce_security_level  # Still needed for validation functions
from elspeth.core.validation_base import ConfigurationError

# Register functions now delegate to the new registries


def register_row_plugin(
    name: str,
    factory: Callable[[dict[str, Any], PluginContext], RowExperimentPlugin],
    *,
    schema: dict[str, Any] | None = None,
) -> None:
    """Register a row-level experiment plugin.

    NOTE: This function now delegates to the migrated row_plugin_registry.
    """
    row_plugin_registry.register(name, factory, schema=schema)


def register_aggregation_plugin(
    name: str,
    factory: Callable[[dict[str, Any], PluginContext], AggregationExperimentPlugin],
    *,
    schema: dict[str, Any] | None = None,
) -> None:
    """Register an aggregation experiment plugin.

    NOTE: This function now delegates to the migrated aggregation_plugin_registry.
    """
    aggregation_plugin_registry.register(name, factory, schema=schema)


def register_baseline_plugin(
    name: str,
    factory: Callable[[dict[str, Any], PluginContext], BaselineComparisonPlugin],
    *,
    schema: dict[str, Any] | None = None,
) -> None:
    """Register a baseline comparison plugin.

    NOTE: This function now delegates to the migrated baseline_plugin_registry.
    """
    baseline_plugin_registry.register(name, factory, schema=schema)


def register_validation_plugin(
    name: str,
    factory: Callable[[dict[str, Any], PluginContext], ValidationPlugin],
    *,
    schema: dict[str, Any] | None = None,
) -> None:
    """Register a suite validation plugin.

    NOTE: This function now delegates to the migrated validation_plugin_registry.
    """
    validation_plugin_registry.register(name, factory, schema=schema)


def register_early_stop_plugin(
    name: str,
    factory: Callable[[dict[str, Any], PluginContext], EarlyStopPlugin],
    *,
    schema: dict[str, Any] | None = None,
) -> None:
    """Register an early-stop plugin.

    NOTE: This function now delegates to the migrated early_stop_plugin_registry.
    """
    early_stop_plugin_registry.register(name, factory, schema=schema)


# Create functions delegate to registries with manual context creation (experiment plugin pattern)


def create_row_plugin(
    definition: dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
) -> RowExperimentPlugin:
    """Instantiate a registered row plugin from its definition.

    NOTE: This function now uses create_plugin_with_inheritance() helper
    to eliminate duplication.
    """
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    try:
        result = create_plugin_with_inheritance(
            row_plugin_registry,
            definition,
            plugin_kind="row_plugin",
            parent_context=parent_context,
            provenance=None,
            allow_none=False,
        )
        # When allow_none=False, create_plugin_with_inheritance never returns None
        # (it raises ValueError instead), but mypy doesn't track this
        assert result is not None, "Unreachable: allow_none=False prevents None return"
        return result
    except ValueError as exc:
        # Re-raise with backward-compatible error message for tests
        if "Unknown row_plugin" in str(exc):
            name = definition.get("name") if definition else None
            raise ValueError(f"Unknown row experiment plugin '{name}'") from exc
        raise


def create_aggregation_plugin(
    definition: dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
) -> AggregationExperimentPlugin:
    """Instantiate a registered aggregation plugin from its definition.

    NOTE: This function now uses create_plugin_with_inheritance() helper
    to eliminate duplication.
    """
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    result = create_plugin_with_inheritance(
        aggregation_plugin_registry,
        definition,
        plugin_kind="aggregation_plugin",
        parent_context=parent_context,
        provenance=None,
        allow_none=False,
    )
    # When allow_none=False, create_plugin_with_inheritance never returns None
    assert result is not None, "Unreachable: allow_none=False prevents None return"
    return result


def create_baseline_plugin(
    definition: dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
) -> BaselineComparisonPlugin:
    """Instantiate a registered baseline plugin from its definition.

    NOTE: This function now uses create_plugin_with_inheritance() helper
    to eliminate duplication.
    """
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    result = create_plugin_with_inheritance(
        baseline_plugin_registry,
        definition,
        plugin_kind="baseline_plugin",
        parent_context=parent_context,
        provenance=None,
        allow_none=False,
    )
    # When allow_none=False, create_plugin_with_inheritance never returns None
    assert result is not None, "Unreachable: allow_none=False prevents None return"
    return result


def create_validation_plugin(
    definition: dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
) -> ValidationPlugin:
    """Instantiate a validation plugin from its definition.

    NOTE: This function now uses create_plugin_with_inheritance() helper
    to eliminate duplication.
    """
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    result = create_plugin_with_inheritance(
        validation_plugin_registry,
        definition,
        plugin_kind="validation_plugin",
        parent_context=parent_context,
        provenance=None,
        allow_none=False,
    )
    # When allow_none=False, create_plugin_with_inheritance never returns None
    assert result is not None, "Unreachable: allow_none=False prevents None return"
    return result


def create_early_stop_plugin(
    definition: dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
) -> EarlyStopPlugin:
    """Instantiate an early-stop plugin from its definition.

    NOTE: This function now uses create_plugin_with_inheritance() helper
    to eliminate duplication.
    """
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    result = create_plugin_with_inheritance(
        early_stop_plugin_registry,
        definition,
        plugin_kind="early_stop_plugin",
        parent_context=parent_context,
        provenance=None,
        allow_none=False,
    )
    # When allow_none=False, create_plugin_with_inheritance never returns None
    assert result is not None, "Unreachable: allow_none=False prevents None return"
    return result


# Validate functions delegate to registries


def validate_row_plugin_definition(definition: dict[str, Any]) -> None:
    """Validate a row plugin definition without instantiating it.

    NOTE: This function now delegates to the migrated row_plugin_registry.
    """
    if not definition:
        raise ConfigurationError("Row plugin definition cannot be empty")

    name = definition.get("name")
    if not name or not isinstance(name, str):
        raise ConfigurationError("Row plugin definition missing 'name' field or name is not a string")

    options = definition.get("options", {})

    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Row plugin options must be a mapping")

    # Validate security level coalescing
    try:
        level = coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"row_plugin:{name}: {exc}") from exc

    prepared = dict(options)
    prepared.pop("security_level", None)
    prepared["security_level"] = level

    try:
        row_plugin_registry.validate(name, prepared)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc


def validate_aggregation_plugin_definition(definition: dict[str, Any]) -> None:
    """Validate an aggregation plugin definition without instantiating it.

    NOTE: This function now delegates to the migrated aggregation_plugin_registry.
    """
    if not definition:
        raise ConfigurationError("Aggregation plugin definition cannot be empty")

    name = definition.get("name")
    if not name or not isinstance(name, str):
        raise ConfigurationError("Aggregation plugin definition missing 'name' field or name is not a string")

    options = definition.get("options", {})

    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Aggregation plugin options must be a mapping")

    try:
        level = coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"aggregation_plugin:{name}: {exc}") from exc

    prepared = dict(options)
    prepared.pop("security_level", None)
    prepared["security_level"] = level

    try:
        aggregation_plugin_registry.validate(name, prepared)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc


def validate_baseline_plugin_definition(definition: dict[str, Any]) -> None:
    """Validate a baseline plugin definition.

    NOTE: This function now delegates to the migrated baseline_plugin_registry.
    """
    if not definition:
        raise ConfigurationError("Baseline plugin definition cannot be empty")

    name = definition.get("name")
    if not name or not isinstance(name, str):
        raise ConfigurationError("Baseline plugin definition missing 'name' field or name is not a string")

    options = definition.get("options", {})

    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Baseline plugin options must be a mapping")

    try:
        level = coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"baseline_plugin:{name}: {exc}") from exc

    prepared = dict(options)
    prepared.pop("security_level", None)
    prepared["security_level"] = level

    try:
        baseline_plugin_registry.validate(name, prepared)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc


def validate_validation_plugin_definition(definition: dict[str, Any]) -> None:
    """Validate a validation plugin definition.

    NOTE: This function now delegates to the migrated validation_plugin_registry.
    """
    if not definition:
        raise ConfigurationError("Validation plugin definition cannot be empty")

    name = definition.get("name")
    if not name or not isinstance(name, str):
        raise ConfigurationError("Validation plugin definition missing 'name' field or name is not a string")

    options = definition.get("options", {})

    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Validation plugin options must be a mapping")

    try:
        level = coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"validation_plugin:{name}: {exc}") from exc

    prepared = dict(options)
    prepared.pop("security_level", None)
    prepared["security_level"] = level

    try:
        validation_plugin_registry.validate(name, prepared)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc


def validate_early_stop_plugin_definition(definition: dict[str, Any]) -> None:
    """Validate an early-stop plugin definition.

    NOTE: This function now delegates to the migrated early_stop_plugin_registry.
    """
    if not definition:
        raise ConfigurationError("Early-stop plugin definition cannot be empty")

    name = definition.get("name")
    if not name or not isinstance(name, str):
        raise ConfigurationError("Early-stop plugin definition missing 'name' field or name is not a string")

    options = definition.get("options", {})

    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Early-stop plugin options must be a mapping")

    try:
        level = coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"early_stop_plugin:{name}: {exc}") from exc

    prepared = dict(options)
    prepared.pop("security_level", None)
    prepared["security_level"] = level

    try:
        early_stop_plugin_registry.validate(name, prepared)
    except ValueError as exc:
        raise ConfigurationError(str(exc)) from exc


# Early stop normalization logic (preserved from original)


def normalize_early_stop_definitions(definitions: Any) -> list[dict[str, Any]]:
    """Normalise raw early-stop definitions into plugin factory definitions."""
    normalized: list[dict[str, Any]] = []
    if not definitions:
        return normalized
    for entry in _iter_early_stop_entries(definitions):
        normalized.append(_normalize_early_stop_entry(entry))
    return normalized


def _iter_early_stop_entries(definitions: Any) -> Sequence[Any]:
    """Return iterable entries for early-stop configuration."""
    if isinstance(definitions, Mapping):
        return [definitions]
    if isinstance(definitions, Sequence) and not isinstance(definitions, (str, bytes)):
        return list(definitions)
    raise ConfigurationError("Early-stop configuration must be an object or list of objects")


def _normalize_early_stop_entry(entry: Any) -> dict[str, Any]:
    """Normalise a single early-stop entry."""
    if not isinstance(entry, Mapping):
        raise ConfigurationError("Each early-stop entry must be an object")

    plugin_name = entry.get("name") or entry.get("plugin")
    if plugin_name:
        options = entry.get("options") or {}
        if not isinstance(options, Mapping):
            raise ConfigurationError(f"Early-stop plugin '{plugin_name}' options must be an object, got {type(options).__name__}")
        base_options = dict(options)
        extra_keys = {k: v for k, v in entry.items() if k not in {"name", "plugin", "options"}}
        if extra_keys:
            base_options.update(extra_keys)
        return {"name": str(plugin_name), "options": base_options}

    return {"name": "threshold", "options": dict(entry)}


# Load default plugins via side-effects


def _load_default_plugins() -> None:
    """Load default plugin implementations via import side-effects."""
    try:  # pragma: no cover - best-effort import only
        import_module("elspeth.plugins.experiments")
    except ImportError:
        pass


_load_default_plugins()


__all__ = [
    "register_row_plugin",
    "register_aggregation_plugin",
    "register_baseline_plugin",
    "register_validation_plugin",
    "register_early_stop_plugin",
    "create_row_plugin",
    "create_aggregation_plugin",
    "create_baseline_plugin",
    "create_validation_plugin",
    "create_early_stop_plugin",
    "validate_row_plugin_definition",
    "validate_aggregation_plugin_definition",
    "validate_baseline_plugin_definition",
    "validate_validation_plugin_definition",
    "validate_early_stop_plugin_definition",
    "normalize_early_stop_definitions",
]
