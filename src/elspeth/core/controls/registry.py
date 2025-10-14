"""Registry for rate limiter and cost tracker plugins.

NOTE: This registry has been migrated to use BasePluginRegistry framework (Phase 2).
The actual plugin registrations are in rate_limiter_registry.py and cost_tracker_registry.py.
This module now provides facade functions that delegate to the new registries while
preserving the existing API and special handling for optional plugins (None returns).

Migrated registries:
- rate_limiter_registry: 3 plugins (noop, fixed_window, adaptive)
- cost_tracker_registry: 2 plugins (noop, fixed_price)
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Iterable

from elspeth.core.plugins import PluginContext
from elspeth.core.security import coalesce_security_level  # Still needed for validation functions
from elspeth.core.validation import ConfigurationError

from .cost_tracker import CostTracker
from .cost_tracker_registry import cost_tracker_registry
from .rate_limit import RateLimiter
from .rate_limiter_registry import rate_limiter_registry


def register_rate_limiter(name: str, factory: Callable[..., RateLimiter], schema: dict[str, Any] | None = None) -> None:
    """Register a custom rate limiter factory under the given name.

    NOTE: This function now delegates to the migrated rate_limiter_registry.
    For backward compatibility, it handles both single-parameter and two-parameter
    factory signatures.
    """
    signature = inspect.signature(factory)

    if len(signature.parameters) == 1:
        # Old style: factory(options) -> RateLimiter
        def _wrapped(options: dict[str, Any], _context: PluginContext) -> RateLimiter:
            return factory(options)

        rate_limiter_registry.register(name, _wrapped, schema=schema)
    else:
        # New style: factory(options, context) -> RateLimiter
        rate_limiter_registry.register(name, factory, schema=schema)


def register_cost_tracker(name: str, factory: Callable[..., CostTracker], schema: dict[str, Any] | None = None) -> None:
    """Register a custom cost tracker factory under the given name.

    NOTE: This function now delegates to the migrated cost_tracker_registry.
    For backward compatibility, it handles both single-parameter and two-parameter
    factory signatures.
    """
    signature = inspect.signature(factory)

    if len(signature.parameters) == 1:
        # Old style: factory(options) -> CostTracker
        def _wrapped(options: dict[str, Any], _context: PluginContext) -> CostTracker:
            return factory(options)

        cost_tracker_registry.register(name, _wrapped, schema=schema)
    else:
        # New style: factory(options, context) -> CostTracker
        cost_tracker_registry.register(name, factory, schema=schema)


def create_rate_limiter(
    definition: dict[str, Any] | None,
    *,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
) -> RateLimiter | None:
    """Instantiate a rate limiter from a configuration dictionary.

    NOTE: This function now uses create_plugin_with_inheritance() helper
    to eliminate duplication. Returns None if definition is None or empty
    (optional plugin pattern).
    """
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    return create_plugin_with_inheritance(
        rate_limiter_registry,
        definition,
        plugin_kind="rate_limiter",
        parent_context=parent_context,
        provenance=provenance,
        allow_none=True,  # Optional plugin pattern
    )


def create_cost_tracker(
    definition: dict[str, Any] | None,
    *,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
) -> CostTracker | None:
    """Instantiate a cost tracker from a configuration dictionary.

    NOTE: This function now uses create_plugin_with_inheritance() helper
    to eliminate duplication. Returns None if definition is None or empty
    (optional plugin pattern).
    """
    from elspeth.core.registry.plugin_helpers import create_plugin_with_inheritance

    return create_plugin_with_inheritance(
        cost_tracker_registry,
        definition,
        plugin_kind="cost_tracker",
        parent_context=parent_context,
        provenance=provenance,
        allow_none=True,  # Optional plugin pattern
    )


def validate_rate_limiter(definition: dict[str, Any] | None) -> None:
    """Validate a rate limiter definition without instantiating it.

    NOTE: This function now delegates to the migrated rate_limiter_registry.
    It preserves special handling for optional plugins (no-op when definition is None).
    """
    if not definition:
        return

    name = definition.get("plugin") or definition.get("name")
    if not name or not isinstance(name, str):
        raise ConfigurationError("Rate limiter definition missing 'name'/'plugin' field or name is not a string")

    options = definition.get("options", {})

    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Rate limiter options must be a mapping")

    # Validate security level coalescing
    try:
        level = coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"rate_limiter:{name}: {exc}") from exc

    # Prepare payload and delegate to registry
    prepared = dict(options)
    prepared.pop("security_level", None)
    prepared_with_context = {"security_level": level, **prepared}

    try:
        rate_limiter_registry.validate(name, prepared_with_context)
    except ValueError as exc:
        # BasePluginRegistry raises ValueError for unknown plugins,
        # but we need ConfigurationError for backward compatibility
        raise ConfigurationError(str(exc)) from exc


def validate_cost_tracker(definition: dict[str, Any] | None) -> None:
    """Validate a cost tracker definition without instantiation.

    NOTE: This function now delegates to the migrated cost_tracker_registry.
    It preserves special handling for optional plugins (no-op when definition is None).
    """
    if not definition:
        return

    name = definition.get("plugin") or definition.get("name")
    if not name or not isinstance(name, str):
        raise ConfigurationError("Cost tracker definition missing 'name'/'plugin' field or name is not a string")

    options = definition.get("options", {})

    if options is None:
        options = {}
    elif not isinstance(options, dict):
        raise ConfigurationError("Cost tracker options must be a mapping")

    # Validate security level coalescing
    try:
        level = coalesce_security_level(definition.get("security_level"), options.get("security_level"))
    except ValueError as exc:
        raise ConfigurationError(f"cost_tracker:{name}: {exc}") from exc

    # Prepare payload and delegate to registry
    prepared = dict(options)
    prepared.pop("security_level", None)
    prepared_with_context = {"security_level": level, **prepared}

    try:
        cost_tracker_registry.validate(name, prepared_with_context)
    except ValueError as exc:
        # BasePluginRegistry raises ValueError for unknown plugins,
        # but we need ConfigurationError for backward compatibility
        raise ConfigurationError(str(exc)) from exc


# Backward compatibility: expose internal plugin dicts for tests
# Note: These are direct references (not @property) because @property only works on class descriptors
_rate_limiters: dict[str, Any] = rate_limiter_registry._plugins
_cost_trackers: dict[str, Any] = cost_tracker_registry._plugins


__all__ = [
    "register_rate_limiter",
    "register_cost_tracker",
    "create_rate_limiter",
    "create_cost_tracker",
    "validate_rate_limiter",
    "validate_cost_tracker",
]
