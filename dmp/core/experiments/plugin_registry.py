"""Experiment plugin registry for row and aggregation plugins."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from dmp.core.experiments.plugins import (
    RowExperimentPlugin,
    AggregationExperimentPlugin,
    BaselineComparisonPlugin,
    EarlyStopPlugin,
)
from dmp.core.validation import ConfigurationError, validate_schema


class _PluginFactory:
    def __init__(self, factory: Callable[[Dict[str, Any]], Any], schema: Mapping[str, Any] | None = None):
        self.factory = factory
        self.schema = schema

    def validate(self, options: Dict[str, Any], *, context: str) -> None:
        if self.schema is None:
            return
        errors = list(validate_schema(options or {}, self.schema, context=context))
        if errors:
            raise ConfigurationError("\n".join(msg.format() for msg in errors))

    def create(self, options: Dict[str, Any], *, context: str) -> Any:
        self.validate(options, context=context)
        return self.factory(options)


_row_plugins: Dict[str, _PluginFactory] = {}
_aggregation_plugins: Dict[str, _PluginFactory] = {}
_baseline_plugins: Dict[str, _PluginFactory] = {}
_early_stop_plugins: Dict[str, _PluginFactory] = {}


def register_row_plugin(
    name: str,
    factory: Callable[[Dict[str, Any]], RowExperimentPlugin],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    _row_plugins[name] = _PluginFactory(factory, schema=schema)


def register_aggregation_plugin(
    name: str,
    factory: Callable[[Dict[str, Any]], AggregationExperimentPlugin],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    _aggregation_plugins[name] = _PluginFactory(factory, schema=schema)


def register_baseline_plugin(
    name: str,
    factory: Callable[[Dict[str, Any]], BaselineComparisonPlugin],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    _baseline_plugins[name] = _PluginFactory(factory, schema=schema)


def register_early_stop_plugin(
    name: str,
    factory: Callable[[Dict[str, Any]], EarlyStopPlugin],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    _early_stop_plugins[name] = _PluginFactory(factory, schema=schema)


def create_row_plugin(definition: Dict[str, Any]) -> RowExperimentPlugin:
    if not definition:
        raise ValueError("Row plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _row_plugins:
        raise ValueError(f"Unknown row experiment plugin '{name}'")
    return _row_plugins[name].create(options, context=f"row_plugin:{name}")


def create_aggregation_plugin(definition: Dict[str, Any]) -> AggregationExperimentPlugin:
    if not definition:
        raise ValueError("Aggregation plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _aggregation_plugins:
        raise ValueError(f"Unknown aggregation experiment plugin '{name}'")
    return _aggregation_plugins[name].create(options, context=f"aggregation_plugin:{name}")


def create_baseline_plugin(definition: Dict[str, Any]) -> BaselineComparisonPlugin:
    if not definition:
        raise ValueError("Baseline plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _baseline_plugins:
        raise ValueError(f"Unknown baseline comparison plugin '{name}'")
    return _baseline_plugins[name].create(options, context=f"baseline_plugin:{name}")


def create_early_stop_plugin(definition: Dict[str, Any]) -> EarlyStopPlugin:
    if not definition:
        raise ValueError("Early-stop plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _early_stop_plugins:
        raise ValueError(f"Unknown early-stop plugin '{name}'")
    return _early_stop_plugins[name].create(options, context=f"early_stop_plugin:{name}")


class _NoopRowPlugin:
    name = "noop"

    def process_row(self, row, responses):  # pragma: no cover - trivial
        return {}


class _NoopAggPlugin:
    name = "noop"

    def finalize(self, records):  # pragma: no cover - trivial
        return {}


class _NoopBaselinePlugin:
    name = "noop"

    def compare(self, baseline, variant):  # pragma: no cover - trivial
        return {}


class _RowCountBaselinePlugin:
    def __init__(self, key: str = "row_delta"):
        self.name = "row_count"
        self._key = key

    def compare(self, baseline, variant):
        base_count = len(baseline.get("results", [])) if baseline else 0
        variant_count = len(variant.get("results", [])) if variant else 0
        return {self._key: variant_count - base_count}


# Register defaults
register_row_plugin("noop", lambda options: _NoopRowPlugin())
register_aggregation_plugin("noop", lambda options: _NoopAggPlugin())
register_baseline_plugin("noop", lambda options: _NoopBaselinePlugin())
register_baseline_plugin(
    "row_count",
    lambda options: _RowCountBaselinePlugin(options.get("key", "row_delta")),
    schema={
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "additionalProperties": True,
    },
)


__all__ = [
    "register_row_plugin",
    "register_aggregation_plugin",
    "register_baseline_plugin",
    "create_row_plugin",
    "create_aggregation_plugin",
    "create_baseline_plugin",
    "register_early_stop_plugin",
    "create_early_stop_plugin",
    "validate_row_plugin_definition",
    "validate_aggregation_plugin_definition",
    "validate_baseline_plugin_definition",
    "validate_early_stop_plugin_definition",
    "normalize_early_stop_definitions",
]


def validate_row_plugin_definition(definition: Dict[str, Any]) -> None:
    if not definition:
        raise ConfigurationError("Row plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _row_plugins:
        raise ConfigurationError(f"Unknown row experiment plugin '{name}'")
    _row_plugins[name].validate(options, context=f"row_plugin:{name}")


def validate_aggregation_plugin_definition(definition: Dict[str, Any]) -> None:
    if not definition:
        raise ConfigurationError("Aggregation plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _aggregation_plugins:
        raise ConfigurationError(f"Unknown aggregation experiment plugin '{name}'")
    _aggregation_plugins[name].validate(options, context=f"aggregation_plugin:{name}")


def validate_baseline_plugin_definition(definition: Dict[str, Any]) -> None:
    if not definition:
        raise ConfigurationError("Baseline plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _baseline_plugins:
        raise ConfigurationError(f"Unknown baseline comparison plugin '{name}'")
    _baseline_plugins[name].validate(options, context=f"baseline_plugin:{name}")


def validate_early_stop_plugin_definition(definition: Dict[str, Any]) -> None:
    if not definition:
        raise ConfigurationError("Early-stop plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _early_stop_plugins:
        raise ConfigurationError(f"Unknown early-stop plugin '{name}'")
    _early_stop_plugins[name].validate(options, context=f"early_stop_plugin:{name}")


def normalize_early_stop_definitions(definitions: Any) -> List[Dict[str, Any]]:
    """Normalise raw early-stop definitions into plugin factory definitions."""

    normalized: List[Dict[str, Any]] = []
    if not definitions:
        return normalized

    if isinstance(definitions, Mapping):
        items: Sequence[Any] = [definitions]
    elif isinstance(definitions, Sequence) and not isinstance(definitions, (str, bytes)):
        items = list(definitions)
    else:
        raise ConfigurationError("Early-stop configuration must be an object or list of objects")

    for entry in items:
        if not isinstance(entry, Mapping):
            raise ConfigurationError("Each early-stop entry must be an object")
        plugin_name = entry.get("name") or entry.get("plugin")
        if plugin_name:
            options = entry.get("options")
            if options is None:
                options = {}
            if not isinstance(options, Mapping):
                raise ConfigurationError(
                    f"Early-stop plugin '{plugin_name}' options must be an object, got {type(options).__name__}"
                )
            base_options = dict(options)
            # Allow inline options alongside the name/plugin keys for convenience.
            extra_keys = {k: v for k, v in entry.items() if k not in {"name", "plugin", "options"}}
            if extra_keys:
                base_options.update(extra_keys)
            normalized.append({"name": str(plugin_name), "options": base_options})
            continue

        # Treat bare dictionaries as options for the default threshold plugin.
        normalized.append({"name": "threshold", "options": dict(entry)})

    return normalized


def _load_default_plugins() -> None:
    """Load default plugin implementations via import side-effects."""

    try:  # pragma: no cover - best-effort import only
        import dmp.plugins.experiments  # noqa: F401
    except ImportError:
        pass


_load_default_plugins()
