"""Registry for LLM middleware plugins."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.protocols import LLMMiddleware
from elspeth.core.security import coalesce_security_level
from elspeth.core.validation.base import ConfigurationError

from .base import BasePluginRegistry

# Use base registry infrastructure
_middleware_registry = BasePluginRegistry[LLMMiddleware]("llm_middleware")

# Backward compatibility: expose internal dict for test mocking
_middlewares = _middleware_registry._plugins


def register_middleware(
    name: str,
    factory: Callable[[dict[str, Any], PluginContext], LLMMiddleware],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    """Register a middleware plugin with the registry."""
    _middleware_registry.register(name, factory, schema=schema)


def create_middleware(
    definition: dict[str, Any],
    *,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
) -> LLMMiddleware:
    """Create a middleware instance from definition (controls pattern).

    Now uses create_plugin_with_inheritance() helper to eliminate duplication.
    """
    from .plugin_helpers import create_plugin_with_inheritance  # pylint: disable=import-outside-toplevel

    result = create_plugin_with_inheritance(
        _middleware_registry,
        definition,
        plugin_kind="llm_middleware",
        parent_context=parent_context,
        provenance=provenance,
        allow_none=False,
    )
    # When allow_none=False, create_plugin_with_inheritance never returns None
    # (it raises ValueError instead), but add a runtime guard for safety in optimized runs
    if result is None:  # pragma: no cover - defensive, should be unreachable
        name = definition.get("name") or definition.get("plugin") or "<unknown>"
        raise RuntimeError(f"Unexpected None from middleware factory for '{name}' with allow_none=False")
    return result


def create_middlewares(
    definitions: list[dict[str, Any]] | None,
    *,
    parent_context: PluginContext | None = None,
) -> list[LLMMiddleware]:
    """Create a list of middleware instances from definitions.

    Applies the standard middleware creation path with inheritance and context.
    """
    if not definitions:
        return []
    return [create_middleware(defn, parent_context=parent_context) for defn in definitions]


def validate_middleware_definition(definition: dict[str, Any]) -> None:
    """Validate middleware definition without instantiation."""
    if not definition:
        raise ConfigurationError("Middleware definition cannot be empty")

    name = definition.get("name") or definition.get("plugin")
    if not name:
        raise ConfigurationError("Middleware definition missing 'name' or 'plugin'")

    # Check if plugin exists
    try:
        _middleware_registry._get_factory(name)
    except ValueError:
        available = ", ".join(sorted(_middleware_registry.list_plugins())) or "<none>"
        raise ConfigurationError(f"Unknown LLM middleware '{name}'. Available: {available}")

    options_raw = definition.get("options", {})
    if options_raw is None:
        options_dict: dict[str, Any] = {}
    elif not isinstance(options_raw, dict):
        raise ConfigurationError("Middleware options must be a mapping")
    else:
        options_dict = dict(options_raw)

    # Validate security level coalescing
    try:
        coalesce_security_level(definition.get("security_level"), options_dict.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"llm_middleware:{name}: {exc}") from exc

    # Validate options against schema
    options_dict.pop("security_level", None)
    try:
        _middleware_registry.validate(name, options_dict)
    except ValueError as exc:
        # Convert ValueError to ConfigurationError for backward compatibility
        raise ConfigurationError(str(exc)) from exc


__all__ = ["register_middleware", "create_middleware", "create_middlewares", "validate_middleware_definition"]
