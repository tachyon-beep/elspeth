"""Utilities for plugin context creation and management.

This module consolidates the 30-40 line context handling pattern
that was repeated in every create_* function across 5 registries.
"""

from __future__ import annotations

from typing import Any, Iterable

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import DeterminismLevel, SecurityLevel
from elspeth.core.security import (
    coalesce_determinism_level,
    coalesce_security_level,
)
from elspeth.core.validation.base import ConfigurationError


def extract_security_levels(
    definition: dict[str, Any],
    options: dict[str, Any],
    *,
    plugin_type: str,
    plugin_name: str,
    parent_context: PluginContext | None = None,
    require_determinism: bool = True,
) -> tuple[SecurityLevel, DeterminismLevel, list[str]]:
    """
    Extract and normalize security/determinism levels from definition and options.

    Consolidates the 30-40 line pattern repeated in every create_* function.
    Handles:
    - Extracting levels from definition, options, and parent context
    - Coalescing multiple sources with precedence rules
    - Normalizing to canonical values
    - Building provenance tracking for audit trails
    - Validating required levels are present

    Args:
        definition: Plugin definition dictionary (may contain security_level)
        options: Plugin options dictionary (may contain security_level)
        plugin_type: Type of plugin (e.g., "datasource", "llm")
        plugin_name: Name of the plugin
        parent_context: Optional parent context for inheritance
        require_determinism: Whether determinism_level is required

    Returns:
        Tuple of (security_level, determinism_level, provenance_sources)
        where provenance_sources is a list of strings indicating where
        the levels came from (for audit trails)

    Raises:
        ConfigurationError: If required levels are missing or invalid

    Example:
        >>> security, determinism, sources = extract_security_levels(
        ...     definition={"security_level": "confidential"},
        ...     options={"path": "data.csv"},
        ...     plugin_type="datasource",
        ...     plugin_name="csv",
        ... )
        >>> print(security, determinism)
        confidential deterministic
        >>> print(sources)
        ['datasource:csv.definition.security_level']
    """
    # Extract levels from various sources
    entry_sec_level = definition.get("security_level")
    option_sec_level = options.get("security_level")
    parent_sec_level = getattr(parent_context, "security_level", None)

    entry_det_level = definition.get("determinism_level")
    option_det_level = options.get("determinism_level")
    parent_det_level = getattr(parent_context, "determinism_level", None)

    # Build provenance tracking
    sources: list[str] = []
    if entry_sec_level is not None:
        sources.append(f"{plugin_type}:{plugin_name}.definition.security_level")
    if option_sec_level is not None:
        sources.append(f"{plugin_type}:{plugin_name}.options.security_level")
    if entry_det_level is not None:
        sources.append(f"{plugin_type}:{plugin_name}.definition.determinism_level")
    if option_det_level is not None:
        sources.append(f"{plugin_type}:{plugin_name}.options.determinism_level")

    # Extract plugin's CLEARANCE level (NO coalescing - defined once at creation)
    # ADR-002-B: Plugin clearance defined ONCE in declared_security_level, that's it
    # base.py already added declared_security_level to definition, so entry_sec_level has it

    # SECURITY: Reject configuration attempting to override security_level
    if option_sec_level is not None:
        raise ConfigurationError(
            f"{plugin_type}:{plugin_name}: security_level cannot be set in options. "
            f"ADR-002-B: Security policy is immutable and plugin-author-owned."
        )

    security_level: SecurityLevel
    if entry_sec_level is None:
        # No security level found - FAIL LOUD
        raise ConfigurationError(
            f"{plugin_type}:{plugin_name}: security_level is required. "
            f"ADR-002-B: Plugins must declare declared_security_level in registration. "
            f"No backdoors, no coalescing, no defaults - defined ONCE at creation."
        )

    # Normalize to SecurityLevel enum
    from elspeth.core.security import ensure_security_level
    security_level = ensure_security_level(entry_sec_level)

    # Coalesce determinism level
    determinism_level: DeterminismLevel | None
    if entry_det_level is not None or option_det_level is not None:
        try:
            determinism_level = coalesce_determinism_level(entry_det_level, option_det_level)
        except ValueError as exc:
            raise ConfigurationError(f"{plugin_type}:{plugin_name}: {exc}") from exc
    else:
        # Inherit from parent or default to None
        determinism_level = parent_det_level if parent_det_level is not None else None

    if determinism_level is None:
        if require_determinism:
            raise ConfigurationError(f"{plugin_type}:{plugin_name}: determinism_level is required")
        # Default to "none" if not required
        determinism_level = DeterminismLevel.NONE

    # Already normalized to DeterminismLevel by coalesce_determinism_level / default

    return security_level, determinism_level, sources


def create_plugin_context(
    plugin_name: str,
    plugin_kind: str,
    security_level: SecurityLevel | None,
    determinism_level: DeterminismLevel,
    provenance: Iterable[str],
    *,
    parent_context: PluginContext | None = None,
) -> PluginContext:
    """
    Create or derive a plugin context consistently.

    Handles both new context creation and context derivation from
    a parent context. Ensures consistent provenance tracking.

    Args:
        plugin_name: Name of the plugin
        plugin_kind: Kind of plugin (e.g., "datasource", "llm")
        security_level: Normalized security level
        determinism_level: Normalized determinism level
        provenance: Provenance source identifiers
        parent_context: Optional parent context to derive from

    Returns:
        New or derived PluginContext

    Example:
        >>> context = create_plugin_context(
        ...     plugin_name="csv",
        ...     plugin_kind="datasource",
        ...     security_level="internal",
        ...     determinism_level="deterministic",
        ...     provenance=["datasource:csv.options"],
        ... )
    """
    provenance_tuple = tuple(provenance) if provenance else (f"{plugin_kind}:{plugin_name}.resolved",)

    if parent_context:
        # When deriving from parent, None security_level is OK - will inherit from parent
        return parent_context.derive(
            plugin_name=plugin_name,
            plugin_kind=plugin_kind,
            security_level=security_level,
            determinism_level=determinism_level,
            provenance=provenance_tuple,
        )

    # Creating new context without parent
    # ADR-001 Fail-Loud: security_level MUST be explicit (no defaults, no graceful degradation)
    if security_level is None:
        raise RuntimeError(
            f"create_plugin_context() called with security_level=None for {plugin_kind}:{plugin_name}. "
            f"Security level must be explicit (ADR-001 fail-loud principle). "
            f"This indicates a programming error in plugin registration or context creation. "
            f"Plugins must declare security_level - no defaults permitted in high-security systems."
        )

    return PluginContext(
        plugin_name=plugin_name,
        plugin_kind=plugin_kind,
        security_level=security_level,
        determinism_level=determinism_level,
        provenance=provenance_tuple,
    )


def prepare_plugin_payload(
    options: dict[str, Any],
    *,
    strip_security: bool = True,
    strip_determinism: bool = True,
) -> dict[str, Any]:
    """
    Prepare plugin options by removing framework-level keys.

    Security and determinism levels are framework-level concerns
    handled by the registry and context system. They should be
    stripped from the options dictionary before passing to the
    plugin factory.

    Args:
        options: Original plugin options
        strip_security: Remove security_level from options
        strip_determinism: Remove determinism_level from options

    Returns:
        Copy of options with framework keys removed

    Example:
        >>> options = {
        ...     "path": "data.csv",
        ...     "security_level": "confidential",
        ...     "determinism_level": "deterministic"
        ... }
        >>> payload = prepare_plugin_payload(options)
        >>> print(payload)
        {'path': 'data.csv'}
    """
    payload = dict(options)
    # ADR-002-B: Reject security policy in configuration
    if "security_level" in payload:
        raise ConfigurationError(
            "Plugin security policy is author-owned (ADR-002-B). "
            "Remove security_level from configuration."
        )
    if "allow_downgrade" in payload:
        raise ConfigurationError(
            "Plugin downgrade policy is author-owned (ADR-002-B). "
            "Remove allow_downgrade from configuration."
        )
    if strip_determinism:
        payload.pop("determinism_level", None)
    return payload


__all__ = [
    "extract_security_levels",
    "create_plugin_context",
    "prepare_plugin_payload",
]
