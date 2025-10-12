"""Registry for LLM middleware plugins."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping

from elspeth.core.plugins import PluginContext, apply_plugin_context
from elspeth.core.security import coalesce_security_level
from elspeth.core.validation import ConfigurationError, validate_schema

from .middleware import LLMMiddleware


class _Factory:
    def __init__(
        self,
        factory: Callable[[Dict[str, Any], PluginContext], LLMMiddleware],
        schema: Mapping[str, Any] | None = None,
    ):
        self.factory = factory
        self.schema = schema

    def validate(self, options: Dict[str, Any], *, context: str) -> None:
        if self.schema is None:
            return
        errors = list(validate_schema(options or {}, self.schema, context=context))
        if errors:
            raise ConfigurationError("\n".join(msg.format() for msg in errors))

    def create(
        self,
        options: Dict[str, Any],
        *,
        plugin_context: PluginContext,
        schema_context: str,
    ) -> LLMMiddleware:
        self.validate(options, context=schema_context)
        return self.factory(options, plugin_context)


_middlewares: Dict[str, _Factory] = {}


def register_middleware(
    name: str,
    factory: Callable[[Dict[str, Any], PluginContext], LLMMiddleware],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    _middlewares[name] = _Factory(factory, schema=schema)


def create_middleware(
    definition: Dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
) -> LLMMiddleware:
    if not definition:
        raise ValueError("Middleware definition cannot be empty")
    name = definition.get("name") or definition.get("plugin")
    if not name:
        raise ValueError("Middleware definition missing 'name' or 'plugin'")
    if name not in _middlewares:
        raise ValueError(f"Unknown LLM middleware '{name}'")
    options = dict(definition.get("options", {}) or {})
    definition_level = definition.get("security_level")
    option_level = options.get("security_level")
    sources: list[str] = []
    if definition_level is not None:
        sources.append(f"llm_middleware:{name}.definition.security_level")
    if option_level is not None:
        sources.append(f"llm_middleware:{name}.options.security_level")
    if provenance:
        sources.extend(provenance)
    try:
        level = coalesce_security_level(definition_level, option_level)
    except ValueError as exc:
        raise ConfigurationError(f"llm_middleware:{name}: {exc}") from exc
    payload = dict(options)
    payload.pop("security_level", None)
    provenance_sources = tuple(sources or (f"llm_middleware:{name}.resolved",))
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind="llm_middleware",
            security_level=level,
            provenance=provenance_sources,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind="llm_middleware",
            security_level=level,
            provenance=provenance_sources,
        )
    middleware = _middlewares[name].create(
        payload,
        plugin_context=context,
        schema_context=f"llm_middleware:{name}",
    )
    apply_plugin_context(middleware, context)
    return middleware


def create_middlewares(
    definitions: list[Dict[str, Any]] | None,
    *,
    parent_context: PluginContext | None = None,
) -> list[LLMMiddleware]:
    if not definitions:
        return []
    return [create_middleware(defn, parent_context=parent_context) for defn in definitions]


def validate_middleware_definition(definition: Dict[str, Any]) -> None:
    if not definition:
        raise ConfigurationError("Middleware definition cannot be empty")
    name = definition.get("name") or definition.get("plugin")
    if not name:
        raise ConfigurationError("Middleware definition missing 'name' or 'plugin'")
    if name not in _middlewares:
        options = ", ".join(sorted(_middlewares)) or "<none>"
        raise ConfigurationError(f"Unknown LLM middleware '{name}'. Available: {options}")
    options = definition.get("options", {})
    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Middleware options must be a mapping")
    try:
        coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"llm_middleware:{name}: {exc}") from exc
    options = dict(options)
    options.pop("security_level", None)
    _middlewares[name].validate(options, context=f"llm_middleware:{name}")


__all__ = ["register_middleware", "create_middleware", "create_middlewares", "validate_middleware_definition"]
