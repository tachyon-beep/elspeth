# ADR 007 – Unified Registry Pattern

## Status

**DRAFT** (2025-10-26)

## Context

Elspeth supports multiple plugin types (datasources, LLM clients, sinks, middleware, experiment helpers), each requiring registration, schema validation, security level stamping, and type-safe instantiation. Prior to Phase 2 migration, each plugin type had custom registration logic, leading to code duplication, inconsistent validation, and difficult maintenance.

ADR-003 "Central Plugin Type Registry" proposed validation completeness requirements but did not specify the underlying registry architecture pattern. Phase 2 migration (historical/A002-complete-registry-migration.md) implemented a unified `BasePluginRegistry[T]` generic, but this fundamental architectural pattern remains undocumented.

**Problems with Pre-Phase-2 Approach**:

- **Code Duplication**: Each plugin type reimplemented registration, validation, schema checking
- **Inconsistent Security**: Security level stamping varied by plugin type
- **Type Safety Gaps**: No compile-time guarantees on plugin types
- **Difficult Extension**: Adding new plugin types required copying/modifying existing patterns
- **Testing Burden**: Each registry implementation needed separate test suites

**Need**: A single, type-safe, extensible pattern for all plugin registries that enforces consistent security, validation, and instantiation semantics.

## Decision

We will implement a **Unified Registry Pattern** based on `BasePluginRegistry[T]` generic base class that all plugin type registries inherit from.

### Core Design

#### 1. Generic Base Registry

All plugin registries inherit from `BasePluginRegistry[T]` where `T` is the plugin protocol type:

```python
from typing import Generic, TypeVar, Protocol
from abc import ABC, abstractmethod

T = TypeVar('T')  # Plugin protocol type

class BasePluginRegistry(Generic[T], ABC):
    """Generic base for type-safe plugin registration.

    Provides:
    - Schema validation via jsonschema
    - Security level stamping (_elspeth_security_level attribute)
    - Factory pattern for plugin instantiation
    - Type safety via Generic[T]
    """

    def __init__(self):
        self._plugins: dict[str, type[T]] = {}
        self._schemas: dict[str, dict] = {}

    def register(
        self,
        name: str,
        plugin_class: type[T],
        schema: dict | None = None,
        security_level: SecurityLevel | None = None,
    ) -> None:
        """Register plugin with validation and security stamping."""
        # Type checking (compile-time via mypy)
        if not isinstance(plugin_class, type):
            raise TypeError(f"Expected class, got {type(plugin_class)}")

        # Schema registration
        if schema:
            self._validate_schema(schema)
            self._schemas[name] = schema

        # Security level stamping (ADR-002 compliance)
        if security_level:
            plugin_class._elspeth_security_level = security_level

        # Store plugin
        self._plugins[name] = plugin_class

    def get(self, name: str) -> type[T]:
        """Retrieve registered plugin class (type-safe)."""
        if name not in self._plugins:
            raise KeyError(f"Plugin '{name}' not registered")
        return self._plugins[name]

    def instantiate(self, name: str, config: dict) -> T:
        """Factory: Instantiate plugin with config validation."""
        # Schema validation
        if name in self._schemas:
            jsonschema.validate(config, self._schemas[name])

        # Type-safe instantiation
        plugin_class = self.get(name)
        return plugin_class(**config)

    @abstractmethod
    def _validate_schema(self, schema: dict) -> None:
        """Subclass-specific schema validation rules."""
        pass
```

#### 2. Concrete Registry Implementations

Each plugin type has a concrete registry:

```python
# src/elspeth/core/registries/datasource.py
class DataSourceRegistry(BasePluginRegistry[DataSource]):
    """Registry for datasource plugins."""

    def _validate_schema(self, schema: dict) -> None:
        # Datasource-specific validation
        required = {"type", "properties"}
        if not required.issubset(schema.keys()):
            raise ValueError(f"Schema missing required keys: {required}")

# src/elspeth/core/registries/llm.py
class LLMClientRegistry(BasePluginRegistry[LLMClient]):
    """Registry for LLM client plugins."""

    def _validate_schema(self, schema: dict) -> None:
        # LLM-specific validation
        pass

# src/elspeth/core/registries/sink.py
class SinkRegistry(BasePluginRegistry[ResultSink]):
    """Registry for result sink plugins."""

    def _validate_schema(self, schema: dict) -> None:
        # Sink-specific validation
        pass
```

#### 3. Registration Pattern

Plugins register via decorator pattern (preferred) or direct registration:

**Decorator Pattern** (recommended):

```python
@datasource_registry.register(
    name="csv_local",
    schema=CSV_LOCAL_SCHEMA,
    security_level=SecurityLevel.UNOFFICIAL
)
class CsvLocalDataSource(BasePlugin, DataSource):
    """Local CSV file datasource."""
    pass
```

**Direct Registration** (programmatic):

```python
datasource_registry.register(
    name="csv_blob",
    plugin_class=CsvBlobDataSource,
    schema=CSV_BLOB_SCHEMA,
    security_level=SecurityLevel.OFFICIAL
)
```

#### 4. Type Safety Guarantees

Generic typing provides compile-time safety:

```python
# Type-safe retrieval
datasource_class: type[DataSource] = datasource_registry.get("csv_local")

# Type error (caught by mypy)
sink_class: type[ResultSink] = datasource_registry.get("csv_local")  # ❌ Type mismatch

# Type-safe instantiation
datasource: DataSource = datasource_registry.instantiate("csv_local", config)
```

### Registry Lifecycle

1. **Bootstrap**: Registries initialized at module import
2. **Registration**: Plugins register during module load (decorator pattern)
3. **Validation**: Schema validation at registration time (fail-fast)
4. **Instantiation**: Factory pattern creates instances with config validation
5. **Audit**: All registrations logged for compliance

### Security Integration (ADR-002, ADR-004)

Registry enforces security at multiple layers:

1. **Security Level Stamping**: `_elspeth_security_level` attribute set at registration
2. **BasePlugin Integration**: All registered plugins inherit from `BasePlugin` (ADR-004)
3. **Validation Completeness**: ADR-003 validation requirements enforced at registration
4. **Audit Logging**: Plugin registrations logged for security audit trail

## Consequences

### Benefits

1. **Type Safety**: Generic typing provides compile-time guarantees via mypy
2. **Consistency**: All plugin types use identical registration/validation pattern
3. **Security**: Automatic security level stamping, BasePlugin enforcement
4. **Extensibility**: New plugin types trivial to add (inherit from base, implement `_validate_schema`)
5. **Testability**: Single test suite for base registry, minimal per-registry testing
6. **DRY Principle**: Zero code duplication across plugin types
7. **ADR Compliance**: Enforces ADR-002 (security levels), ADR-003 (validation), ADR-004 (BasePlugin)

### Limitations / Trade-offs

1. **Learning Curve**: Developers must understand generic typing (`BasePluginRegistry[T]`)
   - *Mitigation*: Documentation with examples, type annotations guide developers

2. **Registry Proliferation**: One registry file per plugin type (5+ files)
   - *Mitigation*: Clear directory structure (`core/registries/`), consistent naming

3. **Rigid Pattern**: Cannot register plugins without going through registry
   - *Mitigation*: This is intentional (security enforcement), direct instantiation forbidden

4. **Schema Coupling**: Plugin schema must be defined at registration time
   - *Mitigation*: Lazy schema loading supported via callable schema factory

### Migration Path

Phase 2 migration (historical/A002) completed registry consolidation:

- ✅ All plugin types migrated to `BasePluginRegistry[T]`
- ✅ Security level stamping consistent
- ✅ Schema validation unified
- ⚠️ **This ADR formalizes the implemented pattern**

### Implementation References

- `src/elspeth/core/registries/base.py` – `BasePluginRegistry[T]` generic
- `src/elspeth/core/registries/datasource.py` – DataSourceRegistry
- `src/elspeth/core/registries/llm.py` – LLMClientRegistry
- `src/elspeth/core/registries/sink.py` – SinkRegistry
- `src/elspeth/core/registries/middleware.py` – MiddlewareRegistry

### Related ADRs

- **ADR-002**: Multi-Level Security – Registry enforces security level stamping
- **ADR-003**: Plugin Type Registry – This ADR defines the registry architecture
- **ADR-004**: Mandatory BasePlugin – Registry enforces BasePlugin inheritance
- **Historical/A002**: Complete Registry Migration – Implementation completion

## Open Questions

1. **Dynamic Plugin Loading**: Should registries support runtime plugin discovery (entry points)?
   - Current: Explicit registration only
   - Alternative: Use Python entry points for third-party plugins
   - Decision deferred to post-1.0

2. **Registry Scope**: Global singleton vs dependency injection?
   - Current: Module-level singletons
   - Alternative: Dependency injection for testability
   - Decision: Singleton pattern sufficient for current needs

3. **Plugin Versioning**: Should registries support multiple plugin versions?
   - Current: Single version per plugin name
   - Alternative: Versioned plugin names (`csv_local_v2`)
   - Decision: Defer to post-1.0 (YAGNI)

---

**Document Status**: DRAFT – Requires review and acceptance before implementation guidance
**Next Steps**: Review with team, update plugin authoring guide with registry pattern examples
