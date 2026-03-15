# Architecture Analysis: Plugin Infrastructure (Core Layer)

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Analyst:** Claude Opus 4.6
**Scope:** `src/elspeth/plugins/` -- base classes, protocols, discovery, management, results, schemas, sentinels, utils, validation, Azure auth

---

## Per-File Analysis

### 1. `src/elspeth/plugins/base.py` (689 lines)

**Purpose:** Defines the three abstract base classes that all plugins must inherit: `BaseTransform`, `BaseSink`, `BaseSource`. Provides lifecycle hooks (on_start, on_complete, close), metadata attributes, and schema creation helpers.

**Key classes:**
- `BaseTransform(ABC)` -- Row transforms with three execution models (sync/streaming/batch-aware). Declares `name`, `input_schema`, `output_schema`, `determinism`, `plugin_version`, routing fields (`on_error`, `on_success`), lifecycle guard (`_on_start_called`), and field collision enforcement (`declared_output_fields`).
- `BaseSink(ABC)` -- Output sinks with `write()`, `flush()`, `close()` abstract methods. Adds resume support (`supports_resume`, `configure_for_resume()`, `validate_output_target()`), output contracts, and required-field enforcement.
- `BaseSource(ABC)` -- Data sources with `load()` and `close()` abstract methods. Adds schema contract support, quarantine routing (`_on_validation_failure`), success routing (`on_success`), and field resolution metadata.

**Dependencies:** `elspeth.contracts` (ArtifactDescriptor, Determinism, PluginSchema, SourceRow, PipelineRow, SchemaContract, OutputValidationResult, PluginContext), `elspeth.plugins.results` (TransformResult).

**Design patterns:** Template Method (lifecycle hooks with optional overrides), ABC enforcement, class attributes as interface metadata rather than constructor params.

**Concerns:**
1. **[MEDIUM] Post-construction injection of routing fields.** Both `on_error` and `on_success` on `BaseTransform` default to `None` and are injected post-construction by `cli_helpers.py`. This creates a temporal coupling: the plugin is in an incomplete state between `__init__()` and the bridge injection. The `_on_start_called` guard catches some lifecycle violations, but routing fields are not similarly guarded. If any code reads `on_error` before injection, it silently gets `None` rather than crashing.
2. **[LOW] `_create_schemas` is a static method on BaseTransform.** It imports `SchemaConfig` and `create_schema_from_config` lazily. This is a convenience helper but its placement on the base class creates an implicit coupling. Could be a standalone utility.
3. **[LOW] BaseTransform.process() raises NotImplementedError instead of being abstract.** This is intentional (streaming transforms override `accept()` instead), but it means mypy cannot enforce that one of `process()` or `accept()` is implemented. The runtime check is in TransformExecutor instead.
4. **[LOW] `_on_validation_failure` uses name-mangled underscore prefix on BaseSource.** This is a public-ish field read by the engine. The underscore implies private but it crosses module boundaries. Inconsistent with `on_success` which has no underscore.

---

### 2. `src/elspeth/plugins/config_base.py` (333 lines)

**Purpose:** Pydantic-based configuration base classes for typed, validated plugin configs. Establishes a config class hierarchy: `PluginConfig` -> `DataPluginConfig` -> `PathConfig` -> `SourceDataConfig`/`SinkPathConfig`; plus `TransformDataConfig`.

**Key classes:**
- `PluginConfig(BaseModel)` -- Root config with `extra="forbid"`, optional `schema_config`, and `from_dict()` factory.
- `DataPluginConfig(PluginConfig)` -- Requires `schema_config` (narrows from Optional to required).
- `PathConfig(DataPluginConfig)` -- Adds `path` with validation and `resolved_path()` helper.
- `SourceDataConfig(PathConfig)` -- Adds required `on_validation_failure` for quarantine routing.
- `TabularSourceDataConfig(SourceDataConfig)` -- Adds `columns`, `normalize_fields`, `field_mapping` for tabular sources with header handling.
- `SinkPathConfig(PathConfig)` -- Adds `headers` mode (normalized/original/custom mapping) with `HeaderMode` resolution.
- `TransformDataConfig(DataPluginConfig)` -- Adds optional `required_input_fields` for DAG validation.
- `PluginConfigError(Exception)` -- Config validation failure.

**Dependencies:** `pydantic`, `elspeth.contracts.header_modes` (HeaderMode, parse_header_mode), `elspeth.contracts.schema` (SchemaConfig), `elspeth.core.identifiers` (validate_field_names).

**Design patterns:** Config class hierarchy with progressive specialization, Factory Method (`from_dict()`), Pydantic strict validation with `extra="forbid"`.

**Concerns:**
1. **[LOW] `from_dict()` does schema key remapping.** The `schema` -> `schema_config` key transformation in `from_dict()` is a minor form of magic. If a user passes `schema_config` directly in YAML, it would bypass the `SchemaConfig.from_dict()` parsing. This is documented but could cause confusion.
2. **[LOW] `TabularSourceDataConfig` model_validator imports from `elspeth.core.identifiers`.** This is a cross-layer dependency (plugins importing from core). The validation function `validate_field_names` is a utility, so the coupling is tolerable but noted.

---

### 3. `src/elspeth/plugins/protocols.py` (560 lines)

**Purpose:** Defines `@runtime_checkable` Protocol classes for each plugin type. These are the type-checking contracts that specify what methods/attributes plugins must have. Used by mypy for structural typing and by `isinstance()` for runtime checks.

**Key classes:**
- `SourceProtocol(Protocol)` -- Requires: `name`, `output_schema`, `node_id`, `config`, `determinism`, `plugin_version`, `_on_validation_failure`, `on_success`, `__init__()`, `load()`, `close()`, `on_start()`, `on_complete()`, `get_field_resolution()`, `get_schema_contract()`.
- `TransformProtocol(Protocol)` -- Requires: `name`, `input_schema`, `output_schema`, `node_id`, `config`, `determinism`, `plugin_version`, `is_batch_aware`, `creates_tokens`, `declared_output_fields`, `validate_input`, `on_error`, `on_success`, `__init__()`, `process()`, `close()`, `on_start()`, `on_complete()`.
- `BatchTransformProtocol(Protocol)` -- Like TransformProtocol but `process()` takes `list[PipelineRow]`.
- `SinkProtocol(Protocol)` -- Requires: `name`, `input_schema`, `idempotent`, `node_id`, `config`, `determinism`, `plugin_version`, `supports_resume`, `declared_required_fields`, `validate_input`, `__init__()`, `write()`, `flush()`, `close()`, `on_start()`, `on_complete()`, `configure_for_resume()`, `validate_output_target()`, `set_resume_field_resolution()`.

**Dependencies:** `elspeth.contracts` (Determinism; TYPE_CHECKING: ArtifactDescriptor, PluginSchema, SourceRow, PluginContext, PipelineRow, OutputValidationResult, TransformResult).

**Design patterns:** Structural typing via Protocol, `@runtime_checkable` for isinstance() support, TYPE_CHECKING imports to avoid circular dependencies.

**Concerns:**
1. **[MEDIUM] Protocol-base class drift risk.** The protocols and base classes must stay in sync manually. If a field is added to `BaseTransform` but not to `TransformProtocol` (or vice versa), mypy won't catch the mismatch directly because concrete plugins inherit from the base class, not the protocol. The protocol is only checked where protocol-typed parameters are used (engine code). There's no automated test verifying protocol/base class attribute parity.
2. **[LOW] `get_schema_contract()` on SourceProtocol returns `Any`.** The docstring explains this avoids a circular import, but it sacrifices type safety. The actual return is `SchemaContract | None`.
3. **[LOW] `_on_validation_failure` with underscore in protocol.** A protocol declaring a name-mangled (underscore-prefixed) attribute is unusual. Protocols describe public interfaces; this naming is inconsistent.

---

### 4. `src/elspeth/plugins/results.py` (30 lines)

**Purpose:** Re-export module. All result types (`TransformResult`, `GateResult`, `RoutingAction`, `RowOutcome`, `SourceRow`) are defined in `elspeth.contracts` and re-exported here as part of the public plugin API.

**Key exports:** `GateResult`, `RoutingAction`, `RowOutcome`, `SourceRow`, `TransformResult`.

**Dependencies:** `elspeth.contracts`.

**Design patterns:** Facade/re-export pattern to maintain a stable import path for plugin authors.

**Concerns:**
1. **[TRIVIAL] Thin re-export module.** This is just 30 lines of re-exports. It exists purely for API ergonomics (`from elspeth.plugins.results import TransformResult` vs `from elspeth.contracts import TransformResult`). Both paths work. The duplication in import paths is minor but adds cognitive overhead.

---

### 5. `src/elspeth/plugins/sentinels.py` (69 lines)

**Purpose:** Provides the `MISSING` singleton sentinel, used to distinguish "field not present" from "field is explicitly None" when accessing row data.

**Key classes:**
- `MissingSentinel` -- Singleton with `__new__`, `__copy__`, `__deepcopy__`, `__reduce__` all preserving identity. Uses `__slots__ = ()` for efficiency.
- `MISSING: Final[MissingSentinel]` -- The singleton instance.

**Dependencies:** None (stdlib only).

**Design patterns:** Singleton with pickle/copy safety.

**Concerns:**
1. **[NONE] Well-implemented.** Clean singleton pattern, proper identity preservation across serialization boundaries, correct `Final` typing. No issues.

---

### 6. `src/elspeth/plugins/hookspecs.py` (74 lines)

**Purpose:** Defines the pluggy hook specifications (interfaces) that plugin implementations must satisfy. Three hook specs, one per plugin type.

**Key classes:**
- `ElspethSourceSpec` -- `@hookspec elspeth_get_source() -> list[type[SourceProtocol]]`
- `ElspethTransformSpec` -- `@hookspec elspeth_get_transforms() -> list[type[TransformProtocol]]`
- `ElspethSinkSpec` -- `@hookspec elspeth_get_sinks() -> list[type[SinkProtocol]]`

**Key objects:**
- `PROJECT_NAME = "elspeth"` -- pluggy project identifier.
- `hookspec` -- `pluggy.HookspecMarker` for defining hooks.
- `hookimpl` -- `pluggy.HookimplMarker` for implementing hooks.

**Dependencies:** `pluggy`, `elspeth.plugins.protocols` (TYPE_CHECKING only).

**Design patterns:** pluggy hook specification pattern. Markers are exported for plugin implementations to use.

**Concerns:**
1. **[NONE] Clean and minimal.** Correctly separates hook definitions from implementations. The `hookimpl` marker is exported for plugins to import.

---

### 7. `src/elspeth/plugins/manager.py` (280 lines)

**Purpose:** Central plugin registry. Wraps a pluggy `PluginManager`, adds name-based caches, duplicate detection, config validation, and factory methods for creating validated plugin instances.

**Key classes:**
- `PluginManager` -- Manages plugin lifecycle: `register_builtin_plugins()` triggers discovery, `register()` adds plugins with rollback on failure, `get_*_by_name()` for lookup, `create_source/transform/sink()` for validated construction.

**Dependencies:** `pluggy`, `elspeth.plugins.hookspecs` (specs and markers), `elspeth.plugins.protocols` (protocol types for cache typing), `elspeth.plugins.validation` (PluginConfigValidator), `elspeth.plugins.discovery` (lazy import).

**Design patterns:** Registry pattern with name-based indexing, Factory Method with pre-validation, pluggy integration.

**Concerns:**
1. **[MEDIUM] Cache typing uses Protocol types, not base class types.** The caches are `dict[str, type[SourceProtocol]]` etc. Since plugins inherit from base classes (not protocols), the type is technically incorrect -- it works because base classes satisfy the protocols, but it could be more precise with `type[BaseSource]`.
2. **[MEDIUM] `_refresh_caches()` rebuilds entirely on every `register()`.** For the current scale (tens of plugins) this is fine, but it's called on every registration including the initial bulk registration in `register_builtin_plugins()` (three calls to `register()` means three full cache rebuilds). This is a minor inefficiency.
3. **[LOW] `create_*` methods validate config then pass raw dict to constructor.** The validation step (via PluginConfigValidator) creates a Pydantic model, validates it, and discards it. The constructor then re-parses the config dict to create its own Pydantic model. This is double parsing -- once for validation, once for construction. The validated model could be passed through.

---

### 8. `src/elspeth/plugins/discovery.py` (288 lines)

**Purpose:** Filesystem-based plugin discovery. Scans plugin directories for Python files, imports them, and finds classes that inherit from base classes and have a `name` attribute.

**Key functions:**
- `discover_plugins_in_directory(directory, base_class)` -- Scans a directory for plugin classes.
- `_discover_in_file(py_file, base_class)` -- Imports a single file and finds plugin classes via `inspect.getmembers()`.
- `discover_all_plugins()` -- Orchestrates scanning across all configured directories.
- `create_dynamic_hookimpl(plugin_classes, hook_method_name)` -- Creates pluggy hookimpl objects dynamically for registration.
- `get_plugin_description(plugin_cls)` -- Extracts description from docstring.

**Key data:**
- `EXCLUDED_FILES` -- frozenset of filenames to skip during scanning (infrastructure files, helpers, clients).
- `PLUGIN_SCAN_CONFIG` -- Maps plugin type to directories to scan.
- `_get_base_classes()` -- Deferred import to avoid circular dependencies.

**Dependencies:** `importlib.util`, `inspect`, `sys`, `pathlib`, `logging`, `elspeth.plugins.base` (deferred), `elspeth.plugins.hookspecs` (deferred).

**Design patterns:** Convention-over-configuration discovery (file-per-plugin in known directories), deferred imports to break circular dependencies, dynamic class generation for hookimpls.

**Concerns:**
1. **[MEDIUM] Brittle `EXCLUDED_FILES` allowlist.** Every new infrastructure file must be added to this frozenset or it will be scanned as a potential plugin source. If a new helper file contains a class that inherits from `BaseTransform`, it will be registered as a plugin. This is inverted logic -- it would be safer to use an inclusion pattern (e.g., a decorator or naming convention) rather than exclusion.
2. **[MEDIUM] Non-recursive scanning requires explicit directory listing.** `PLUGIN_SCAN_CONFIG` must list subdirectories explicitly (e.g., `"transforms/azure"` separately from `"transforms"`). Adding a new subdirectory requires updating this config. This is brittle but at least explicit.
3. **[LOW] `create_dynamic_hookimpl()` uses `setattr` to monkey-patch methods onto a dynamically created class.** This works but is fragile and hard to debug. The dynamic class has no useful `__qualname__` for error messages.
4. **[LOW] `get_plugin_description()` uses `getattr(plugin_cls, "name", ...)`.** Per project policy, this defensive `getattr` is questionable since all plugin classes are system-owned and must have `name`. However, this function may be called on classes that haven't passed validation yet, so the fallback is arguably appropriate as a display utility.

---

### 9. `src/elspeth/plugins/schema_factory.py` (202 lines)

**Purpose:** Creates runtime Pydantic schema models from `SchemaConfig` declarations. Enforces the three-tier trust model: sources may coerce (`allow_coercion=True`), transforms/sinks must reject wrong types (`allow_coercion=False`).

**Key functions:**
- `create_schema_from_config(config, name, allow_coercion)` -- Main factory. Routes to observed vs explicit schema creation.
- `_create_dynamic_schema(name)` -- Creates an "accept anything" schema for observed mode with NaN/Infinity rejection.
- `_create_explicit_schema(config, name, allow_coercion)` -- Creates typed schema with field definitions, extra mode (allow/forbid), and strict mode based on coercion flag.
- `_get_python_type(field_def)` -- Maps field type strings to Python types.
- `_find_non_finite_value_path(value, path)` -- Recursively finds NaN/Infinity in nested structures.
- `_reject_non_finite_observed_values(data)` -- Model validator for observed schemas.

**Key data:**
- `TYPE_MAP` -- Maps `"str"`, `"int"`, `"float"`, `"bool"`, `"any"` to Python types. `"float"` maps to `FiniteFloat` (rejects NaN/Infinity).
- `FiniteFloat` -- `Annotated[float, Field(allow_inf_nan=False)]`.
- `_ObservedPluginSchema(PluginSchema)` -- Base for observed schemas with NaN/Infinity rejection.

**Dependencies:** `math`, `pydantic` (ConfigDict, Field, create_model, model_validator), `elspeth.contracts` (PluginSchema), `elspeth.contracts.schema` (FieldDefinition, SchemaConfig).

**Design patterns:** Abstract Factory (creates schema classes at runtime), Strategy (coercion behavior varies by trust tier).

**Concerns:**
1. **[LOW] `TYPE_MAP` is not extensible.** Adding a new field type requires modifying this dict. For a system-owned framework this is fine, but worth noting.
2. **[LOW] `_find_non_finite_value_path` recurses without depth limit.** Deep nesting could cause stack overflow. In practice, pipeline data is shallow, but this is a theoretical concern.
3. **[NONE] Trust model enforcement is well-implemented.** The `allow_coercion` flag correctly maps to Pydantic's `strict` mode, and NaN/Infinity rejection is thorough (covers numpy types without importing numpy).

---

### 10. `src/elspeth/plugins/utils.py` (56 lines)

**Purpose:** Provides `get_nested_field()`, a dot-notation path traversal utility for nested dictionaries. Uses the `MISSING` sentinel for "not found" distinction.

**Key functions:**
- `get_nested_field(data, path, default=MISSING)` -- Traverses nested dicts using dot notation. Raises `TypeError` if a non-dict is encountered mid-path. Returns `MISSING` or custom default if path not found.

**Dependencies:** `elspeth.plugins.sentinels` (MISSING).

**Design patterns:** Utility function with sentinel-based missing detection.

**Concerns:**
1. **[NONE] Clean implementation.** Appropriate use of sentinels, raises TypeError for structural violations (not defensive), well-documented.

---

### 11. `src/elspeth/plugins/validation.py` (342 lines)

**Purpose:** Pre-instantiation config validation. Validates plugin configs against their Pydantic models without actually creating plugin instances. Returns structured `ValidationError` objects rather than raising exceptions.

**Key classes:**
- `ValidationError` (dataclass) -- Structured error with `field`, `message`, `value`.
- `PluginConfigValidator` -- Validates configs by looking up the appropriate Pydantic config model and calling `from_dict()`. Methods: `validate_source_config()`, `validate_transform_config()`, `validate_sink_config()`, `validate_schema_config()`.

**Dependencies:** `pydantic.ValidationError`, `elspeth.plugins.config_base` (PluginConfigError, PluginConfig; TYPE_CHECKING). Many lazy imports of concrete plugin configs.

**Design patterns:** Strategy/dispatcher pattern (maps plugin name to config class), structured error reporting.

**Concerns:**
1. **[HIGH] Hardcoded plugin-name-to-config-class mapping.** `_get_transform_config_model()` is a 70-line if/elif chain mapping plugin names to their config classes. Adding a new plugin requires updating this method. This is the single largest maintenance burden in the plugin infrastructure -- it's easy to forget and there's no automated check. This mirrors the `EXCLUDED_FILES` problem in discovery.py: the system requires manual synchronization between discovery and validation registries.
2. **[MEDIUM] Double validation.** As noted in manager.py, the validator creates a Pydantic model, validates, discards. Then the plugin constructor re-creates it. This is wasted work. The validator could return the validated config model for the constructor to use.
3. **[LOW] `_extract_wrapped_plugin_config_error` uses `type(cause) is PydanticValidationError`.** This is identity comparison on exception types, which won't match subclasses. In practice PydanticValidationError is not subclassed, so this is fine, but `isinstance()` would be more robust.
4. **[LOW] Naming collision: `ValidationError` shadows the common Pydantic/stdlib name.** The local `ValidationError` dataclass has the same name as `pydantic.ValidationError`. The import alias `PydanticValidationError` helps, but consumers must be careful.

---

### 12. `src/elspeth/plugins/azure/auth.py` (234 lines)

**Purpose:** Azure authentication configuration supporting four mutually exclusive methods: connection string, SAS token, managed identity, and service principal. Shared across Azure plugins (blob source, blob sink).

**Key classes:**
- `AzureAuthConfig(BaseModel)` -- Pydantic model with `model_validator` ensuring exactly one auth method is configured. Provides `create_blob_service_client()` factory and `auth_method` property.

**Dependencies:** `pydantic`, `azure.storage.blob` (lazy import), `azure.identity` (lazy import for managed identity/service principal).

**Design patterns:** Pydantic validation with mutual exclusion enforcement, Factory Method for client creation, lazy imports for optional dependencies.

**Concerns:**
1. **[LOW] `cast()` usage after validator guarantees.** Multiple `cast(str, self.field)` calls are necessary because Pydantic's type narrowing doesn't propagate through `model_validator`. This is correct but verbose.
2. **[LOW] `_is_set()` duplicates logic from the validator.** The same "non-None and non-whitespace" check runs during validation and during `create_blob_service_client()`. Minor duplication but ensures runtime consistency with validation semantics.
3. **[NONE] Well-structured for its purpose.** Proper mutual exclusion, helpful error messages, lazy imports for optional dependencies. Good code.

---

## Overall Architecture Analysis

### 1. Plugin System Architecture -- pluggy Integration

The plugin system uses a **layered architecture**:

```
Layer 4: PluginManager (registry, lookup, validated creation)
Layer 3: Discovery (filesystem scanning, dynamic hookimpl generation)
Layer 2: Hookspecs (pluggy hook definitions -- 3 hooks total)
Layer 1: Protocols + Base Classes (contracts + implementations)
Layer 0: Results + Schemas + Config (data types and validation)
```

**pluggy's role is minimal.** There are exactly three hooks (`elspeth_get_source`, `elspeth_get_transforms`, `elspeth_get_sinks`), each returning a list of classes. pluggy manages the hook call aggregation (collecting results from multiple registrants), but the actual plugin lifecycle (construction, on_start, process, on_complete, close) is managed entirely by the engine's orchestrator and executors.

**The discovery->hookimpl bridge is unusual.** Rather than plugins self-registering via `@hookimpl`, discovery.py scans the filesystem, finds classes by inheritance, and creates dynamic hookimpl wrappers. This means pluggy is essentially acting as a glorified list aggregator. The actual discovery is inheritance-based (`issubclass(cls, BaseSource)`), not hook-based.

**Assessment:** pluggy adds complexity for minimal value in the current architecture. Since all plugins are system-owned code in known directories, the filesystem scanner could directly populate the PluginManager's caches without the pluggy indirection. However, pluggy does provide: (a) clean hook call semantics if multiple registrants exist, (b) `check_pending()` for validating hooks, and (c) `unregister()` for rollback. These are nice-to-haves but not strictly necessary.

### 2. Protocol Hierarchy

Three concrete protocols, no base protocol:

```
SourceProtocol     -- load(), close(), on_start(), on_complete(), get_field_resolution(), get_schema_contract()
TransformProtocol  -- process(), close(), on_start(), on_complete()
BatchTransformProtocol -- process(list), close(), on_start(), on_complete()
SinkProtocol       -- write(), flush(), close(), on_start(), on_complete(), configure_for_resume(), validate_output_target(), set_resume_field_resolution()
```

**Common attributes across all protocols:** `name`, `node_id`, `config`, `determinism`, `plugin_version`, `__init__(config)`, `close()`, `on_start()`, `on_complete()`.

**Notable:** A `PluginProtocol` base was explicitly deleted (comment in protocols.py). The rationale is sound -- the protocols diverge enough that a shared base would be a leaky abstraction. However, the repeated declaration of 6+ identical attributes across three protocols is maintenance overhead.

**Protocol/Base class relationship:** Protocols define the contract; base classes provide the implementation. The engine code uses protocol types for parameters (e.g., `TransformProtocol`), but runtime objects are always base class subclasses. The two must stay synchronized manually.

### 3. Base Class Design

Base classes are **moderately fat**:

| Base Class | Abstract Methods | Concrete Methods | Class Attributes |
|---|---|---|---|
| BaseTransform | 0 (process is NotImplementedError) | process, close, on_start, on_complete, _create_schemas | 12 |
| BaseSink | 3 (write, flush, close) | configure_for_resume, validate_output_target, set_resume_field_resolution, get/set_output_contract, on_start, on_complete | 9 |
| BaseSource | 2 (load, close) | get_field_resolution, get/set_schema_contract, on_start, on_complete | 8 |

The base classes carry significant metadata (routing, schemas, determinism, version, node_id, validation flags, collision enforcement). This metadata is largely for the engine's benefit, not the plugin's -- it enables the engine to make decisions without calling plugin methods.

**Assessment:** The metadata density is justified by the audit and DAG requirements. The lifecycle hooks (on_start, on_complete, close) are well-documented with clear guarantees. The main architectural risk is the post-construction injection pattern for routing fields.

### 4. Discovery Mechanism

**Flow:**
1. `PluginManager.register_builtin_plugins()` calls `discover_all_plugins()`
2. `discover_all_plugins()` iterates `PLUGIN_SCAN_CONFIG` (hardcoded directory lists)
3. For each directory, `discover_plugins_in_directory()` scans `*.py` files
4. `_discover_in_file()` imports the file, inspects members for `issubclass(cls, base_class)`
5. Validated classes are collected, checked for duplicate names
6. Results are wrapped in dynamic hookimpls via `create_dynamic_hookimpl()`
7. Dynamic hookimpls are registered with pluggy

**Strengths:** No decorator needed on plugin classes. Simply inheriting from the base class and having a `name` attribute is sufficient. Duplicate detection is thorough (both in discovery and in the manager's cache refresh).

**Weaknesses:** The `EXCLUDED_FILES` frozenset is a maintenance burden. The `PLUGIN_SCAN_CONFIG` directory list is hardcoded. The dynamic hookimpl generation is complex for what it achieves.

### 5. Plugin Manager

The `PluginManager` provides:
- **Registration:** Via pluggy with rollback on failure.
- **Lookup:** Name-based caches rebuilt on every registration. O(1) lookup by name.
- **Validated Creation:** `create_source/transform/sink()` validate config before construction.
- **Duplicate Detection:** Crashes on duplicate plugin names (correct per system-owned policy).

The manager does NOT manage:
- Plugin lifecycle (that's the orchestrator's job).
- Plugin configuration beyond validation (config is a raw dict passed to constructors).
- Plugin instances after creation (no instance registry).

### 6. Result Types

All result types live in `elspeth.contracts.results` and are re-exported through `elspeth.plugins.results`:

- **TransformResult** -- Success or error, carries output row dict, success/error reasons for audit, supports `success()`, `error()`, `success_multi()` factory methods.
- **GateResult** -- Carries `RoutingAction` (continue, route_to_sink, fork_to_paths) with reasons.
- **SourceRow** -- Wraps row data with valid/quarantined status.
- **RowOutcome** -- Enum of terminal states (COMPLETED, ROUTED, FORKED, QUARANTINED, etc.).

The re-export pattern through `plugins.results` maintains backward-compatible import paths while keeping canonical definitions in `contracts`.

### 7. Schema Factory

The schema factory creates runtime Pydantic models with trust-tier-appropriate validation:

- **Observed mode:** Accepts any fields, rejects NaN/Infinity via model validator.
- **Fixed mode:** Typed fields with `extra="forbid"`, coercion controlled by `allow_coercion`.
- **Flexible mode:** Typed required fields with `extra="allow"`.

The `allow_coercion` parameter maps directly to Pydantic's `strict` mode, which is the correct mechanism. `FiniteFloat` handles typed float fields; `_ObservedPluginSchema` handles untyped fields. Together they ensure NaN/Infinity never enters the pipeline.

### 8. Validation

Validation is **pre-instantiation** and **separate from construction**:

1. `PluginConfigValidator` looks up the config model class by plugin name.
2. Calls `config_model.from_dict(config)` which runs Pydantic validation.
3. Returns structured `ValidationError` list (empty = valid).
4. Plugin constructor re-parses the config dict independently.

The hardcoded if/elif chain in `_get_transform_config_model()` is the largest maintenance liability in the plugin system.

### 9. Sentinels

Single sentinel: `MISSING`. Correctly implemented singleton with identity-safe copy/pickle. Used by `get_nested_field()` in utils.py and potentially by plugin implementations directly.

### 10. Cross-Cutting Dependencies

```
plugins/base.py          -> contracts (types, schemas, results)
plugins/config_base.py   -> contracts (SchemaConfig, HeaderMode), core (identifiers)
plugins/protocols.py     -> contracts (types, schemas, results) [TYPE_CHECKING]
plugins/results.py       -> contracts (re-export)
plugins/schema_factory.py -> contracts (PluginSchema, SchemaConfig, FieldDefinition)
plugins/manager.py       -> plugins (hookspecs, protocols, validation, discovery)
plugins/discovery.py     -> plugins (base, hookspecs)
plugins/validation.py    -> plugins (config_base), concrete plugin configs (lazy)
plugins/utils.py         -> plugins (sentinels)
plugins/azure/auth.py    -> (standalone: pydantic, azure SDK)
```

The dependency flow is generally clean: `contracts` is the foundation, `plugins` depends on it, `engine` depends on both. The only cross-layer dependency is `config_base.py` importing from `core.identifiers`, which is a minor utility dependency.

**Circular dependency avoidance:** The codebase uses `TYPE_CHECKING` imports extensively and deferred imports in discovery.py and validation.py. This is necessary but makes the actual dependency graph harder to trace.

---

## Concerns and Recommendations (Ranked by Severity)

### HIGH

1. **Hardcoded plugin-name-to-config-class dispatch in validation.py.** The `_get_transform_config_model()` and `_get_sink_config_model()` methods are 70+ line if/elif chains that must be manually updated when plugins are added. This is the most likely source of "forgot to update" bugs. **Recommendation:** Plugins could declare their config class via a class attribute (e.g., `config_class = CSVSourceConfig`), and the validator could discover it from the plugin class rather than maintaining a parallel registry. Alternatively, a decorator or registration mechanism could link plugin names to config classes at import time.

### MEDIUM

2. **Protocol/base class synchronization is manual.** Adding a field to `BaseTransform` without updating `TransformProtocol` (or vice versa) will silently succeed unless mypy is run against engine code that uses the protocol type. **Recommendation:** Add a test that verifies all protocol attributes exist on the corresponding base class (and vice versa, for non-private attributes).

3. **Post-construction routing field injection.** `on_error` and `on_success` on transforms are `None` after `__init__()` and injected later by `cli_helpers.py`. This temporal coupling means the object is in an invalid state between construction and injection. **Recommendation:** Consider passing routing config through the constructor (expanding the config dict), or adding a guard that crashes if routing fields are accessed while still `None` (similar to `_on_start_called`).

4. **Brittle `EXCLUDED_FILES` in discovery.py.** Forgetting to add a new infrastructure file to this set will cause it to be scanned for plugins. **Recommendation:** Invert the pattern: use an inclusion marker (e.g., a class variable like `_is_plugin = True` or a naming convention) rather than an exclusion list. Or move plugin files to dedicated subdirectories that contain only plugin implementations.

5. **Double config parsing (validate then construct).** `PluginManager.create_*()` validates config via the validator (parsing it into a Pydantic model), then the plugin constructor re-parses it. **Recommendation:** The validator could return the parsed config model, and plugins could accept pre-validated configs. This would require a protocol change but would eliminate redundant parsing.

6. **Cache rebuild on every registration.** `_refresh_caches()` rebuilds all three caches from scratch on every `register()` call. During `register_builtin_plugins()`, this happens 3 times. **Recommendation:** Batch registration or incremental cache updates.

### LOW

7. **`_on_validation_failure` naming inconsistency.** Underscore prefix implies private, but it's read across module boundaries (engine code, protocols). `on_success` on the same class has no underscore. Should be `on_validation_failure` for consistency.

8. **`get_plugin_description()` uses defensive `getattr`.** Per project policy, system-owned classes should not use defensive access. The fallback `getattr(plugin_cls, "name", plugin_cls.__name__)` hides potential bugs. However, this is a display utility that may be called before full validation, so the defense is arguably warranted.

9. **pluggy overhead for minimal benefit.** The three-hook architecture could be replaced with direct registration. pluggy provides clean abstractions but the dynamic hookimpl generation and hook call aggregation add complexity for a system where all plugins are known at compile time.

---

## Confidence: HIGH

This analysis is based on a complete reading of all 12 specified files. The architecture is well-documented with extensive docstrings and comments. The design decisions are clearly motivated by the audit trail requirements and trust model. The main concerns are maintenance burdens (hardcoded dispatch tables, exclusion lists) rather than architectural defects. The plugin system is fundamentally sound for its current purpose as a system-owned, non-extensible plugin framework.
