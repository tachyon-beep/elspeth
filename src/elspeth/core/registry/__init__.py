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
]

__version__ = "0.1.0"
