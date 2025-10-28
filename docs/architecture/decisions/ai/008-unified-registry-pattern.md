# ADR-008 – Unified Registry Pattern (LITE)

## Status

**IMPLEMENTED** (2025-10-26)
**Enhanced**: Sprint 2 - CentralPluginRegistry (2025-10-27)

## Context

Elspeth supports multiple plugin types (datasources, LLM clients, sinks, middleware, experiment helpers). Pre-Phase-2, each had custom registration logic → code duplication, inconsistent security, type safety gaps.

**Problems**:
- Code duplication (each reimplemented registration/validation)
- Inconsistent security level stamping
- No compile-time type guarantees
- Difficult extension (copy/modify pattern)
- Each registry needs separate test suites

## Decision

Implement **Unified Registry Pattern** via `BasePluginRegistry[T]` generic base that all registries inherit.

### Generic Base Registry

```python
from typing import Generic, TypeVar, Protocol

T = TypeVar('T')  # Plugin protocol type

class BasePluginRegistry(Generic[T], ABC):
    """Generic base for type-safe plugin registration.

    Provides:
    - Schema validation via jsonschema
    - Security level stamping (_elspeth_security_level attribute)
    - Factory pattern for instantiation
    - Type safety via Generic[T]
    - Security policy field enforcement (ADR-002-B)
    """

    # ADR-002-B: Forbidden configuration fields (immutable security policy)
    FORBIDDEN_CONFIG_FIELDS = frozenset({
        "security_level",
        "allow_downgrade",
        "max_operating_level",
    })

    def __init__(self):
        self._plugins: dict[str, type[T]] = {}
        self._schemas: dict[str, dict] = {}

    def register(
        self,
        name: str,
        plugin_class: type[T],
        schema: dict | None = None,
        security_level: SecurityLevel | None = None,
    ):
        """Register plugin with validation and security stamping."""
        # Schema registration with security policy validation (ADR-002-B)
        if schema:
            self._validate_schema_security(name, schema)  # ← ADR-002-B
            self._validate_schema(schema)
            self._schemas[name] = schema

        # Security level stamping (ADR-002)
        if security_level:
            plugin_class._elspeth_security_level = security_level

        self._plugins[name] = plugin_class

    def _validate_schema_security(self, plugin_name: str, schema: dict):
        """Verify schema doesn't expose security policy fields (ADR-002-B)."""
        properties = schema.get("properties", {})
        exposed_fields = self.FORBIDDEN_CONFIG_FIELDS & set(properties.keys())

        if exposed_fields:
            raise RegistrationError(
                f"Plugin '{plugin_name}' schema exposes forbidden fields: "
                f"{exposed_fields}. Security policy is author-owned, immutable (ADR-002-B). "
                f"Remove from schema - declare via BasePlugin.__init__(security_level=..., allow_downgrade=...)."
            )

    def instantiate(self, name: str, config: dict) -> T:
        """Factory: Instantiate plugin with config validation."""
        # Schema validation
        if name in self._schemas:
            jsonschema.validate(config, self._schemas[name])

        # Type-safe instantiation
        plugin_class = self.get(name)
        return plugin_class(**config)

    @abstractmethod
    def _validate_schema(self, schema: dict):
        """Subclass-specific validation rules."""
        pass
```

### Concrete Registries

```python
# src/elspeth/core/registries/datasource.py
class DataSourceRegistry(BasePluginRegistry[DataSource]):
    """Registry for datasource plugins."""

    def _validate_schema(self, schema: dict):
        required = {"type", "properties"}
        if not required.issubset(schema.keys()):
            raise ValueError(f"Schema missing required keys: {required}")

# src/elspeth/core/registries/llm.py
class LLMClientRegistry(BasePluginRegistry[LLMClient]):
    """Registry for LLM client plugins."""

# src/elspeth/core/registries/sink.py
class SinkRegistry(BasePluginRegistry[ResultSink]):
    """Registry for result sink plugins."""
```

### Registration Patterns

**Decorator** (recommended):
```python
@datasource_registry.register(
    name="csv_local",
    schema=CSV_LOCAL_SCHEMA,
    security_level=SecurityLevel.UNOFFICIAL
)
class CsvLocalDataSource(BasePlugin, DataSource):
    def __init__(self, *, path: str, allow_downgrade: bool):
        super().__init__(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=allow_downgrade)
```

**Direct**:
```python
datasource_registry.register(
    name="csv_blob",
    plugin_class=CsvBlobDataSource,
    schema=CSV_BLOB_SCHEMA,
    security_level=SecurityLevel.OFFICIAL
)
```

### Type Safety

```python
# Type-safe retrieval
datasource_class: type[DataSource] = datasource_registry.get("csv_local")

# Type error (caught by mypy)
sink_class: type[ResultSink] = datasource_registry.get("csv_local")  # ❌ Mismatch

# Type-safe instantiation
datasource: DataSource = datasource_registry.instantiate("csv_local", config)
```

## Security Integration (ADR-002, ADR-004)

1. **Security level stamping**: `_elspeth_security_level` attribute at registration
2. **BasePlugin enforcement**: All plugins inherit BasePlugin (ADR-004)
3. **Validation completeness**: ADR-003 requirements enforced at registration
4. **Audit logging**: Plugin registrations logged for compliance

## Consequences

### Benefits
- **Type safety** - Generic typing → compile-time guarantees (mypy)
- **Consistency** - All plugin types use identical pattern
- **Security** - Automatic level stamping, BasePlugin enforcement
- **Extensibility** - New types trivial (inherit, implement `_validate_schema`)
- **Testability** - Single test suite for base, minimal per-registry
- **DRY** - Zero code duplication

### Limitations
- **Learning curve** - Developers need generic typing knowledge
- **Registry proliferation** - One file per plugin type (5+ files)
- **Rigid pattern** - Cannot bypass registry (intentional for security)

### Migration

**Phase 2 (ADR-002-B)** - ✅ COMPLETE:
- ✅ All plugin types migrated to `BasePluginRegistry[T]`
- ✅ Security level stamping consistent
- ✅ Pattern fully implemented across codebase

**Sprint 2 Enhancement (ADR-003)** - ✅ COMPLETE:
- ✅ `CentralPluginRegistry` facade added
- ✅ Unified access via `central_registry.get_registry()`
- ✅ Automatic plugin discovery with validation
- ✅ Single enforcement point for all plugin operations

### Sprint 2 Enhancement: CentralPluginRegistry

**Component**: `src/elspeth/core/registry/central.py`

**Purpose**: Provide unified facade over all `BasePluginRegistry[T]` instances

**Architecture**:
```python
class CentralPluginRegistry:
    def __init__(self):
        self._registries: dict[str, BasePluginRegistry[Any]] = {
            "datasource": datasource_registry,
            "llm": llm_registry,
            "sink": sink_registry,
            # ... 9 more types
        }

        # SECURITY: Auto-discover + validate on init
        auto_discover_internal_plugins()
        validate_discovery(self._registries)

    def get_registry(self, plugin_type: str) -> BasePluginRegistry[Any]:
        """Get type-specific registry through central access point."""
        return self._registries[plugin_type]
```

**Benefits**:
- Single import: `from elspeth.core.registry import central_registry`
- Unified access pattern across all plugin types
- Automatic discovery + validation (security)
- Easy testing (mock one facade vs 12 registries)

**Status**: ✅ IMPLEMENTED
- 12 registry types consolidated
- 1480 tests passing
- Zero regressions
- Documentation complete

## Related

ADR-002 (MLS), ADR-003 (Central Plugin Registry), ADR-004 (BasePlugin)

---
**Last Updated**: 2025-10-27 (Sprint 2 Enhancement Complete)
