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

Backward Compatibility:
    The old PluginRegistry singleton is still available as `registry` for
    backward compatibility during Phase 1.
"""

# Import old registry module (the file at elspeth/core/registry.py)
# We need to import it using importlib to avoid the directory shadowing the file
import importlib.util
import sys
from pathlib import Path

# Dynamically load the old registry.py file
_registry_file = Path(__file__).parent.parent / "registry.py"
_spec = importlib.util.spec_from_file_location("elspeth.core._old_registry", _registry_file)

# Check that spec was created successfully
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load registry module from {_registry_file}")

_old_registry_module = importlib.util.module_from_spec(_spec)
sys.modules["elspeth.core._old_registry"] = _old_registry_module
_spec.loader.exec_module(_old_registry_module)

# Re-export the singleton and classes for backward compatibility
registry = _old_registry_module.registry
PluginFactory = _old_registry_module.PluginFactory
PluginRegistry = _old_registry_module.PluginRegistry

# Import new base framework
# ruff: noqa: E402 - imports must come after dynamic module loading above
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
    # Backward compatibility (Phase 1)
    "registry",
    "PluginFactory",
    "PluginRegistry",
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
