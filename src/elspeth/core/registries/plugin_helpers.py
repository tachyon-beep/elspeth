"""Helper functions for plugin creation with inheritance patterns.

This module provides the create_plugin_with_inheritance() function that consolidates
the "controls pattern" used across multiple registries (utilities, middleware, controls,
experiments). This pattern handles:

- Optional plugin support (return None if definition is None)
- Security/determinism level inheritance from parent context
- Manual provenance tracking
- Context derivation or creation
- Pre-built context passing to registry

The helper eliminates 400+ lines of duplicate code across 12+ plugin creation functions.
"""

from __future__ import annotations

from typing import Any, Iterable, TypeVar

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.security import (
    coalesce_determinism_level,
    coalesce_security_level,
    ensure_security_level,
)
from elspeth.core.validation.base import ConfigurationError

from .base import BasePluginRegistry

T = TypeVar("T")


def create_plugin_with_inheritance(
    registry: BasePluginRegistry[T],
    definition: dict[str, Any] | None,
    *,
    plugin_kind: str,
    parent_context: PluginContext | None = None,
    provenance: Iterable[str] | None = None,
    allow_none: bool = False,
) -> T | None:
    """
    Create plugin with inheritance pattern (controls/middleware/experiments pattern).

    This helper consolidates the "controls pattern" used across multiple registries:
    1. Optional plugin support (return None if definition is None and allow_none=True)
    2. Security/determinism level inheritance from parent if not explicitly specified
    3. Manual provenance tracking with multiple sources
    4. Context derivation or creation based on parent existence
    5. Pre-built context passed to registry.create() (bypassing extract_security_levels)

    This pattern differs from standard registry.create() because it:
    - Allows returning None for optional plugins (rate_limiter, cost_tracker)
    - Inherits levels from parent WITHOUT creating nested derivations
    - Performs manual coalescing before context creation
    - Tracks provenance explicitly from definition and options

    Args:
        registry: The BasePluginRegistry to create from
        definition: Plugin definition dict with 'name', 'options', optional security levels
        plugin_kind: Plugin type for provenance (e.g., "rate_limiter", "row_plugin")
        parent_context: Optional parent context to inherit security/determinism from
        provenance: Additional provenance sources to append
        allow_none: If True, return None when definition is None (for optional plugins)

    Returns:
        Plugin instance of type T, or None if allow_none=True and definition is None

    Raises:
        ValueError: If definition is empty and allow_none=False
        ValueError: If definition missing 'name' or 'plugin'
        ConfigurationError: If security level coalescing fails

    Example:
        >>> # Create optional rate limiter (can be None)
        >>> limiter = create_plugin_with_inheritance(
        ...     rate_limiter_registry,
        ...     {"name": "fixed_window", "options": {"rate": 100}},
        ...     plugin_kind="rate_limiter",
        ...     parent_context=parent_ctx,
        ...     allow_none=True,
        ... )

        >>> # Create required row plugin (must exist)
        >>> plugin = create_plugin_with_inheritance(
        ...     row_plugin_registry,
        ...     {"name": "score_extraction", "options": {"threshold": 0.5}},
        ...     plugin_kind="row_plugin",
        ...     parent_context=parent_ctx,
        ...     allow_none=False,
        ... )
    """
    # Handle None/empty definition
    if not definition:
        if allow_none:
            return None
        raise ValueError(f"{plugin_kind} definition cannot be empty")

    # Extract plugin name
    name = definition.get("name") or definition.get("plugin")
    if not name:
        raise ValueError(f"{plugin_kind} definition missing 'name' or 'plugin'")

    # Check if plugin exists early for better error messages
    try:
        registry._get_factory(name)
    except ValueError as exc:
        # Re-raise with expected format for backward compatibility
        raise ValueError(f"Unknown {plugin_kind} '{name}'") from exc

    options = dict(definition.get("options", {}) or {})

    # =========================================================================
    # Manual security level coalescing (why this function exists)
    # =========================================================================
    # Extract levels from definition, options, and parent
    definition_sec_level = definition.get("security_level")
    option_sec_level = options.get("security_level")
    parent_sec_level = getattr(parent_context, "security_level", None)

    definition_det_level = definition.get("determinism_level")
    option_det_level = options.get("determinism_level")

    # Build provenance tracking
    sources: list[str] = []
    if definition_sec_level is not None:
        sources.append(f"{plugin_kind}:{name}.definition.security_level")
    if option_sec_level is not None:
        sources.append(f"{plugin_kind}:{name}.options.security_level")

    if definition_det_level is not None:
        sources.append(f"{plugin_kind}:{name}.definition.determinism_level")
    if option_det_level is not None:
        sources.append(f"{plugin_kind}:{name}.options.determinism_level")

    if provenance:
        sources.extend(provenance)

    if definition_sec_level is None and option_sec_level is None:
        raise ConfigurationError(f"{plugin_kind}:{name}: security_level must be declared on the plugin definition or options")
    if definition_det_level is None and option_det_level is None:
        raise ConfigurationError(f"{plugin_kind}:{name}: determinism_level must be declared on the plugin definition or options")

    # Coalesce security level with downgrade prevention
    # Security enforcement: child plugins CANNOT downgrade parent's security classification
    # but CAN upgrade or match it
    try:
        child_sec_level = coalesce_security_level(definition_sec_level, option_sec_level)
    except ValueError as exc:
        raise ConfigurationError(f"{plugin_kind}:{name}: {exc}") from exc

    level = coalesce_security_level(child_sec_level)
    if parent_sec_level is not None:
        parent_level = parent_sec_level if isinstance(parent_sec_level, SecurityLevel) else ensure_security_level(parent_sec_level)
        if level < parent_level:
            child_text = level.value if isinstance(level, SecurityLevel) else str(level)
            parent_text = parent_level.value if isinstance(parent_level, SecurityLevel) else str(parent_level)
            raise ConfigurationError(f"{plugin_kind}:{name}: security_level '{child_text}' cannot downgrade parent level '{parent_text}'")

    try:
        det_level = coalesce_determinism_level(definition_det_level, option_det_level)
    except ValueError as exc:
        raise ConfigurationError(f"{plugin_kind}:{name}: {exc}") from exc

    # det_level already normalized by coalesce_determinism_level

    provenance_tuple = tuple(sources or (f"{plugin_kind}:{name}.resolved",))

    # =========================================================================
    # Prepare payload (strip framework keys)
    # =========================================================================
    payload = dict(options)
    payload.pop("security_level", None)
    payload.pop("determinism_level", None)

    # =========================================================================
    # Create context manually (controls pattern)
    # =========================================================================
    # We create the context ourselves instead of letting registry.create() do it
    # because we need to control inheritance without nesting
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind=plugin_kind,
            security_level=level,
            determinism_level=det_level,
            provenance=provenance_tuple,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind=plugin_kind,
            security_level=level,
            determinism_level=det_level,
            provenance=provenance_tuple,
        )

    # =========================================================================
    # Use factory directly with pre-built context
    # =========================================================================
    # We use the factory directly instead of registry.create() because
    # registry.create() would create a NEW context derived from our context,
    # resulting in double-nesting. We've already built the exact context we want.
    factory = registry._get_factory(name)
    plugin = factory.instantiate(
        payload,
        plugin_context=context,
        schema_context=f"{plugin_kind}:{name}",
    )
    return plugin


__all__ = ["create_plugin_with_inheritance"]
