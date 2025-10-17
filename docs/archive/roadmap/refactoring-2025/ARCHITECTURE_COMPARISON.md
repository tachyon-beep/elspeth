# Registry Architecture: Before vs After

**Visual comparison of the registry consolidation refactoring**

---

## Current Architecture (Before)

### Registry Distribution

```
src/elspeth/core/
├── registry.py (887 LOC)                    # Datasources, LLMs, Sinks
│   ├── class PluginFactory                 # Custom factory (30 lines)
│   ├── class PluginRegistry               # Main registry
│   ├── create_datasource() (50 lines)     # Manual context handling
│   ├── create_llm() (50 lines)            # Manual context handling
│   ├── create_sink() (50 lines)           # Manual context handling
│   └── create_llm_from_definition() (70)  # Special nested logic
│
├── llm/
│   └── registry.py (141 LOC)              # LLM Middleware
│       ├── class _Factory                 # Duplicate factory (25 lines)
│       ├── create_middleware() (45 lines) # Manual context handling
│       └── validate_middleware_def() (20)
│
├── controls/
│   └── registry.py (300 LOC)              # Rate Limiters, Cost Trackers
│       ├── class _Factory                 # Duplicate factory (30 lines)
│       ├── create_rate_limiter() (50)     # Manual context handling
│       └── create_cost_tracker() (50)     # Manual context handling
│
├── experiments/
│   └── plugin_registry.py (603 LOC)       # Experiment Plugins
│       ├── class _PluginFactory           # Duplicate factory (25 lines)
│       ├── create_row_plugin() (50)       # Manual context handling
│       ├── create_aggregation_plugin() (50)
│       ├── create_baseline_plugin() (50)
│       ├── create_validation_plugin() (50)
│       └── create_early_stop_plugin() (50)
│
└── utilities/
    └── plugin_registry.py (156 LOC)       # Utility Plugins
        ├── class _PluginFactory           # Duplicate factory (25 lines)
        └── create_utility_plugin() (50)   # Manual context handling

TOTAL: 2,087 lines
DUPLICATION: ~900 lines (43%)
```

### Code Duplication Map

```
┌─────────────────────────────────────────────────────────────────┐
│ Repeated Pattern #1: Factory Class (~25-30 lines × 5 files)    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ class _Factory:                                                 │
│     def __init__(self, factory, schema=None):                  │
│         self.factory = factory                                 │
│         self.schema = schema                                   │
│                                                                 │
│     def validate(self, options, *, context):                   │
│         if self.schema is None: return                         │
│         errors = list(validate_schema(...))                    │
│         if errors:                                             │
│             raise ConfigurationError(...)                      │
│                                                                 │
│     def create(self, options, *, plugin_context, ...):         │
│         self.validate(...)                                     │
│         return self.factory(options, plugin_context)           │
│                                                                 │
│ REPEATED IN: 5 files (registry.py, llm/registry.py, etc.)     │
│ DUPLICATE LINES: ~150                                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Repeated Pattern #2: Context Extraction (~30-40 lines × 10+)   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ def create_xxx_plugin(definition, ...):                        │
│     # Extract security levels                                  │
│     definition_level = definition.get("security_level")        │
│     option_level = options.get("security_level")               │
│     sources: list[str] = []                                    │
│                                                                 │
│     if definition_level is not None:                           │
│         sources.append(f"{plugin_type}:...")                   │
│     if option_level is not None:                               │
│         sources.append(...)                                    │
│                                                                 │
│     # Coalesce and normalize                                   │
│     try:                                                        │
│         level = coalesce_security_level(...)                   │
│     except ValueError as exc:                                  │
│         raise ConfigurationError(...) from exc                 │
│                                                                 │
│     normalized = normalize_security_level(level)               │
│                                                                 │
│     # Create context                                           │
│     if parent_context:                                         │
│         context = parent_context.derive(...)                   │
│     else:                                                       │
│         context = PluginContext(...)                           │
│                                                                 │
│     # Apply context                                            │
│     plugin = factory.create(...)                               │
│     apply_plugin_context(plugin, context)                      │
│     return plugin                                              │
│                                                                 │
│ REPEATED IN: ~12 create_* functions across 5 files            │
│ DUPLICATE LINES: ~400                                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Repeated Pattern #3: Schema Definitions (~20-30 lines × 5+)    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ON_ERROR_ENUM = {"type": "string", "enum": ["abort", "skip"]} │
│                                                                 │
│ ARTIFACT_DESCRIPTOR_SCHEMA = {                                 │
│     "type": "object",                                          │
│     "properties": {...},                                       │
│     ...                                                         │
│ }                                                               │
│                                                                 │
│ ARTIFACTS_SECTION_SCHEMA = {...}                               │
│                                                                 │
│ REPEATED IN: Main registry, multiple sink schemas             │
│ DUPLICATE LINES: ~100                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Proposed Architecture (After)

### Unified Registry Framework

```
src/elspeth/core/
├── registry/                              # NEW: Base framework
│   ├── __init__.py                       # Public API exports
│   ├── base.py                           # Core abstractions
│   │   ├── class BasePluginFactory[T]   # Generic factory (30 lines)
│   │   └── class BasePluginRegistry[T]  # Generic registry (80 lines)
│   ├── context_utils.py                 # Shared context logic
│   │   ├── extract_security_levels()    # Consolidates 400 lines
│   │   ├── create_plugin_context()      # Consistent creation
│   │   └── prepare_plugin_payload()     # Strip framework keys
│   ├── schemas.py                        # Common schema definitions
│   │   ├── ON_ERROR_ENUM
│   │   ├── ARTIFACT_DESCRIPTOR_SCHEMA
│   │   ├── ARTIFACTS_SECTION_SCHEMA
│   │   ├── with_security_properties()
│   │   ├── with_artifact_properties()
│   │   └── with_error_handling()
│   └── validation.py                     # (Optional) Extra validation
│
├── registry.py (400 LOC, -487)          # Main registry - SIMPLIFIED
│   └── class PluginRegistry
│       ├── __init__()
│       │   ├── _datasource_registry = BasePluginRegistry[DataSource]("datasource")
│       │   ├── _llm_registry = BasePluginRegistry[LLMClientProtocol]("llm")
│       │   └── _sink_registry = BasePluginRegistry[ResultSink]("sink")
│       ├── _register_datasources()      # Registration only
│       ├── _register_llms()             # Registration only
│       ├── _register_sinks()            # Registration only
│       ├── create_datasource()          # Delegates to registry (10 lines)
│       ├── create_llm()                 # Delegates to registry (10 lines)
│       ├── create_sink()                # Delegates to registry (10 lines)
│       └── create_llm_from_definition() # Keep special logic (70 lines)
│
├── llm/
│   └── registry.py (80 LOC, -61)        # LLM Middleware - SIMPLIFIED
│       ├── _middleware_registry = BasePluginRegistry[LLMMiddleware]("llm_middleware")
│       ├── create_middleware()          # Delegates (10 lines)
│       └── validate_middleware_def()    # Delegates (5 lines)
│
├── controls/
│   └── registry.py (150 LOC, -150)      # Controls - SIMPLIFIED
│       ├── _rate_limiter_registry = BasePluginRegistry[RateLimiter]("rate_limiter")
│       ├── _cost_tracker_registry = BasePluginRegistry[CostTracker]("cost_tracker")
│       ├── create_rate_limiter()        # Delegates (15 lines)
│       └── create_cost_tracker()        # Delegates (15 lines)
│
├── experiments/
│   └── plugin_registry.py (350 LOC, -253) # Experiments - SIMPLIFIED
│       ├── _row_registry = BasePluginRegistry[RowExperimentPlugin]("row_plugin")
│       ├── _aggregation_registry = BasePluginRegistry[AggregationExperimentPlugin]("agg")
│       ├── _baseline_registry = BasePluginRegistry[BaselineComparisonPlugin]("baseline")
│       ├── _validation_registry = BasePluginRegistry[ValidationPlugin]("validation")
│       ├── _early_stop_registry = BasePluginRegistry[EarlyStopPlugin]("early_stop")
│       ├── create_row_plugin()          # Delegates (15 lines)
│       ├── create_aggregation_plugin()  # Delegates (15 lines)
│       ├── create_baseline_plugin()     # Delegates (15 lines)
│       ├── create_validation_plugin()   # Delegates (15 lines)
│       └── create_early_stop_plugin()   # Delegates (15 lines)
│
└── utilities/
    └── plugin_registry.py (80 LOC, -76) # Utilities - SIMPLIFIED
        ├── _utility_registry = BasePluginRegistry[Any]("utility")
        └── create_utility_plugin()      # Delegates (15 lines)

TOTAL: 1,270 lines (-817 lines, -39%)
BASE FRAMEWORK: 210 lines
DUPLICATION: ~0 lines (0%)
```

### Dependency Flow (After)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Application Layer                            │
│  (ExperimentRunner, SuiteRunner, Orchestrator)                  │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Specialized Registries                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Main       │  │ Experiments  │  │   Controls   │          │
│  │  Registry    │  │   Registry   │  │   Registry   │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│         └─────────────────┼─────────────────┘                   │
│                           │                                     │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Base Registry Framework                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │        BasePluginRegistry[T]                             │  │
│  │  - register(name, factory, schema)                       │  │
│  │  - validate(name, options)                               │  │
│  │  - create(name, options, context, ...)                   │  │
│  └────────────────────┬─────────────────────────────────────┘  │
│                       │                                         │
│  ┌────────────────────┼─────────────────────────────────────┐  │
│  │  BasePluginFactory[T]                                    │  │
│  │  - validate(options, context)                            │  │
│  │  - instantiate(options, plugin_context, schema_context)  │  │
│  └────────────────────┬─────────────────────────────────────┘  │
└───────────────────────┼─────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   Context    │ │   Schemas    │ │  Validation  │
│   Utils      │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
```

---

## Code Comparison Examples

### Example 1: Creating a Datasource

**Before:**
```python
# src/elspeth/core/registries/__init__.py (50+ lines)

def create_datasource(
    self,
    name: str,
    options: Dict[str, Any],
    *,
    provenance: Iterable[str] | None = None,
    parent_context: PluginContext | None = None,
) -> DataSource:
    try:
        factory = self._datasources[name]
    except KeyError as exc:
        raise ValueError(f"Unknown datasource plugin '{name}'") from exc

    payload = dict(options or {})
    validation_payload = dict(payload)
    validation_payload.pop("security_level", None)
    validation_payload.pop("determinism_level", None)
    factory.validate(validation_payload, context=f"datasource:{name}")

    # Extract and normalize security_level
    security_level = payload.get("security_level")
    if security_level is None:
        raise ConfigurationError(f"datasource:{name}: security_level is required")
    normalized_sec_level = normalize_security_level(security_level)
    payload["security_level"] = normalized_sec_level

    # Extract and normalize determinism_level
    determinism_level = payload.get("determinism_level")
    if determinism_level is None:
        raise ConfigurationError(f"datasource:{name}: determinism_level is required")
    normalized_det_level = normalize_determinism_level(determinism_level)
    payload["determinism_level"] = normalized_det_level

    sources = tuple(provenance or ("options.security_level", "options.determinism_level"))
    if parent_context:
        context = parent_context.derive(
            plugin_name=name,
            plugin_kind="datasource",
            security_level=normalized_sec_level,
            determinism_level=normalized_det_level,
            provenance=sources,
        )
    else:
        context = PluginContext(
            plugin_name=name,
            plugin_kind="datasource",
            security_level=normalized_sec_level,
            determinism_level=normalized_det_level,
            provenance=sources,
        )

    call_payload = dict(payload)
    call_payload.pop("security_level", None)
    call_payload.pop("determinism_level", None)
    plugin = factory.create(call_payload, context)
    apply_plugin_context(plugin, context)
    return plugin
```

**After:**
```python
# src/elspeth/core/registries/__init__.py (10 lines)

def create_datasource(
    self,
    name: str,
    options: Dict[str, Any],
    *,
    provenance: Iterable[str] | None = None,
    parent_context: PluginContext | None = None,
) -> DataSource:
    """Create a datasource plugin. Delegates to internal registry."""
    return self._datasource_registry.create(
        name=name,
        options=options,
        provenance=provenance,
        parent_context=parent_context,
    )
```

**Savings:** 40 lines per method × 12 methods = 480 lines total

---

### Example 2: Factory Pattern

**Before (Repeated 5 times):**
```python
# 5 different files, each with nearly identical code

class _Factory:
    def __init__(
        self,
        factory: Callable[[Dict[str, Any], PluginContext], Any],
        schema: Mapping[str, Any] | None = None,
    ):
        self.factory = factory
        self.schema = schema

    def validate(self, options: Dict[str, Any], *, context: str) -> None:
        if self.schema is None:
            return
        errors = list(validate_schema(options or {}, self.schema, context=context))
        if errors:
            raise ConfigurationError("\n".join(msg.format() for msg in errors))

    def create(
        self,
        options: Dict[str, Any],
        *,
        plugin_context: PluginContext,
        schema_context: str,
    ) -> Any:
        self.validate(options, context=schema_context)
        return self.factory(options, plugin_context)
```

**After (Once in base.py):**
```python
# src/elspeth/core/registry/base.py

@dataclass
class BasePluginFactory(Generic[T]):
    """Base factory for creating and validating plugin instances."""

    create: Callable[[Dict[str, Any], PluginContext], T]
    schema: Mapping[str, Any] | None = None
    plugin_type: str = "plugin"

    def validate(self, options: Dict[str, Any], *, context: str) -> None:
        """Validate options against the schema."""
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
        """Validate and create a plugin instance."""
        self.validate(options, context=schema_context)
        plugin = self.create(options, plugin_context)
        apply_plugin_context(plugin, context)
        return plugin
```

**All other files import and use it:**
```python
from elspeth.core.registry import BasePluginRegistry

_my_registry = BasePluginRegistry[MyPluginType]("my_plugin")
```

**Savings:** 25 lines × 5 files = 125 lines

---

## Metrics Comparison

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| **Total Registry LOC** | 2,087 | 1,270 | -817 (-39%) |
| **Duplicate Factory Classes** | 5 | 1 | -4 |
| **Duplicate Context Logic** | ~12 functions | 1 function | -11 |
| **Average create_* Function** | 50 lines | 10-15 lines | -35 lines |
| **Schema Definitions** | Scattered | Centralized | Unified |
| **Base Framework LOC** | 0 | 210 | +210 (new) |
| **Net Code Reduction** | | | -607 lines |

---

## Folder Structure Comparison

### Before
```
src/elspeth/
├── core/
│   ├── registry.py                 # 887 lines
│   ├── llm/
│   │   └── registry.py             # 141 lines
│   ├── controls/
│   │   └── registry.py             # 300 lines
│   ├── experiments/
│   │   └── plugin_registry.py      # 603 lines
│   └── utilities/
│       └── plugin_registry.py      # 156 lines
├── datasources/                    # CONFUSING NAME
│   └── blob_store.py
└── plugins/
    └── datasources/                # DUPLICATE NAME
        ├── blob.py
        ├── csv_blob.py
        └── csv_local.py
```

### After
```
src/elspeth/
├── core/
│   ├── registry/                   # NEW: Base framework
│   │   ├── __init__.py
│   │   ├── base.py                 # 110 lines
│   │   ├── context_utils.py        # 60 lines
│   │   └── schemas.py              # 40 lines
│   ├── registry.py                 # 400 lines (-487)
│   ├── llm/
│   │   └── registry.py             # 80 lines (-61)
│   ├── controls/
│   │   └── registry.py             # 150 lines (-150)
│   ├── experiments/
│   │   └── plugin_registry.py      # 350 lines (-253)
│   └── utilities/
│       └── plugin_registry.py      # 80 lines (-76)
├── adapters/                       # RENAMED FOR CLARITY
│   └── blob_storage.py
└── plugins/
    └── datasources/                # CLEAR PURPOSE
        ├── blob.py
        ├── csv_blob.py
        └── csv_local.py
```

---

## Benefits Summary

### Code Quality
✅ **-39% code duplication** removed
✅ **Single source of truth** for factory pattern
✅ **Consistent behavior** across all plugin types
✅ **Easier to maintain** and debug
✅ **Type-safe** with generics

### Developer Experience
✅ **Easier to add new plugin types** (just extend BasePluginRegistry)
✅ **Clearer architecture** for new developers
✅ **Better error messages** (standardized)
✅ **Reduced cognitive load** (one pattern to learn)
✅ **Clearer folder names** (no confusion)

### Testing
✅ **Centralized testing** of common behavior
✅ **Better coverage** through shared tests
✅ **Easier to verify** security context propagation
✅ **Consistent test patterns**

### Performance
✅ **No regression** (delegation is fast)
✅ **Potentially faster** (less code to execute)
✅ **Lower memory footprint** (shared code)

---

## Migration Risk Assessment

| Area | Risk Level | Mitigation |
|------|-----------|------------|
| Backward Compatibility | 🟡 Medium | Maintain all public APIs |
| Performance | 🟢 Low | Delegation adds minimal overhead |
| Security | 🟡 Medium | Extensive context propagation tests |
| Testing Burden | 🟡 Medium | Incremental migration, extensive testing |
| Timeline Overrun | 🟡 Medium | Buffer time, clear phases |

---

## Next Steps

1. ✅ Review this architecture comparison
2. ⬜ Approve refactoring plan
3. ⬜ Begin Phase 1: Foundation
4. ⬜ Validate with integration tests
5. ⬜ Complete migration phases 2-4

---

**Document Version:** 1.0
**Last Updated:** 2025-10-14
**Status:** Ready for Review
