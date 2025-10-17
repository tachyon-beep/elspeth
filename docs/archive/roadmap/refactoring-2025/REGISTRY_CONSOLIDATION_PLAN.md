# Registry Consolidation Refactoring Plan

**Status:** Draft
**Created:** 2025-10-14
**Target Completion:** 4 weeks
**Estimated Effort:** 15-20 days
**Risk Level:** Medium

---

## Executive Summary

This document outlines a comprehensive plan to consolidate 5 separate plugin registry implementations into a unified base system, reducing ~900-1000 lines of duplicate code while maintaining backward compatibility and improving maintainability.

### Current State
- **5 registry files** with duplicate factory patterns (~2,087 LOC total)
- **~500 lines** of duplicate factory/validation code
- **~300 lines** of duplicate context propagation logic
- **~100 lines** of duplicate schema definitions

### Target State
- **Single base registry framework** with specialized subclasses
- **Unified factory pattern** eliminating duplication
- **Shared context utilities** for consistent behavior
- **Common schema library** for validation rules

---

## Phase 1: Foundation (Days 1-5)

### Goal
Create the core infrastructure without breaking existing code.

### Tasks

#### 1.1 Create Base Registry Module Structure
**File:** `src/elspeth/core/registry/`

```
src/elspeth/core/registry/
├── __init__.py           # Public API exports
├── base.py               # BasePluginFactory, BasePluginRegistry
├── context_utils.py      # Unified context creation/derivation
├── validation.py         # Shared validation utilities
└── schemas.py            # Common schema definitions
```

**Deliverables:**
- [ ] Directory structure created
- [ ] `__init__.py` with minimal exports
- [ ] All files with docstrings and type hints

**Estimated Time:** 4 hours

---

#### 1.2 Implement BasePluginFactory
**File:** `src/elspeth/core/registry/base.py`

**Design:**

```python
"""Base plugin registry infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, Mapping, TypeVar

from elspeth.core.plugins import PluginContext, apply_plugin_context
from elspeth.core.validation import ConfigurationError, validate_schema

T = TypeVar('T')  # Plugin type


@dataclass
class BasePluginFactory(Generic[T]):
    """
    Base factory for creating and validating plugin instances.

    Consolidates the factory pattern repeated across 5 registries.

    Attributes:
        create: Factory callable that creates plugin instances
        schema: Optional JSON schema for validation
        plugin_type: Human-readable plugin type (e.g., "datasource", "llm")
    """

    create: Callable[[Dict[str, Any], PluginContext], T]
    schema: Mapping[str, Any] | None = None
    plugin_type: str = "plugin"

    def validate(self, options: Dict[str, Any], *, context: str) -> None:
        """
        Validate options against the schema.

        Args:
            options: Plugin options dictionary
            context: Context string for error messages

        Raises:
            ConfigurationError: If validation fails
        """
        if self.schema is None:
            return

        errors = list(validate_schema(options or {}, self.schema, context=context))
        if errors:
            message = "\n".join(msg.format() for msg in errors)
            raise ConfigurationError(message)

    def instantiate(
        self,
        options: Dict[str, Any],
        *,
        plugin_context: PluginContext,
        schema_context: str,
    ) -> T:
        """
        Validate and create a plugin instance.

        Args:
            options: Plugin configuration options
            plugin_context: Security and provenance context
            schema_context: Context string for validation errors

        Returns:
            Instantiated plugin of type T
        """
        self.validate(options, context=schema_context)
        plugin = self.create(options, plugin_context)
        apply_plugin_context(plugin, plugin_context)
        return plugin


# Type alias for registry dictionaries
PluginFactoryMap = Dict[str, BasePluginFactory[T]]
```

**Test Coverage:**
```python
# tests/test_registry_base.py

def test_base_factory_validation_success():
    """Factory validates options against schema."""

def test_base_factory_validation_failure():
    """Factory raises ConfigurationError on invalid options."""

def test_base_factory_instantiation():
    """Factory creates and applies context to plugin."""

def test_base_factory_no_schema():
    """Factory works without schema validation."""
```

**Deliverables:**
- [ ] `BasePluginFactory` implemented
- [ ] Full docstrings with examples
- [ ] Type hints complete
- [ ] Unit tests (>90% coverage)

**Estimated Time:** 6 hours

---

#### 1.3 Implement Context Utilities
**File:** `src/elspeth/core/registry/context_utils.py`

**Design:**

```python
"""Utilities for plugin context creation and management."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from elspeth.core.plugins import PluginContext
from elspeth.core.security import (
    coalesce_determinism_level,
    coalesce_security_level,
    normalize_determinism_level,
    normalize_security_level,
)
from elspeth.core.validation import ConfigurationError


def extract_security_levels(
    definition: Dict[str, Any],
    options: Dict[str, Any],
    *,
    plugin_type: str,
    plugin_name: str,
    parent_context: PluginContext | None = None,
    require_security: bool = True,
    require_determinism: bool = True,
) -> tuple[str, str, list[str]]:
    """
    Extract and normalize security/determinism levels from definition and options.

    Consolidates the 30-40 line pattern repeated in every create_* function.

    Args:
        definition: Plugin definition dictionary
        options: Plugin options dictionary
        plugin_type: Type of plugin (e.g., "datasource", "llm")
        plugin_name: Name of the plugin
        parent_context: Optional parent context for inheritance
        require_security: Whether security_level is required
        require_determinism: Whether determinism_level is required

    Returns:
        Tuple of (security_level, determinism_level, provenance_sources)

    Raises:
        ConfigurationError: If required levels are missing or invalid
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

    # Coalesce security level
    try:
        if parent_sec_level is not None:
            security_level = coalesce_security_level(
                parent_sec_level, entry_sec_level, option_sec_level
            )
        else:
            security_level = coalesce_security_level(entry_sec_level, option_sec_level)
    except ValueError as exc:
        raise ConfigurationError(f"{plugin_type}:{plugin_name}: {exc}") from exc

    if security_level is None and require_security:
        raise ConfigurationError(
            f"{plugin_type}:{plugin_name}: security_level is required"
        )

    if security_level is not None:
        security_level = normalize_security_level(security_level)

    # Coalesce determinism level
    if entry_det_level is not None or option_det_level is not None:
        try:
            determinism_level = coalesce_determinism_level(
                entry_det_level, option_det_level
            )
        except ValueError as exc:
            raise ConfigurationError(f"{plugin_type}:{plugin_name}: {exc}") from exc
    else:
        # Inherit from parent or default
        determinism_level = parent_det_level if parent_det_level else "none"

    if determinism_level is None and require_determinism:
        raise ConfigurationError(
            f"{plugin_type}:{plugin_name}: determinism_level is required"
        )

    if determinism_level is not None:
        determinism_level = normalize_determinism_level(determinism_level)

    return security_level, determinism_level, sources


def create_plugin_context(
    plugin_name: str,
    plugin_kind: str,
    security_level: str,
    determinism_level: str,
    provenance: Iterable[str],
    *,
    parent_context: PluginContext | None = None,
) -> PluginContext:
    """
    Create or derive a plugin context consistently.

    Args:
        plugin_name: Name of the plugin
        plugin_kind: Kind of plugin (e.g., "datasource", "llm")
        security_level: Normalized security level
        determinism_level: Normalized determinism level
        provenance: Provenance source identifiers
        parent_context: Optional parent context to derive from

    Returns:
        New or derived PluginContext
    """
    provenance_tuple = tuple(provenance) if provenance else (f"{plugin_kind}:{plugin_name}.resolved",)

    if parent_context:
        return parent_context.derive(
            plugin_name=plugin_name,
            plugin_kind=plugin_kind,
            security_level=security_level,
            determinism_level=determinism_level,
            provenance=provenance_tuple,
        )

    return PluginContext(
        plugin_name=plugin_name,
        plugin_kind=plugin_kind,
        security_level=security_level,
        determinism_level=determinism_level,
        provenance=provenance_tuple,
    )


def prepare_plugin_payload(
    options: Dict[str, Any],
    *,
    strip_security: bool = True,
    strip_determinism: bool = True,
) -> Dict[str, Any]:
    """
    Prepare plugin options by removing framework-level keys.

    Args:
        options: Original plugin options
        strip_security: Remove security_level from options
        strip_determinism: Remove determinism_level from options

    Returns:
        Copy of options with framework keys removed
    """
    payload = dict(options)
    if strip_security:
        payload.pop("security_level", None)
    if strip_determinism:
        payload.pop("determinism_level", None)
    return payload
```

**Test Coverage:**
```python
# tests/test_registry_context_utils.py

def test_extract_security_levels_from_options():
    """Extract levels from options dictionary."""

def test_extract_security_levels_from_definition():
    """Extract levels from definition dictionary."""

def test_extract_security_levels_with_parent_context():
    """Inherit levels from parent context."""

def test_extract_security_levels_missing_required():
    """Raise error when required levels missing."""

def test_extract_security_levels_provenance_tracking():
    """Build correct provenance source list."""

def test_create_plugin_context_new():
    """Create new context without parent."""

def test_create_plugin_context_derived():
    """Derive context from parent."""

def test_prepare_plugin_payload():
    """Strip framework keys from options."""
```

**Deliverables:**
- [ ] Context utility functions implemented
- [ ] Full docstrings with examples
- [ ] Type hints complete
- [ ] Unit tests (>95% coverage)

**Estimated Time:** 8 hours

---

#### 1.4 Implement Common Schemas
**File:** `src/elspeth/core/registry/schemas.py`

**Design:**

```python
"""Common JSON schemas for plugin validation."""

from typing import Any, Dict, Mapping

# Standard enums
ON_ERROR_ENUM = {"type": "string", "enum": ["abort", "skip"]}

# Security and determinism schemas
SECURITY_LEVEL_SCHEMA = {"type": "string"}
DETERMINISM_LEVEL_SCHEMA = {"type": "string"}

# Artifact descriptor schema (used by sinks)
ARTIFACT_DESCRIPTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string"},
        "schema_id": {"type": "string"},
        "persist": {"type": "boolean"},
        "alias": {"type": "string"},
        "security_level": {"type": "string"},
        "determinism_level": {"type": "string"},
    },
    "required": ["name", "type"],
    "additionalProperties": False,
}

# Artifacts section schema (produces/consumes)
ARTIFACTS_SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "produces": {
            "type": "array",
            "items": ARTIFACT_DESCRIPTOR_SCHEMA,
        },
        "consumes": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {
                            "token": {"type": "string"},
                            "mode": {"type": "string", "enum": ["single", "all"]},
                        },
                        "required": ["token"],
                        "additionalProperties": False,
                    },
                ]
            },
        },
    },
    "additionalProperties": False,
}


def with_security_properties(
    schema: Dict[str, Any],
    *,
    require_security: bool = False,
    require_determinism: bool = False,
) -> Dict[str, Any]:
    """
    Add standard security and determinism properties to a schema.

    Args:
        schema: Base schema dictionary
        require_security: Add security_level to required fields
        require_determinism: Add determinism_level to required fields

    Returns:
        Schema with security properties added
    """
    result = dict(schema)
    properties = result.setdefault("properties", {})
    properties["security_level"] = SECURITY_LEVEL_SCHEMA
    properties["determinism_level"] = DETERMINISM_LEVEL_SCHEMA

    if require_security or require_determinism:
        required = result.setdefault("required", [])
        if require_security and "security_level" not in required:
            required.append("security_level")
        if require_determinism and "determinism_level" not in required:
            required.append("determinism_level")

    return result


def with_artifact_properties(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add artifact section properties to a schema.

    Args:
        schema: Base schema dictionary

    Returns:
        Schema with artifacts property added
    """
    result = dict(schema)
    properties = result.setdefault("properties", {})
    properties["artifacts"] = ARTIFACTS_SECTION_SCHEMA
    return result


def with_error_handling(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add on_error property to a schema.

    Args:
        schema: Base schema dictionary

    Returns:
        Schema with on_error property added
    """
    result = dict(schema)
    properties = result.setdefault("properties", {})
    properties["on_error"] = ON_ERROR_ENUM
    return result
```

**Test Coverage:**
```python
# tests/test_registry_schemas.py

def test_with_security_properties():
    """Add security properties to schema."""

def test_with_security_properties_required():
    """Add security properties as required fields."""

def test_with_artifact_properties():
    """Add artifact section to schema."""

def test_with_error_handling():
    """Add on_error enum to schema."""
```

**Deliverables:**
- [ ] Common schemas defined
- [ ] Schema builder functions implemented
- [ ] Unit tests

**Estimated Time:** 4 hours

---

#### 1.5 Implement Base Registry Class
**File:** `src/elspeth/core/registry/base.py` (continued)

**Design:**

```python
class BasePluginRegistry(Generic[T]):
    """
    Base class for plugin registries.

    Provides common functionality for registering, validating, and creating
    plugins with consistent security context handling.

    Attributes:
        plugin_type: Human-readable plugin type name
        _plugins: Internal registry of factories
    """

    def __init__(self, plugin_type: str):
        self.plugin_type = plugin_type
        self._plugins: PluginFactoryMap[T] = {}

    def register(
        self,
        name: str,
        factory: Callable[[Dict[str, Any], PluginContext], T],
        *,
        schema: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Register a plugin factory.

        Args:
            name: Plugin name
            factory: Factory callable
            schema: Optional validation schema
        """
        self._plugins[name] = BasePluginFactory(
            create=factory,
            schema=schema,
            plugin_type=self.plugin_type,
        )

    def validate(self, name: str, options: Dict[str, Any] | None) -> None:
        """
        Validate plugin options without instantiation.

        Args:
            name: Plugin name
            options: Plugin options

        Raises:
            ValueError: If plugin not found
            ConfigurationError: If validation fails
        """
        factory = self._get_factory(name)
        payload = dict(options or {})

        # Security validation happens at create time
        factory.validate(payload, context=f"{self.plugin_type}:{name}")

    def create(
        self,
        name: str,
        options: Dict[str, Any],
        *,
        provenance: Iterable[str] | None = None,
        parent_context: PluginContext | None = None,
        require_security: bool = True,
        require_determinism: bool = True,
    ) -> T:
        """
        Create a plugin instance with full context handling.

        Args:
            name: Plugin name
            options: Plugin configuration options
            provenance: Optional provenance source identifiers
            parent_context: Optional parent context
            require_security: Whether security_level is required
            require_determinism: Whether determinism_level is required

        Returns:
            Instantiated plugin

        Raises:
            ValueError: If plugin not found
            ConfigurationError: If validation or creation fails
        """
        factory = self._get_factory(name)

        # Extract and normalize security levels
        security_level, determinism_level, sources = extract_security_levels(
            definition=options,
            options=options,
            plugin_type=self.plugin_type,
            plugin_name=name,
            parent_context=parent_context,
            require_security=require_security,
            require_determinism=require_determinism,
        )

        # Add provenance if provided
        if provenance:
            sources.extend(provenance)

        # Create plugin context
        context = create_plugin_context(
            plugin_name=name,
            plugin_kind=self.plugin_type,
            security_level=security_level,
            determinism_level=determinism_level,
            provenance=sources,
            parent_context=parent_context,
        )

        # Prepare payload (strip framework keys)
        payload = prepare_plugin_payload(options)

        # Instantiate plugin
        return factory.instantiate(
            payload,
            plugin_context=context,
            schema_context=f"{self.plugin_type}:{name}",
        )

    def _get_factory(self, name: str) -> BasePluginFactory[T]:
        """Get factory by name, raising ValueError if not found."""
        try:
            return self._plugins[name]
        except KeyError as exc:
            raise ValueError(
                f"Unknown {self.plugin_type} plugin '{name}'"
            ) from exc

    def list_plugins(self) -> list[str]:
        """Return list of registered plugin names."""
        return sorted(self._plugins.keys())
```

**Test Coverage:**
```python
# tests/test_registry_base.py (continued)

def test_base_registry_register():
    """Register a plugin factory."""

def test_base_registry_validate():
    """Validate plugin options."""

def test_base_registry_create():
    """Create plugin with context."""

def test_base_registry_create_unknown_plugin():
    """Raise error for unknown plugin."""

def test_base_registry_list_plugins():
    """List registered plugin names."""
```

**Deliverables:**
- [ ] `BasePluginRegistry` implemented
- [ ] Full docstrings
- [ ] Type hints complete
- [ ] Unit tests (>90% coverage)

**Estimated Time:** 6 hours

---

#### 1.6 Create Public API
**File:** `src/elspeth/core/registry/__init__.py`

```python
"""
Unified plugin registry infrastructure.

This module provides base classes and utilities for creating consistent
plugin registries across the Elspeth framework.
"""

from .base import BasePluginFactory, BasePluginRegistry, PluginFactoryMap
from .context_utils import (
    create_plugin_context,
    extract_security_levels,
    prepare_plugin_payload,
)
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
```

**Deliverables:**
- [ ] Public API defined
- [ ] Module docstring
- [ ] `__all__` exports

**Estimated Time:** 1 hour

---

### Phase 1 Summary

**Total Estimated Time:** 29 hours (~4 days)

**Deliverables:**
- ✅ Complete base registry framework
- ✅ 100% backward compatible (no breaking changes)
- ✅ >90% test coverage on all new code
- ✅ Full documentation

**Testing Checklist:**
- [ ] All unit tests pass
- [ ] Test coverage >90%
- [ ] Existing tests still pass
- [ ] No import errors

**Review Gate:**
- [ ] Code review by 2+ team members
- [ ] Security review of context handling
- [ ] Performance benchmarks (should be identical to current)

---

## Phase 2: Migration (Days 6-15)

### Strategy
Migrate each registry one at a time, maintaining backward compatibility at each step.

### Migration Order (by complexity, simplest first)

1. **Utilities Registry** (simplest, lowest risk)
2. **Controls Registry** (rate limiters, cost trackers)
3. **LLM Middleware Registry**
4. **Experiment Plugins Registry** (most complex)
5. **Main Registry** (datasources, LLMs, sinks - do last as most critical)

---

### 2.1 Migrate Utilities Registry
**Target:** `src/elspeth/core/utilities/plugin_registry.py`
**Estimated Time:** 4 hours

**Current:** 156 lines, custom `_PluginFactory`, manual context handling

**Steps:**

1. **Import new base classes:**
```python
from elspeth.core.registry import BasePluginRegistry
```

2. **Replace `_PluginFactory` usage:**
```python
# OLD:
_utility_plugins: Dict[str, _PluginFactory] = {}

# NEW:
_utility_registry = BasePluginRegistry[Any]("utility")
```

3. **Update `register_utility_plugin`:**
```python
# OLD: Manual _PluginFactory creation
# NEW: Use registry.register()

def register_utility_plugin(name, factory, *, schema=None):
    _utility_registry.register(name, factory, schema=schema)
```

4. **Update `create_utility_plugin`:**
```python
# OLD: 50+ lines of manual context handling
# NEW: Use registry.create()

def create_utility_plugin(definition, *, parent_context=None, provenance=None):
    if not definition:
        raise ValueError("Utility plugin definition cannot be empty")

    name = definition.get("name")
    if not name:
        raise ConfigurationError("utility plugin definition requires 'name'")

    options = dict(definition.get("options", {}) or {})

    return _utility_registry.create(
        name=name,
        options=options,
        provenance=provenance,
        parent_context=parent_context,
        require_security=False,  # Utilities inherit from parent
        require_determinism=False,
    )
```

5. **Keep backward compatibility:**
```python
# Maintain existing function signature and behavior
def create_named_utility(...):
    # Keep as-is, calls create_utility_plugin internally
```

**Testing:**
- [ ] All existing utility plugin tests pass
- [ ] No behavior changes
- [ ] Coverage maintained

---

### 2.2 Migrate Controls Registry
**Target:** `src/elspeth/core/controls/registry.py`
**Estimated Time:** 6 hours

**Current:** 300 lines, two registries (rate limiters + cost trackers)

**Approach:** Create two `BasePluginRegistry` instances

```python
from elspeth.core.registry import BasePluginRegistry

_rate_limiter_registry = BasePluginRegistry[RateLimiter]("rate_limiter")
_cost_tracker_registry = BasePluginRegistry[CostTracker]("cost_tracker")

# Populate with existing plugins
_rate_limiter_registry.register("noop", lambda opts, ctx: NoopRateLimiter())
_rate_limiter_registry.register("fixed_window", ...)
# etc.
```

**Special Handling:**
- Keep backward-compatible `register_*` functions
- Maintain inspection logic for single-arg vs two-arg factories

**Testing:**
- [ ] Rate limiter creation works
- [ ] Cost tracker creation works
- [ ] Backward compatibility maintained

---

### 2.3 Migrate LLM Middleware Registry
**Target:** `src/elspeth/core/llm/registry.py`
**Estimated Time:** 5 hours

**Current:** 141 lines, simpler pattern

**Steps:**
1. Replace `_Factory` with `BasePluginRegistry`
2. Update `create_middleware` to use registry
3. Keep `create_middlewares` list helper

**Testing:**
- [ ] Middleware plugins load correctly
- [ ] Suite-level middleware hooks work
- [ ] Security context propagates correctly

---

### 2.4 Migrate Experiment Plugins Registry
**Target:** `src/elspeth/core/experiments/plugin_registry.py`
**Estimated Time:** 8 hours

**Current:** 603 lines, 5 plugin types (row, aggregation, baseline, validation, early-stop)

**Challenge:** Multiple plugin types in one file

**Approach:** Create 5 separate registry instances

```python
from elspeth.core.registry import BasePluginRegistry

_row_registry = BasePluginRegistry[RowExperimentPlugin]("row_plugin")
_aggregation_registry = BasePluginRegistry[AggregationExperimentPlugin]("aggregation_plugin")
_baseline_registry = BasePluginRegistry[BaselineComparisonPlugin]("baseline_plugin")
_validation_registry = BasePluginRegistry[ValidationPlugin]("validation_plugin")
_early_stop_registry = BasePluginRegistry[EarlyStopPlugin]("early_stop_plugin")
```

**Simplification:**
- Each `create_*_plugin` function becomes ~10 lines (was 50+)
- Each `validate_*_plugin_definition` becomes ~5 lines
- Keep `normalize_early_stop_definitions` as-is (special logic)

**Testing:**
- [ ] All 5 plugin types work
- [ ] Experiment runner integration works
- [ ] Baseline comparisons work

---

### 2.5 Migrate Main Registry
**Target:** `src/elspeth/core/registries/__init__.py`
**Estimated Time:** 10 hours (most critical, test thoroughly)

**Current:** 887 lines, handles datasources, LLMs, and sinks

**Challenge:**
- Most complex registry
- Most widely used
- Backward compatibility critical

**Approach:**

```python
from elspeth.core.registry import BasePluginRegistry

class PluginRegistry:
    """Central registry for datasource, LLM, and sink plugins."""

    def __init__(self):
        self._datasource_registry = BasePluginRegistry[DataSource]("datasource")
        self._llm_registry = BasePluginRegistry[LLMClientProtocol]("llm")
        self._sink_registry = BasePluginRegistry[ResultSink]("sink")

        # Register all plugins
        self._register_datasources()
        self._register_llms()
        self._register_sinks()

    def _register_datasources(self):
        """Register all datasource plugins."""
        self._datasource_registry.register(
            "azure_blob",
            lambda opts, ctx: BlobDataSource(**opts),
            schema={...}
        )
        # etc.

    def create_datasource(self, name, options, *, provenance=None, parent_context=None):
        """Delegate to datasource registry."""
        return self._datasource_registry.create(
            name=name,
            options=options,
            provenance=provenance,
            parent_context=parent_context,
        )

    # Similar for LLMs and sinks
```

**Special Cases:**
- `create_llm_from_definition`: Keep custom logic for nested definitions
- Schema definitions: Move to `schemas.py`, import here
- Validation methods: Delegate to registries

**Testing:**
- [ ] All datasource types work
- [ ] All LLM client types work
- [ ] All sink types work
- [ ] Nested LLM creation works
- [ ] Security level validation works
- [ ] Artifact pipeline integration works
- [ ] Full end-to-end suite runs successfully

---

### Phase 2 Summary

**Total Estimated Time:** 33 hours (~7 days with testing)

**Migration Checklist:**
- [ ] Utilities Registry migrated
- [ ] Controls Registry migrated
- [ ] LLM Middleware Registry migrated
- [ ] Experiment Plugins Registry migrated
- [ ] Main Registry migrated

**Testing Requirements:**
- [ ] All existing tests pass (100%)
- [ ] No behavior changes
- [ ] Performance benchmarks match baseline
- [ ] Full integration test suite passes
- [ ] Sample suite runs successfully

**Review Gate:**
- [ ] Code review for each registry
- [ ] Integration testing
- [ ] Performance validation
- [ ] Security review

---

## Phase 3: Cleanup & Optimization (Days 16-20)

### 3.1 Rename Datasource Folders
**Estimated Time:** 4 hours

**Goal:** Eliminate naming confusion

**Plan A (Recommended):**
```
src/elspeth/
├── adapters/               # Renamed from datasources/
│   └── blob_storage.py    # Merged blob utilities
└── plugins/
    └── datasources/        # Unchanged
```

**Steps:**
1. Create `src/elspeth/adapters/` directory
2. Move `datasources/blob_store.py` → `adapters/blob_storage.py`
3. Update imports across codebase
4. Update `__init__.py` files
5. Run full test suite
6. Update documentation

**Testing:**
- [ ] All blob datasource tests pass
- [ ] All imports resolve correctly
- [ ] No broken references

---

### 3.2 Remove Duplicate Code
**Estimated Time:** 2 hours

**Targets:**
- Delete old `_Factory` and `_PluginFactory` classes
- Remove duplicate context extraction logic
- Remove duplicate schema definitions

**Files to Clean:**
- `src/elspeth/core/llm/registry.py` - remove `_Factory`
- `src/elspeth/core/controls/registry.py` - remove `_Factory`
- `src/elspeth/core/experiments/plugin_registry.py` - remove `_PluginFactory`
- `src/elspeth/core/utilities/plugin_registry.py` - remove `_PluginFactory`

---

### 3.3 Update Documentation
**Estimated Time:** 6 hours

**Documents to Update:**
1. `CLAUDE.md` - Reflect new registry architecture
2. `docs/architecture/plugin-catalogue.md` - Update plugin registration examples
3. `docs/architecture/README.md` - Update architecture diagrams
4. `CONTRIBUTING.md` - Update plugin development guide

**New Documentation:**
1. `docs/architecture/registry-architecture.md` - Explain new base system
2. `docs/developer-guide/creating-plugins.md` - Step-by-step plugin creation

---

### 3.4 Performance Validation
**Estimated Time:** 4 hours

**Benchmarks:**
- [ ] Registry instantiation time (should be unchanged)
- [ ] Plugin creation time (should be unchanged or faster)
- [ ] Context creation overhead (should be minimal)
- [ ] Suite execution time (should be identical)

**Tool:** Create `tests/benchmark_registry.py`

```python
import time
from elspeth.core import registry

def benchmark_plugin_creation():
    """Measure plugin creation performance."""
    reg = registry.PluginRegistry()

    start = time.perf_counter()
    for _ in range(1000):
        plugin = reg.create_datasource("local_csv", {...})
    end = time.perf_counter()

    print(f"1000 creations: {end - start:.3f}s")
```

---

### Phase 3 Summary

**Total Estimated Time:** 16 hours (~3 days)

**Deliverables:**
- ✅ Cleaner folder structure
- ✅ ~900 lines of code removed
- ✅ Updated documentation
- ✅ Performance validated

---

## Phase 4: Validation & Release (Days 21+)

### 4.1 Integration Testing
**Estimated Time:** 8 hours

**Test Scenarios:**
1. Run complete sample suite
2. Test all plugin types
3. Test nested plugin creation
4. Test middleware chains
5. Test artifact pipeline
6. Test security level propagation
7. Test error handling
8. Test edge cases

**Checklist:**
- [ ] Sample suite runs without errors
- [ ] All output files generated correctly
- [ ] Visual analytics render
- [ ] Signed artifacts validate
- [ ] Repository sinks work
- [ ] Embeddings store works

---

### 4.2 Backward Compatibility Verification
**Estimated Time:** 4 hours

**Test existing configurations:**
- [ ] Sample suite configs work unchanged
- [ ] All prompt packs work
- [ ] Custom plugins still register
- [ ] No breaking API changes

---

### 4.3 Security Review
**Estimated Time:** 4 hours

**Review Areas:**
- [ ] Context propagation maintains security
- [ ] Security levels enforced correctly
- [ ] No privilege escalation possible
- [ ] Provenance tracking accurate
- [ ] Artifact pipeline security intact

---

### 4.4 Release Preparation
**Estimated Time:** 4 hours

**Tasks:**
1. Update CHANGELOG.md
2. Update version number
3. Create migration guide for custom plugins
4. Tag release
5. Update README with new features

---

## Rollback Plan

### If Issues Arise

**Phase 1 Rollback:**
- Delete `src/elspeth/core/registry/` directory
- No other changes needed (foundation only)

**Phase 2 Rollback (per registry):**
- Git revert the specific registry file
- Restore original file from backup
- Re-run tests

**Complete Rollback:**
```bash
git revert <commit-range>
git push origin main
```

**Risk Mitigation:**
- Commit each registry migration separately
- Tag each phase completion
- Keep backup branches
- Extensive testing before merging

---

## Success Metrics

### Quantitative
- [ ] Code reduction: ~900 lines removed
- [ ] Test coverage: Maintained or improved (>85%)
- [ ] Performance: No regression (±5% tolerance)
- [ ] Build time: No increase

### Qualitative
- [ ] Easier to add new plugin types
- [ ] Clearer architecture for new developers
- [ ] Consistent patterns across all registries
- [ ] Better error messages

---

## Timeline Summary

| Phase | Days | Deliverable |
|-------|------|-------------|
| Phase 1: Foundation | 1-5 | Base registry framework |
| Phase 2: Migration | 6-15 | All registries migrated |
| Phase 3: Cleanup | 16-20 | Folders renamed, docs updated |
| Phase 4: Validation | 21+ | Release ready |

**Total:** 20+ days (4 weeks with buffer)

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking changes | Medium | High | Extensive testing, backward compat layer |
| Performance regression | Low | Medium | Benchmarking, profiling |
| Security issues | Low | High | Security review, context validation tests |
| Migration bugs | Medium | Medium | Incremental migration, rollback plan |
| Timeline overrun | Medium | Low | Buffer time, prioritize critical features |

---

## Approval & Sign-off

- [ ] Technical Lead Review
- [ ] Security Team Review
- [ ] QA Testing Complete
- [ ] Documentation Review
- [ ] Stakeholder Approval

**Approved by:** ________________
**Date:** ________________

---

## Appendix A: Current Registry Comparison

| Registry | LOC | Factories | Plugin Types | Dependencies |
|----------|-----|-----------|--------------|--------------|
| Main | 887 | PluginFactory | 3 (datasource, llm, sink) | Multiple |
| Experiments | 603 | _PluginFactory | 5 (row, agg, baseline, validation, early-stop) | Core |
| Controls | 300 | _Factory | 2 (rate limiter, cost tracker) | Core |
| Middleware | 141 | _Factory | 1 (middleware) | Core |
| Utilities | 156 | _PluginFactory | 1 (utility) | Core |
| **Total** | **2,087** | | **12 plugin types** | |

---

## Appendix B: Example Migration Diff

**Before (Controls Registry):**
```python
class _Factory:
    def __init__(self, factory, schema=None):
        self.factory = factory
        self.schema = schema

    def validate(self, options, *, context):
        if self.schema is None:
            return
        errors = list(validate_schema(...))
        if errors:
            raise ConfigurationError(...)

    def create(self, options, *, plugin_context, schema_context):
        self.validate(...)
        return self.factory(options, plugin_context)

_rate_limiters: Dict[str, _Factory] = {}

def create_rate_limiter(definition, *, parent_context=None, provenance=None):
    # 60+ lines of manual context handling
    ...
```

**After:**
```python
from elspeth.core.registry import BasePluginRegistry

_rate_limiter_registry = BasePluginRegistry[RateLimiter]("rate_limiter")

def create_rate_limiter(definition, *, parent_context=None, provenance=None):
    # 10 lines using registry
    name = definition.get("plugin") or definition.get("name")
    options = definition.get("options", {}) or {}
    return _rate_limiter_registry.create(
        name=name,
        options=options,
        provenance=provenance,
        parent_context=parent_context,
    )
```

**Lines saved:** ~80 lines in this registry alone

---

**End of Plan**
