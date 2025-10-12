"""Registry for utility plugins used outside experiment flows."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping

from elspeth.core.plugins import PluginContext, apply_plugin_context
from elspeth.core.security import coalesce_security_level
from elspeth.core.validation import ConfigurationError, validate_schema


class _PluginFactory:
    """Wrap utility plugin factories with optional schema validation."""

    def __init__(
        self,
        factory: Callable[[Dict[str, Any], PluginContext], Any],
        *,
        schema: Mapping[str, Any] | None = None,
    ) -> None:
        self.factory = factory
        self.schema = schema

    def validate(self, options: Dict[str, Any], *, context: str) -> None:
        """Validate plugin options and raise ``ConfigurationError`` on failure."""

        if self.schema is None:
            return
        errors = list(validate_schema(options or {}, self.schema, context=context))
        if errors:
            raise ConfigurationError("\n".join(msg.format() for msg in errors))

    def create(self, options: Dict[str, Any], *, plugin_context: PluginContext, schema_context: str) -> Any:
        """Instantiate the plugin after validation."""

        self.validate(options, context=schema_context)
        return self.factory(options, plugin_context)


_utility_plugins: Dict[str, _PluginFactory] = {}


def register_utility_plugin(
    name: str,
    factory: Callable[[Dict[str, Any], PluginContext], Any],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    """Register a named utility plugin."""

    _utility_plugins[name] = _PluginFactory(factory, schema=schema)


def create_utility_plugin(
    definition: Mapping[str, Any],
    *,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
) -> Any:
    """Instantiate a registered utility plugin from a declarative definition."""

    if not definition:
        raise ValueError("Utility plugin definition cannot be empty")

    name = definition.get("name")
    if not name:
        raise ConfigurationError("utility plugin definition requires 'name'")

    try:
        factory = _utility_plugins[name]
    except KeyError as exc:
        raise ValueError(f"Unknown utility plugin '{name}'") from exc

    options = dict(definition.get("options", {}) or {})
    entry_level = definition.get("security_level")
    option_level = options.get("security_level")
    parent_level = getattr(parent_context, "security_level", None)
    sources: list[str] = []
    if entry_level is not None:
        sources.append(f"utility:{name}.definition.security_level")
    if option_level is not None:
        sources.append(f"utility:{name}.options.security_level")
    if provenance:
        sources.extend(provenance)
    try:
        level = coalesce_security_level(parent_level, entry_level, option_level)
    except ValueError as exc:
        raise ConfigurationError(f"utility:{name}: {exc}") from exc

    payload = dict(options)
    payload.pop("security_level", None)
    context_sources = tuple(sources or (f"utility:{name}.resolved",))
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind="utility",
            security_level=level,
            provenance=context_sources,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind="utility",
            security_level=level,
            provenance=context_sources,
        )

    plugin = factory.create(payload, plugin_context=context, schema_context=f"utility:{name}")
    apply_plugin_context(plugin, context)
    return plugin


def create_named_utility(
    name: str,
    options: Mapping[str, Any] | None,
    *,
    security_level: str | None = None,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
) -> Any:
    """Instantiate a utility plugin directly by name."""

    definition = {
        "name": name,
        "options": dict(options or {}),
        "security_level": security_level,
    }
    return create_utility_plugin(definition, parent_context=parent_context, provenance=provenance)


__all__ = ["register_utility_plugin", "create_utility_plugin", "create_named_utility"]
