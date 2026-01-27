# ELSPETH Plugin System Architecture Analysis

**Date:** 2026-01-27
**Analyst:** Claude (Codebase Explorer Agent)
**Scope:** `src/elspeth/plugins/` - Base classes, protocols, manager, discovery, results

---

## Executive Summary

The plugin system is architecturally sound with clear separation between protocols (contracts) and base classes (conveniences). However, several non-obvious issues exist:

1. **Protocol/Base Class Duality Creates Two Parallel Hierarchies** - Maintenance burden
2. **Coalesce Has No Base Class** - Unlike all other plugin types
3. **Validation Subsystem is Hardcoded** - Extension requires source modification
4. **LLM Transforms Have Dual Execution Models** - `process()` vs `accept()` split
5. **Gate Discovery is Disabled** - Despite having BaseGate and GateProtocol
6. **Lifecycle Hook Ordering Undefined** - No documented execution order guarantees

---

## 1. Design Issues

### 1.1 Protocol/Base Class Duality Creates Maintenance Burden

**Location:** `base.py`, `protocols.py`

The system defines parallel hierarchies:
- `SourceProtocol` / `BaseSource`
- `TransformProtocol` / `BaseTransform`
- `GateProtocol` / `BaseGate`
- `SinkProtocol` / `BaseSink`
- `CoalesceProtocol` / **(no base class)**

**Issue:** Every attribute change must be synchronized across both files. For example:

```python
# protocols.py:160-171
class TransformProtocol(Protocol):
    is_batch_aware: bool
    creates_tokens: bool
    _on_error: str | None

# base.py:52-67
class BaseTransform(ABC):
    is_batch_aware: bool = False
    creates_tokens: bool = False
    _on_error: str | None = None
```

If someone adds a new attribute to the protocol but forgets the base class (or vice versa), type checking passes but runtime behavior diverges.

**Evidence:** The `_on_error` attribute appears in both files but with slightly different documentation, suggesting drift over time.

**Recommendation:** Consider generating one from the other, or using a shared definition.

---

### 1.2 CoalesceProtocol Has No BaseCoalesce Class

**Location:** `protocols.py:318-386`, `base.py` (absent)

Every plugin type except Coalesce has a base class:
- `BaseSource`
- `BaseTransform`
- `BaseGate`
- `BaseSink`
- **No `BaseCoalesce`**

The CoalesceProtocol exists in `protocols.py:318`:
```python
@runtime_checkable
class CoalesceProtocol(Protocol):
    name: str
    policy: CoalescePolicy
    quorum_threshold: int | None
    expected_branches: list[str]
    output_schema: type["PluginSchema"]
    node_id: str | None
```

But there is no corresponding base class in `base.py`. The docstring examples show manual implementations:
```python
# protocols.py:330-344
class SimpleCoalesce:
    name = "merge"
    policy = CoalescePolicy.REQUIRE_ALL
    quorum_threshold = None
    # ... manually implements everything
```

**Impact:** Plugin authors implementing coalesce transforms must manually implement all attributes and lifecycle hooks, unlike other plugin types.

---

### 1.3 Gate Discovery is Disabled Despite Infrastructure Existing

**Location:** `discovery.py:159-163`, `manager.py:145-154`

Gates have full infrastructure (BaseGate, GateProtocol, hook spec) but discovery is explicitly disabled:

```python
# discovery.py:159-163
PLUGIN_SCAN_CONFIG: dict[str, list[str]] = {
    "sources": ["sources", "azure"],
    "transforms": ["transforms", "transforms/azure", "llm"],
    "sinks": ["sinks", "azure"],
    # NOTE: No "gates" entry
}
```

```python
# manager.py:145-154
def register_builtin_plugins(self) -> None:
    # NOTE: Gates are NOT registered here. Per docs/contracts/plugin-protocol.md,
    # gates are config-driven system operations handled by the engine, not plugins.
```

**Contradiction:** The hook spec in `hookspecs.py:64-70` defines `elspeth_get_gates()`, and `_refresh_caches()` in `manager.py:192-197` processes gates. This infrastructure is unused.

**Current state:** Gates exist as an intermediate design - protocol and base class exist, but actual gate plugins would need manual registration since discovery is disabled.

---

### 1.4 LLM Transforms Have Incompatible Execution Models

**Location:** `llm/azure.py`, `llm/azure_multi_query.py`

The LLM transforms using `BatchTransformMixin` have two incompatible execution models:

```python
# llm/azure.py:228-243
def process(
    self,
    row: dict[str, Any],
    ctx: PluginContext,
) -> TransformResult:
    """Not supported - use accept() for row-level pipelining.
    ...
    Raises:
        NotImplementedError: Always, directing callers to use accept()
    """
    raise NotImplementedError(...)
```

These transforms implement `BaseTransform` which requires `process()`, but then raise `NotImplementedError` and require `accept()` instead.

**Problems:**
1. Violates Liskov Substitution Principle - cannot use these transforms polymorphically via `TransformProtocol`
2. Engine must special-case these transforms or have separate execution paths
3. The interface contract is violated at runtime, not compile time

**Deeper issue:** `BatchTransformMixin` fundamentally changes the contract from pull (engine calls `process()`) to push (plugin calls `output.emit()`). This is a different execution model, not just an optimization.

---

## 2. Functionality Gaps

### 2.1 Validation Subsystem Requires Source Modification to Extend

**Location:** `validation.py:85-109`, `validation.py:239-299`, `validation.py:301-308`, `validation.py:310-334`

Each plugin type has a hardcoded lookup table:

```python
# validation.py:85-109
def _get_source_config_model(self, source_type: str) -> type["PluginConfig"] | None:
    if source_type == "csv":
        from elspeth.plugins.sources.csv_source import CSVSourceConfig
        return CSVSourceConfig
    elif source_type == "json":
        from elspeth.plugins.sources.json_source import JSONSourceConfig
        return JSONSourceConfig
    # ... hardcoded for each type
    else:
        raise ValueError(f"Unknown source type: {source_type}")
```

**Impact:** Adding a new plugin requires modifying `validation.py` in addition to creating the plugin. This violates the Open-Closed Principle.

**Note:** Gate validation is completely unimplemented:
```python
# validation.py:301-308
def _get_gate_config_model(self, gate_type: str) -> type["PluginConfig"]:
    # No gate plugins exist yet in codebase
    raise ValueError(f"Unknown gate type: {gate_type}")
```

---

### 2.2 No Plugin Metadata Discovery for Config Classes

The discovery system finds plugin classes but not their config classes. `PluginConfigValidator` must hardcode the mapping. A cleaner design would have plugins declare their config class:

```python
# Current: must be hardcoded in validation.py
class CSVSource(BaseSource):
    name = "csv"
    # No reference to CSVSourceConfig

# Better: self-describing
class CSVSource(BaseSource):
    name = "csv"
    config_class = CSVSourceConfig  # Plugin declares its config
```

---

### 2.3 Lifecycle Hook Ordering is Undefined

**Location:** `base.py:102-117`, `protocols.py:100-108`

The hooks `on_start()` and `on_complete()` exist on all plugin types, but their execution order is not documented:

**Questions without answers:**
1. Does source `on_start()` run before or after transform `on_start()`?
2. In a DAG with forks, what order do parallel branch transforms get `on_start()`?
3. Does `on_complete()` run in reverse order of `on_start()`?
4. What happens if `on_start()` fails - do already-started plugins get `on_complete()`?

The engine presumably implements this, but the plugin contract doesn't specify it.

---

### 2.4 `close()` vs `on_complete()` Semantics Unclear

**Location:** `base.py:94-100`, `base.py:112-117`

Two cleanup hooks exist with similar purposes:

```python
def close(self) -> None:  # noqa: B027 - optional override, not abstract
    """Clean up resources after pipeline completion.
    Called once after all rows have been processed."""
    pass

def on_complete(self, ctx: PluginContext) -> None:  # noqa: B027 - optional hook
    """Called at the end of each run.
    Override for cleanup."""
    pass
```

**Ambiguity:**
- When is `close()` called vs `on_complete()`?
- For sinks, `on_complete()` is documented as "(before close)" but transforms don't have this clarification
- Is `close()` called on error, or only on success?

---

## 3. Wiring Problems

### 3.1 PluginContext Token is Derivative State

**Location:** `context.py:97`

```python
# === Row-Level Pipelining (BatchTransformMixin) ===
# Set by orchestrator/executor when calling accept() on batch transforms.
# IMPORTANT: This is derivative state - the executor must keep it synchronized
# with the authoritative token flowing through the pipeline.
token: "TokenInfo | None" = field(default=None)
```

The comment admits this is "derivative state" that "must be synchronized". This is a coupling smell - the token should flow through the method signature, not be set on a shared context object.

**Risk:** If executor fails to synchronize, the token in context doesn't match the actual row being processed, corrupting audit trail.

---

### 3.2 BatchTransformMixin Requires connect_output() Before accept()

**Location:** `llm/azure.py:173-200`, `batching/mixin.py:102-152`

The mixin requires explicit wiring:

```python
# llm/azure.py:173
def connect_output(
    self,
    output: OutputPort,
    max_pending: int = 30,
) -> None:
```

This must be called between `__init__()` and `accept()`. If forgotten, runtime error:

```python
# llm/azure.py:223-224
if not self._batch_initialized:
    raise RuntimeError("connect_output() must be called before accept()")
```

**Issue:** This is a two-phase initialization pattern that could be forgotten. The constructor should either require the output port, or the transform should be lazily initialized on first `accept()`.

---

### 3.3 Output Port Protocol Requires Three Parameters

**Location:** `batching/ports.py:41-55`

```python
def emit(self, token: TokenInfo, result: TransformResult | ExceptionResult, state_id: str | None) -> None:
```

The `state_id` parameter is documented as "for retry safety" but it's not clear:
1. Who provides it?
2. What if it's wrong?
3. How does the receiving end validate it?

The `None` case seems to be "state tracking not used" but this creates two operational modes with different guarantees.

---

## 4. Extension Points

### 4.1 No Hook for Plugin Load/Unload Events

Plugins can implement `on_start()`/`on_complete()` per run, but there's no hook for:
- Plugin class loading (static initialization)
- Plugin class unloading (cleanup static resources)
- Manager-level events (all plugins registered)

---

### 4.2 No Hook for Schema Transformation at DAG Edges

When output of transform A connects to input of transform B, there's no hook to:
- Validate schema compatibility
- Transform data to match schemas
- Log/audit schema mismatches

The engine presumably does schema checking, but plugins cannot participate in this.

---

### 4.3 No Plugin Dependency Declaration

Plugins cannot declare dependencies on other plugins. For example:
- LLM transforms depend on `openai` package
- Azure plugins depend on `azure-storage-blob`

Currently handled via optional dependencies in `pyproject.toml`, but plugins have no way to check at load time if their dependencies are available.

---

## 5. Configuration Issues

### 5.1 Schema is Required but Defaults Could Work

**Location:** `config_base.py:71-90`

```python
class DataPluginConfig(PluginConfig):
    @model_validator(mode="after")
    def _require_schema(self) -> Self:
        if self.schema_config is None:
            raise ValueError(
                "Data plugins require 'schema' configuration. ..."
            )
```

Every data plugin must specify schema, even `passthrough` which doesn't care about fields. The error message suggests using `{fields: dynamic}` but this is still boilerplate.

**Consider:** Default to dynamic schema if not specified, rather than requiring explicit declaration.

---

### 5.2 Inconsistent Path Resolution

**Location:** `config_base.py:112-125`

```python
def resolved_path(self, base_dir: Path | None = None) -> Path:
    p = Path(self.path)
    if base_dir and not p.is_absolute():
        return base_dir / p
```

This method exists on `PathConfig` but callers must know to use it:

```python
# csv_source.py:58
self._path = cfg.resolved_path()  # No base_dir passed
```

If `base_dir` is not passed, relative paths resolve from CWD, not config file location. This could cause confusion.

---

## 6. Plugin Isolation

### 6.1 LLM Client Caching Creates Shared State

**Location:** `llm/azure.py:165-168`

```python
# LLM client cache - ensures call_index uniqueness
self._llm_clients: dict[str, AuditedLLMClient] = {}
self._llm_clients_lock = Lock()
self._underlying_client: AzureOpenAI | None = None
```

The underlying Azure client is shared across all rows. If it has any mutable state, rows could interfere with each other.

The cleanup in `_process_row` removes clients from cache:
```python
# llm/azure.py:323-326
finally:
    # Clean up cached client for this state_id to prevent unbounded growth
    with self._llm_clients_lock:
        self._llm_clients.pop(ctx.state_id, None)
```

But the underlying client persists for the transform's lifetime.

---

### 6.2 PluginContext Carries Mutable State

**Location:** `context.py:117-121`

```python
# Checkpoints stored on context
_checkpoint: dict[str, Any] = field(default_factory=dict)
_batch_checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict)
```

The context is passed to plugins and carries mutable checkpoint state. If a plugin modifies this incorrectly, it could corrupt checkpoint data for other plugins.

---

### 6.3 Lock in Dataclass Requires __post_init__ Workaround

**Location:** `context.py:103-131`

```python
_call_index_lock: "Lock" = field(init=False)  # Initialized in __post_init__

def __post_init__(self) -> None:
    # Thread safety for call_index increment (INFRA-01 fix)
    object.__setattr__(self, "_call_index_lock", Lock())
```

Using `object.__setattr__` is a workaround for dataclass frozen semantics. This is fragile - if someone adds `@dataclass(frozen=True)`, this breaks silently.

---

## Confidence Assessment

**High Confidence:**
- Read all core files: `base.py`, `protocols.py`, `hookspecs.py`, `manager.py`, `context.py`, `results.py`, `validation.py`, `schema_factory.py`, `discovery.py`, `config_base.py`
- Read sample plugins: `csv_source.py`, `csv_sink.py`, `passthrough.py`, `field_mapper.py`, `azure.py`, `azure_multi_query.py`
- Read batching infrastructure: `mixin.py`, `ports.py`
- Cross-verified claims by checking imports and dependencies

**Medium Confidence:**
- Engine integration (how engine calls these hooks) - would need to read engine code
- Actual Gate usage - discovery disabled, may be documented elsewhere

---

## Risk Assessment

| Issue | Severity | Impact |
|-------|----------|--------|
| LLM transform dual execution model | High | Breaks polymorphism, requires special casing |
| Protocol/Base class drift | Medium | Maintenance burden, potential runtime surprises |
| Hardcoded validation tables | Medium | Extension requires source modification |
| Missing BaseCoalesce | Low | Inconvenience for implementers |
| Lifecycle hook ordering | Low | Predictability concern |

---

## Information Gaps

1. **Engine integration details** - How does the engine decide which execution model to use for transforms?
2. **Gate usage** - Are gates used at all? The discovery is disabled but infrastructure exists.
3. **Coalesce implementations** - Where are the actual coalesce plugins? Only protocol exists.
4. **Plugin versioning** - How is `plugin_version` used for migration/compatibility?

---

## Caveats

- This analysis focused on the plugin subsystem; engine integration may address some concerns
- The "No Legacy Code" policy in CLAUDE.md explains some design choices (no backwards compat)
- RC-1 status means some gaps may be intentional scope deferral
