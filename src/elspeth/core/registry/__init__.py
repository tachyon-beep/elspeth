"""
Unified plugin registry infrastructure.

This module provides base classes and utilities for creating consistent
plugin registries across the Elspeth framework. It consolidates the factory
pattern previously duplicated across 5 separate registry implementations.

Architecture:
    - BasePluginFactory: Generic factory for plugin creation and validation
    - BasePluginRegistry: Generic registry for plugin management
    - Context utilities: Shared security level and context handling
    - Common schemas: Reusable validation schemas

Usage:
    >>> from elspeth.core.registry import BasePluginRegistry
    >>> registry = BasePluginRegistry[MyPlugin]("my_plugin")
    >>> registry.register("name", factory_fn, schema=validation_schema)
    >>> plugin = registry.create("name", options, parent_context=context)
"""

from typing import Any, Iterable, Mapping

# Import new base framework
from .base import BasePluginFactory, BasePluginRegistry, PluginFactoryMap
from .context_utils import (
    create_plugin_context,
    extract_security_levels,
    prepare_plugin_payload,
)
from .plugin_helpers import create_plugin_with_inheritance
from .schemas import (
    ARTIFACT_DESCRIPTOR_SCHEMA,
    ARTIFACTS_SECTION_SCHEMA,
    DETERMINISM_LEVEL_SCHEMA,
    ON_ERROR_ENUM,
    SECURITY_LEVEL_SCHEMA,
    with_artifact_properties,
    with_error_handling,
    with_security_properties,
)

__all__ = [
    # Base classes
    "BasePluginFactory",
    "BasePluginRegistry",
    "PluginFactoryMap",
    # Context utilities
    "create_plugin_context",
    "extract_security_levels",
    "prepare_plugin_payload",
    # Plugin helpers
    "create_plugin_with_inheritance",
    # Schemas
    "ARTIFACT_DESCRIPTOR_SCHEMA",
    "ARTIFACTS_SECTION_SCHEMA",
    "DETERMINISM_LEVEL_SCHEMA",
    "ON_ERROR_ENUM",
    "SECURITY_LEVEL_SCHEMA",
    "with_artifact_properties",
    "with_error_handling",
    "with_security_properties",
    # Compatibility shim
    "create_llm_from_definition",
]

__version__ = "0.1.0"


# Compatibility shim for create_llm_from_definition
# This function provides the same interface as the old registry.create_llm_from_definition
# but uses the new llm_registry directly to avoid circular imports
def create_llm_from_definition(
    definition: Mapping[str, Any],
    *,
    parent_context: Any,
    provenance: Iterable[str] | None = None,
) -> Any:
    """Create LLM from definition with inherited context (compatibility shim).

    This function exists for backward compatibility with code that used
    registry.create_llm_from_definition(). It delegates to llm_registry.
    """
    from elspeth.core.llm_registry import llm_registry
    from elspeth.core.plugins import PluginContext
    from elspeth.core.security import coalesce_security_level, coalesce_determinism_level
    from elspeth.core.validation_base import ConfigurationError

    if not isinstance(definition, Mapping):
        raise ValueError("LLM definition must be a mapping")

    plugin_name = definition.get("plugin")
    if not plugin_name:
        raise ConfigurationError("LLM definition requires 'plugin'")

    options = dict(definition.get("options", {}) or {})

    # Coalesce security and determinism levels
    entry_sec = definition.get("security_level")
    opts_sec = options.get("security_level")
    entry_det = definition.get("determinism_level")
    opts_det = options.get("determinism_level")

    sources = []
    if entry_sec:
        sources.append(f"llm:{plugin_name}.definition.security_level")
    if opts_sec:
        sources.append(f"llm:{plugin_name}.options.security_level")
    if entry_det:
        sources.append(f"llm:{plugin_name}.definition.determinism_level")
    if opts_det:
        sources.append(f"llm:{plugin_name}.options.determinism_level")
    if provenance:
        sources.extend(provenance)

    try:
        sec_level = coalesce_security_level(parent_context.security_level, entry_sec, opts_sec)
    except ValueError as exc:
        raise ConfigurationError(f"llm:{plugin_name}: {exc}") from exc

    if entry_det is not None or opts_det is not None:
        try:
            det_level = coalesce_determinism_level(entry_det, opts_det)
        except ValueError as exc:
            raise ConfigurationError(f"llm:{plugin_name}: {exc}") from exc
    else:
        det_level = parent_context.determinism_level

    options["security_level"] = sec_level
    options["determinism_level"] = det_level

    return llm_registry.create(
        plugin_name,
        options,
        provenance=tuple(sources or (f"llm:{plugin_name}.resolved",)),
        parent_context=parent_context,
    )
