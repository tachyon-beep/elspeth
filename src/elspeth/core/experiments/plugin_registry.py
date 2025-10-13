"""Experiment plugin registry for row and aggregation plugins."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Dict, List, Mapping, Sequence

from elspeth.core.experiments.plugins import (
    AggregationExperimentPlugin,
    BaselineComparisonPlugin,
    EarlyStopPlugin,
    RowExperimentPlugin,
    ValidationPlugin,
)
from elspeth.core.plugins import PluginContext, apply_plugin_context
from elspeth.core.security import coalesce_security_level
from elspeth.core.validation import ConfigurationError, validate_schema


class _PluginFactory:
    """Wrap plugin factories with optional schema validation."""

    def __init__(
        self,
        factory: Callable[[Dict[str, Any], PluginContext], Any],
        schema: Mapping[str, Any] | None = None,
    ) -> None:
        self.factory = factory
        self.schema = schema

    def validate(self, options: Dict[str, Any], *, context: str) -> None:
        """Run schema validation for the provided options."""

        if self.schema is None:
            return
        errors = list(validate_schema(options or {}, self.schema, context=context))
        if errors:
            raise ConfigurationError("\n".join(msg.format() for msg in errors))

    def create(self, options: Dict[str, Any], *, plugin_context: PluginContext, schema_context: str) -> Any:
        """Validate options and instantiate the plugin."""

        self.validate(options, context=schema_context)
        return self.factory(options, plugin_context)


_row_plugins: Dict[str, _PluginFactory] = {}
_aggregation_plugins: Dict[str, _PluginFactory] = {}
_baseline_plugins: Dict[str, _PluginFactory] = {}
_validation_plugins: Dict[str, _PluginFactory] = {}
_early_stop_plugins: Dict[str, _PluginFactory] = {}


def register_row_plugin(
    name: str,
    factory: Callable[[Dict[str, Any], PluginContext], RowExperimentPlugin],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    """Register a row-level experiment plugin."""

    _row_plugins[name] = _PluginFactory(factory, schema=schema)


def register_aggregation_plugin(
    name: str,
    factory: Callable[[Dict[str, Any], PluginContext], AggregationExperimentPlugin],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    """Register an aggregation experiment plugin."""

    _aggregation_plugins[name] = _PluginFactory(factory, schema=schema)


def register_baseline_plugin(
    name: str,
    factory: Callable[[Dict[str, Any], PluginContext], BaselineComparisonPlugin],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    """Register a baseline comparison plugin."""

    _baseline_plugins[name] = _PluginFactory(factory, schema=schema)


def register_validation_plugin(
    name: str,
    factory: Callable[[Dict[str, Any], PluginContext], ValidationPlugin],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    """Register a suite validation plugin."""

    _validation_plugins[name] = _PluginFactory(factory, schema=schema)


def register_early_stop_plugin(
    name: str,
    factory: Callable[[Dict[str, Any], PluginContext], EarlyStopPlugin],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    """Register an early-stop plugin."""

    _early_stop_plugins[name] = _PluginFactory(factory, schema=schema)


def create_row_plugin(
    definition: Dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
) -> RowExperimentPlugin:
    """Instantiate a registered row plugin from its definition."""

    if not definition:
        raise ValueError("Row plugin definition cannot be empty")
    name = definition.get("name")
    options = dict(definition.get("options", {}) or {})
    if name not in _row_plugins:
        raise ValueError(f"Unknown row experiment plugin '{name}'")
    definition_level = definition.get("security_level")
    option_level = options.get("security_level")
    sources: list[str] = []
    if definition_level is not None:
        sources.append(f"row_plugin:{name}.definition.security_level")
    if option_level is not None:
        sources.append(f"row_plugin:{name}.options.security_level")
    try:
        level = coalesce_security_level(definition_level, option_level)
    except ValueError as exc:
        raise ConfigurationError(f"row_plugin:{name}: {exc}") from exc
    payload = dict(options)
    payload.pop("security_level", None)
    provenance = tuple(sources or (f"row_plugin:{name}.resolved",))
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind="row_plugin",
            security_level=level,
            provenance=provenance,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind="row_plugin",
            security_level=level,
            provenance=provenance,
        )
    plugin = _row_plugins[name].create(
        payload,
        plugin_context=context,
        schema_context=f"row_plugin:{name}",
    )
    apply_plugin_context(plugin, context)
    return plugin  # type: ignore[no-any-return]


def create_aggregation_plugin(
    definition: Dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
) -> AggregationExperimentPlugin:
    """Instantiate a registered aggregation plugin from its definition."""

    if not definition:
        raise ValueError("Aggregation plugin definition cannot be empty")
    name = definition.get("name")
    options = dict(definition.get("options", {}) or {})
    if name not in _aggregation_plugins:
        raise ValueError(f"Unknown aggregation experiment plugin '{name}'")
    definition_level = definition.get("security_level")
    option_level = options.get("security_level")
    sources: list[str] = []
    if definition_level is not None:
        sources.append(f"aggregation_plugin:{name}.definition.security_level")
    if option_level is not None:
        sources.append(f"aggregation_plugin:{name}.options.security_level")
    try:
        level = coalesce_security_level(definition_level, option_level)
    except ValueError as exc:
        raise ConfigurationError(f"aggregation_plugin:{name}: {exc}") from exc
    payload = dict(options)
    payload.pop("security_level", None)
    provenance = tuple(sources or (f"aggregation_plugin:{name}.resolved",))
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind="aggregation_plugin",
            security_level=level,
            provenance=provenance,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind="aggregation_plugin",
            security_level=level,
            provenance=provenance,
        )
    plugin = _aggregation_plugins[name].create(
        payload,
        plugin_context=context,
        schema_context=f"aggregation_plugin:{name}",
    )
    apply_plugin_context(plugin, context)
    return plugin  # type: ignore[no-any-return]


def create_baseline_plugin(
    definition: Dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
) -> BaselineComparisonPlugin:
    """Instantiate a registered baseline plugin from its definition."""

    if not definition:
        raise ValueError("Baseline plugin definition cannot be empty")
    name = definition.get("name")
    options = dict(definition.get("options", {}) or {})
    if name not in _baseline_plugins:
        raise ValueError(f"Unknown baseline comparison plugin '{name}'")
    definition_level = definition.get("security_level")
    option_level = options.get("security_level")
    sources: list[str] = []
    if definition_level is not None:
        sources.append(f"baseline_plugin:{name}.definition.security_level")
    if option_level is not None:
        sources.append(f"baseline_plugin:{name}.options.security_level")
    try:
        level = coalesce_security_level(definition_level, option_level)
    except ValueError as exc:
        raise ConfigurationError(f"baseline_plugin:{name}: {exc}") from exc
    payload = dict(options)
    payload.pop("security_level", None)
    provenance = tuple(sources or (f"baseline_plugin:{name}.resolved",))
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind="baseline_plugin",
            security_level=level,
            provenance=provenance,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind="baseline_plugin",
            security_level=level,
            provenance=provenance,
        )
    plugin = _baseline_plugins[name].create(
        payload,
        plugin_context=context,
        schema_context=f"baseline_plugin:{name}",
    )
    apply_plugin_context(plugin, context)
    return plugin  # type: ignore[no-any-return]


def create_validation_plugin(
    definition: Dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
) -> ValidationPlugin:
    """Instantiate a validation plugin from its definition."""

    if not definition:
        raise ValueError("Validation plugin definition cannot be empty")
    name = definition.get("name")
    options = dict(definition.get("options", {}) or {})
    if name not in _validation_plugins:
        raise ValueError(f"Unknown validation plugin '{name}'")
    definition_level = definition.get("security_level")
    option_level = options.get("security_level")
    sources: list[str] = []
    if definition_level is not None:
        sources.append(f"validation_plugin:{name}.definition.security_level")
    if option_level is not None:
        sources.append(f"validation_plugin:{name}.options.security_level")
    try:
        level = coalesce_security_level(definition_level, option_level)
    except ValueError as exc:
        raise ConfigurationError(f"validation_plugin:{name}: {exc}") from exc

    payload = dict(options)
    payload.pop("security_level", None)
    provenance = tuple(sources or (f"validation_plugin:{name}.resolved",))
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind="validation_plugin",
            security_level=level,
            provenance=provenance,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind="validation_plugin",
            security_level=level,
            provenance=provenance,
        )
    plugin = _validation_plugins[name].create(
        payload,
        plugin_context=context,
        schema_context=f"validation_plugin:{name}",
    )
    apply_plugin_context(plugin, context)
    return plugin  # type: ignore[no-any-return]


def create_early_stop_plugin(
    definition: Dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
) -> EarlyStopPlugin:
    """Instantiate an early-stop plugin from its definition."""

    if not definition:
        raise ValueError("Early-stop plugin definition cannot be empty")
    name = definition.get("name")
    options = dict(definition.get("options", {}) or {})
    if name not in _early_stop_plugins:
        raise ValueError(f"Unknown early-stop plugin '{name}'")
    definition_level = definition.get("security_level")
    option_level = options.get("security_level")
    sources: list[str] = []
    if definition_level is not None:
        sources.append(f"early_stop_plugin:{name}.definition.security_level")
    if option_level is not None:
        sources.append(f"early_stop_plugin:{name}.options.security_level")
    try:
        level = coalesce_security_level(definition_level, option_level)
    except ValueError as exc:
        raise ConfigurationError(f"early_stop_plugin:{name}: {exc}") from exc
    payload = dict(options)
    payload.pop("security_level", None)
    provenance = tuple(sources or (f"early_stop_plugin:{name}.resolved",))
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind="early_stop_plugin",
            security_level=level,
            provenance=provenance,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind="early_stop_plugin",
            security_level=level,
            provenance=provenance,
        )
    plugin = _early_stop_plugins[name].create(
        payload,
        plugin_context=context,
        schema_context=f"early_stop_plugin:{name}",
    )
    apply_plugin_context(plugin, context)
    return plugin  # type: ignore[no-any-return]


class _NoopRowPlugin:  # pylint: disable=too-few-public-methods
    name = "noop"

    def process_row(self, _row: Dict[str, Any], _responses: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover - trivial
        """Return an empty payload for noop processing."""

        return {}

    def input_schema(self):
        """Noop plugin does not require specific input columns."""
        return None


class _NoopAggPlugin:  # pylint: disable=too-few-public-methods
    name = "noop"

    def finalize(self, _records: List[Dict[str, Any]]) -> Dict[str, Any]:  # pragma: no cover - trivial
        """Return an empty aggregation result."""

        return {}

    def input_schema(self):
        """Noop plugin does not require specific input columns."""
        return None


class _NoopBaselinePlugin:  # pylint: disable=too-few-public-methods
    name = "noop"

    def compare(self, _baseline: Dict[str, Any], _variant: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover - trivial
        """Return an empty comparison result."""

        return {}


class _RowCountBaselinePlugin:  # pylint: disable=too-few-public-methods
    def __init__(self, key: str = "row_delta"):
        self.name = "row_count"
        self._key = key

    def compare(self, baseline: Dict[str, Any], variant: Dict[str, Any]) -> Dict[str, Any]:
        """Return the delta in result counts between baseline and variant."""

        base_count = len(baseline.get("results", [])) if baseline else 0
        variant_count = len(variant.get("results", [])) if variant else 0
        return {self._key: variant_count - base_count}


# Register defaults
register_row_plugin("noop", lambda options, context: _NoopRowPlugin())
register_aggregation_plugin("noop", lambda options, context: _NoopAggPlugin())
register_baseline_plugin("noop", lambda options, context: _NoopBaselinePlugin())
register_baseline_plugin(
    "row_count",
    lambda options, context: _RowCountBaselinePlugin(options.get("key", "row_delta")),
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
    "register_validation_plugin",
    "create_row_plugin",
    "create_aggregation_plugin",
    "create_baseline_plugin",
    "create_validation_plugin",
    "register_early_stop_plugin",
    "create_early_stop_plugin",
    "validate_row_plugin_definition",
    "validate_aggregation_plugin_definition",
    "validate_baseline_plugin_definition",
    "validate_validation_plugin_definition",
    "validate_early_stop_plugin_definition",
    "normalize_early_stop_definitions",
]


def validate_row_plugin_definition(definition: Dict[str, Any]) -> None:
    """Validate a row plugin definition without instantiating it."""

    if not definition:
        raise ConfigurationError("Row plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _row_plugins:
        raise ConfigurationError(f"Unknown row experiment plugin '{name}'")
    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Row plugin options must be a mapping")
    try:
        coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"row_plugin:{name}: {exc}") from exc
    prepared = dict(options)
    prepared.pop("security_level", None)
    _row_plugins[name].validate(prepared, context=f"row_plugin:{name}")


def validate_aggregation_plugin_definition(definition: Dict[str, Any]) -> None:
    """Validate an aggregation plugin definition without instantiating it."""

    if not definition:
        raise ConfigurationError("Aggregation plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _aggregation_plugins:
        raise ConfigurationError(f"Unknown aggregation experiment plugin '{name}'")
    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Aggregation plugin options must be a mapping")
    try:
        coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"aggregation_plugin:{name}: {exc}") from exc
    prepared = dict(options)
    prepared.pop("security_level", None)
    _aggregation_plugins[name].validate(prepared, context=f"aggregation_plugin:{name}")


def validate_baseline_plugin_definition(definition: Dict[str, Any]) -> None:
    """Validate a baseline plugin definition."""

    if not definition:
        raise ConfigurationError("Baseline plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _baseline_plugins:
        raise ConfigurationError(f"Unknown baseline comparison plugin '{name}'")
    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Baseline plugin options must be a mapping")
    try:
        coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"baseline_plugin:{name}: {exc}") from exc
    prepared = dict(options)
    prepared.pop("security_level", None)
    _baseline_plugins[name].validate(prepared, context=f"baseline_plugin:{name}")


def validate_validation_plugin_definition(definition: Dict[str, Any]) -> None:
    """Validate a validation plugin definition."""

    if not definition:
        raise ConfigurationError("Validation plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _validation_plugins:
        raise ConfigurationError(f"Unknown validation plugin '{name}'")
    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Validation plugin options must be a mapping")
    try:
        coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"validation_plugin:{name}: {exc}") from exc
    prepared = dict(options)
    prepared.pop("security_level", None)
    _validation_plugins[name].validate(prepared, context=f"validation_plugin:{name}")


def validate_early_stop_plugin_definition(definition: Dict[str, Any]) -> None:
    """Validate an early-stop plugin definition."""

    if not definition:
        raise ConfigurationError("Early-stop plugin definition cannot be empty")
    name = definition.get("name")
    options = definition.get("options", {})
    if name not in _early_stop_plugins:
        raise ConfigurationError(f"Unknown early-stop plugin '{name}'")
    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Early-stop plugin options must be a mapping")
    try:
        coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"early_stop_plugin:{name}: {exc}") from exc
    prepared = dict(options)
    prepared.pop("security_level", None)
    _early_stop_plugins[name].validate(prepared, context=f"early_stop_plugin:{name}")


def normalize_early_stop_definitions(definitions: Any) -> List[Dict[str, Any]]:
    """Normalise raw early-stop definitions into plugin factory definitions."""

    normalized: List[Dict[str, Any]] = []
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


def _normalize_early_stop_entry(entry: Any) -> Dict[str, Any]:
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


def _load_default_plugins() -> None:
    """Load default plugin implementations via import side-effects."""

    try:  # pragma: no cover - best-effort import only
        import_module("elspeth.plugins.experiments")
    except ImportError:
        pass


_load_default_plugins()
