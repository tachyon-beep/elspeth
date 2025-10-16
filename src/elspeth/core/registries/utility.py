"""Registry for utility plugins used outside experiment flows."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from elspeth.core.base.plugin_context import PluginContext

from .base import BasePluginRegistry

# Use base registry infrastructure
_utility_registry = BasePluginRegistry[Any]("utility")

# Expose registry for external use (e.g., plugin registration)
utility_plugin_registry = _utility_registry


def register_utility_plugin(
    name: str,
    factory: Callable[[dict[str, Any], PluginContext], Any],
    *,
    schema: Mapping[str, Any] | None = None,
) -> None:
    """Register a named utility plugin."""
    _utility_registry.register(name, factory, schema=schema)


def create_utility_plugin(
    definition: Mapping[str, Any],
    *,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
) -> Any:
    """Instantiate a registered utility plugin from a declarative definition (controls pattern).

    Now uses create_plugin_with_inheritance() helper to eliminate duplication.
    """
    from .plugin_helpers import create_plugin_with_inheritance

    return create_plugin_with_inheritance(
        _utility_registry,
        dict(definition) if definition else None,  # Convert Mapping to Dict
        plugin_kind="utility",
        parent_context=parent_context,
        provenance=provenance,
        allow_none=False,
    )


def create_named_utility(
    name: str,
    options: Mapping[str, Any] | None,
    *,
    security_level: str | None = None,
    determinism_level: str | None = None,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
) -> Any:
    """Instantiate a utility plugin directly by name."""

    definition = {
        "name": name,
        "options": dict(options or {}),
        "security_level": security_level,
        "determinism_level": determinism_level,
    }
    return create_utility_plugin(definition, parent_context=parent_context, provenance=provenance)


__all__ = ["register_utility_plugin", "create_utility_plugin", "create_named_utility", "utility_plugin_registry"]
