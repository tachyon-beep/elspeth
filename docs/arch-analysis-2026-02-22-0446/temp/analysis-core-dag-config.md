# Architecture Analysis: Core Infrastructure (DAG, Checkpoint, Config, Utilities)

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Analyst:** Claude Opus 4.6
**Scope:** 12 files across core/dag/, core/checkpoint/, and core root utilities

---

## 1. File-by-File Analysis

### 1.1 core/dag/models.py (137 lines)

**Purpose:** Leaf module defining types, constants, and exceptions for DAG operations. Deliberately has no intra-package imports to prevent circular dependencies.

**Key classes/functions:**
- `GraphValidationError(ValueError)` -- Exception for invalid graph structures
- `GraphValidationWarning` -- Frozen dataclass for non-fatal construction warnings (code, message, node_ids)
- `BranchInfo` -- Frozen dataclass consolidating branch-to-coalesce and branch-to-gate mappings
- `NodeInfo` -- Frozen dataclass storing node metadata (ID, type, plugin name, config, schemas)
- `_GateEntry` -- Internal gate metadata for wiring (frozen, not slotted)
- `WiredTransform` -- Pairs a TransformProtocol with its TransformSettings, validates name match
- `NodeConfig` -- Type alias: `dict[str, Any]` (intentionally untyped; plugins validate via Pydantic)
- `_suggest_similar()` -- Fuzzy matching for wiring error messages (uses `difflib`)
- `_NODE_ID_MAX_LENGTH` -- Imported from landscape schema, enforced in NodeInfo.__post_init__

**Dependencies:**
- `elspeth.contracts.enums.NodeType`
- `elspeth.contracts.schema.SchemaConfig`
- `elspeth.contracts.types` (type aliases: NodeID, CoalesceName, etc.)
- `elspeth.core.landscape.schema.NODE_ID_COLUMN_LENGTH`

**Architectural patterns:**
- Leaf module pattern (no intra-package imports)
- Frozen dataclasses for immutability
- Type aliases for domain identifiers (NewType wrappers)
- `__post_init__` for invariant enforcement

**Concerns:**
- `_GateEntry` is `frozen=True` but lacks `slots=True` (inconsistent with other dataclasses in the module). Minor memory/perf difference.
- `NodeConfig = dict[str, Any]` is documented as intentional but creates a Tier 1 trust gap: the graph layer stores arbitrary dicts that are only validated by individual plugins. The config dict is later frozen to `MappingProxyType` by the builder, but the shallow freeze means nested values remain mutable.
- `NodeInfo.config` field type annotation says `dict` but runtime type after build is `MappingProxyType`. This is documented but creates a lie-in-the-type-system issue -- mypy sees `dict` while runtime is `MappingProxyType`.

---

### 1.2 core/dag/graph.py (1,452 lines)

**Purpose:** The `ExecutionGraph` class -- wraps NetworkX `MultiDiGraph` with domain-specific query, validation, and traversal operations. Construction is delegated to `builder.py`.

**Key classes/functions:**
- `ExecutionGraph` -- Core graph wrapper with:
  - **Construction facade:** `from_plugin_instances()` (delegates to builder via lazy import)
  - **Structural queries:** `get_source()`, `get_sinks()`, `get_node_info()`, `get_edges()`, `get_incoming_edges()`
  - **Traversal:** `topological_order()`, `get_pipeline_node_sequence()`, `get_next_node()`, `get_first_transform_node()`
  - **ID maps:** 6 `set_*` / `get_*` pairs for sink, transform, gate, aggregation, coalesce, branch mappings
  - **Route resolution:** `get_route_resolution_map()`, `get_route_label()`, `get_terminal_sink_map()`, `get_branch_first_nodes()`, `get_branch_to_sink_map()`
  - **Validation:** `validate()` (structural), `validate_edge_compatibility()` (schema), `_validate_coalesce_compatibility()`, `_validate_route_resolution_map_complete()`
  - **Schema tracing:** `get_effective_producer_schema()`, `get_effective_guaranteed_fields()`, `get_required_fields()`, `get_schema_config_from_node()`
  - **Warnings:** `warn_divert_coalesce_interactions()`
  - **Step map:** `build_step_map()` for audit trail step numbering

**Dependencies:**
- `networkx` (MultiDiGraph, topological_sort, is_directed_acyclic_graph, descendants, find_cycle, freeze)
- `elspeth.contracts` (EdgeInfo, RouteDestination, RoutingMode, check_compatibility, NodeType, SchemaConfig)
- `elspeth.core.dag.models` (all model types)

**Architectural patterns:**
- Wrapper/facade pattern over NetworkX
- Lazy import for builder (breaks circular dependency)
- Protocol-based schema compatibility checking
- Strategy-aware coalesce validation (union/nested/select have different rules)
- Frozen graph copy via `nx.freeze()` for external access
- Separation of structural validation (`validate()`) from schema validation (`validate_edge_compatibility()`)

**Concerns:**
- **C1 (MEDIUM): God class tendency.** At 1,452 lines, ExecutionGraph handles construction delegation, structural queries, traversal, schema validation, route resolution, branch tracing, and step mapping. The separation of builder logic helped, but the graph class still has too many responsibilities. Consider extracting schema validation and route resolution into separate collaborators.
- **C2 (LOW): Mutable internal state with public setters.** The 6+ `set_*` methods allow any caller to mutate graph state after construction. While these are used only by the builder, they are public API. `MappingProxyType` freezing happens at the end of `build_execution_graph()`, but the setter methods remain callable. A `freeze()` method or construction-only builder pattern would be safer.
- **C3 (LOW): Repeated graph iteration patterns.** Multiple methods iterate `self._graph.nodes(data=True)` with `data["info"]` extraction. A cached node-info index would eliminate redundant iterations.
- **C4 (LOW): `get_nx_graph()` returns frozen copy.** This is correct for safety but means every external caller pays the copy cost. If called frequently, this could be a performance concern.

---

### 1.3 core/dag/builder.py (938 lines)

**Purpose:** Module-level `build_execution_graph()` function that constructs an ExecutionGraph from plugin instances. Extracted from ExecutionGraph to break circular dependencies. This is the single production code path for graph construction (test integrity requirement from CLAUDE.md).

**Key classes/functions:**
- `build_execution_graph()` -- The monolithic build function (~830 lines of logic):
  - Generates deterministic node IDs using canonical JSON + SHA-256 hashing
  - Adds source, sinks, transforms, aggregations, gates, and coalesce nodes
  - Builds producer/consumer registries for connection wiring
  - Validates connection namespace integrity (no duplicates, no dangling, no overlap with sinks)
  - Resolves gate routes (to sinks, to processing nodes, to fork branches)
  - Connects fork branches to coalesce or sink destinations
  - Validates coalesce branch origins (all declared branches must come from gates)
  - Resolves schema propagation through coalesce nodes (strategy-aware: union/nested/select)
  - Deferred gate schema resolution (two-pass: first pass pre-coalesce, second pass post-coalesce)
  - Adds divert edges for quarantine/error sinks
  - Topological sort via NetworkX
  - Phase 2 schema compatibility validation
  - Config freezing (MappingProxyType wrapping)
  - Pipeline node sequence and step map generation
- `_field_name_type()` -- Parses field specs in multiple formats
- `_field_required()` -- Extracts required status from field specs

**Dependencies:**
- `networkx` (topological_sort, find_cycle)
- `elspeth.contracts` (RouteDestination, RoutingMode, error_edge_label, NodeType, type aliases)
- `elspeth.core.canonical` (canonical_json for deterministic node ID generation)
- `elspeth.core.dag.models` (all model types)

**Architectural patterns:**
- Module-level function (not a class) to avoid circular dependency with graph.py
- Deterministic node IDs via canonical JSON + SHA-256 (critical for checkpoint/resume)
- Producer/consumer registry pattern for connection wiring validation
- Two-pass schema resolution (pre-coalesce and post-coalesce)
- Deep copy for schema dicts to prevent aliasing (P1-2026-02-14 bug fix)
- Explicit fail-fast: no fallback behavior for fork branches without destinations

**Concerns:**
- **C5 (HIGH): Monolithic function.** `build_execution_graph()` is ~830 lines of sequential logic with deeply nested helper closures (`node_id()`, `_best_schema_dict()`, `_sink_name_set()`, `register_producer()`, `register_consumer()`). The function is effectively a procedural script. While the logic is sequential and must be (each section depends on prior sections), the inline closures reference the outer scope extensively, making testing of individual phases impossible. Consider a builder class with named methods for each phase.
- **C6 (MEDIUM): `getattr()` for `_output_schema_config`.** Lines 223 and 251 use `getattr(transform, "_output_schema_config", None)` which is documented as a "framework boundary" exception. However, `_output_schema_config` is a private attribute accessed across module boundaries. This should be promoted to the TransformProtocol or exposed via a public method.
- **C7 (LOW): `assert select_branch is not None` (line 888).** An assert in production code for a condition "guaranteed by validate_merge_requirements." If the guarantee is truly structural, the assert is redundant. If it could fail, assert is wrong (disabled in optimized mode). A proper crash with a descriptive message would be more appropriate.
- **C8 (LOW): Hash collision risk.** Node IDs use 48-bit SHA-256 truncation (12 hex chars). For a pipeline with N nodes, collision probability is approximately N^2 / 2^49. With <100 nodes this is negligible, but the birthday bound should be documented.

---

### 1.4 core/checkpoint/manager.py (267 lines)

**Purpose:** `CheckpointManager` handles checkpoint creation and retrieval for crash recovery. Stores checkpoints in the Landscape audit database.

**Key classes/functions:**
- `IncompatibleCheckpointError` -- Raised when checkpoint format version doesn't match
- `CheckpointCorruptionError` -- Raised for Tier 1 data integrity failures (unrecoverable)
- `CheckpointManager`:
  - `create_checkpoint()` -- Creates checkpoint with topology hash, node config hash, optional aggregation state. All generation inside transaction for atomicity.
  - `get_latest_checkpoint()` -- Retrieves most recent checkpoint by sequence number. Validates format version compatibility.
  - `get_checkpoints()` -- All checkpoints for a run, ordered by sequence.
  - `delete_checkpoints()` -- Cleanup after successful run completion.
  - `_validate_checkpoint_compatibility()` -- Rejects both older and newer format versions.

**Dependencies:**
- `sqlalchemy` (select, delete, asc, desc)
- `elspeth.contracts.Checkpoint` (frozen dataclass with CURRENT_FORMAT_VERSION)
- `elspeth.core.canonical` (compute_full_topology_hash, stable_hash)
- `elspeth.core.checkpoint.serialization` (checkpoint_dumps)
- `elspeth.core.landscape.database.LandscapeDB`
- `elspeth.core.landscape.schema.checkpoints_table`

**Architectural patterns:**
- Transaction-scoped checkpoint creation (atomicity guarantee)
- Format versioning for checkpoint compatibility
- Full topology hashing (BUG-COMPAT-01 fix: validates entire DAG, not just upstream)
- Separate serialization for aggregation state (checkpoint_dumps, not canonical_json)
- Tier 1 trust model: checkpoint corruption raises CheckpointCorruptionError (crash)

**Concerns:**
- **C9 (LOW): `ValueError` catch in `get_latest_checkpoint()` (line 176).** The Checkpoint dataclass constructor raises ValueError on invalid data. This is caught and re-raised as CheckpointCorruptionError. The catch is appropriate (Tier 1 crash-on-corruption), but the ValueError from a frozen dataclass constructor could theoretically come from any field validation, not just corruption. The error message could be more specific about which field failed.
- **C10 (LOW): No connection pooling awareness.** Each method opens a new connection via `self._db.engine.connect()` or `self._db.engine.begin()`. This is fine for SQLite but could be a concern for PostgreSQL backends where connection establishment is expensive. The LandscapeDB engine handles pooling, so this is mostly architectural consistency.

---

### 1.5 core/checkpoint/recovery.py (510 lines)

**Purpose:** `RecoveryManager` provides the resume protocol: checking if runs can be resumed, finding resume points, and identifying unprocessed rows.

**Key classes/functions:**
- `RecoveryManager`:
  - `can_resume()` -- Multi-step eligibility check: run status, checkpoint existence, topology compatibility, schema contract integrity.
  - `get_resume_point()` -- Returns ResumePoint with checkpoint, token/node IDs, sequence number, and deserialized aggregation state.
  - `get_unprocessed_rows()` -- Complex SQL query using token outcome semantics: delegation markers (FORKED, EXPANDED) are excluded from completion checks; buffered tokens from checkpoint state are handled carefully.
  - `get_unprocessed_row_data()` -- Retrieves actual row data with type fidelity restoration via Pydantic schema re-validation.
  - `verify_contract_integrity()` -- Tier 1 check: missing or corrupt schema contracts raise CheckpointCorruptionError.

**Dependencies:**
- `sqlalchemy` (select, Row)
- `elspeth.contracts` (PayloadStore, PluginSchema, ResumeCheck, ResumePoint, RowOutcome, RunStatus, SchemaContract)
- `elspeth.contracts.aggregation_checkpoint.AggregationCheckpointState`
- `elspeth.core.checkpoint.compatibility.CheckpointCompatibilityValidator`
- `elspeth.core.checkpoint.manager` (CheckpointCorruptionError, CheckpointManager, IncompatibleCheckpointError)
- `elspeth.core.checkpoint.serialization` (checkpoint_loads)
- `elspeth.core.landscape.database.LandscapeDB`
- `elspeth.core.landscape.recorder.LandscapeRecorder`
- `elspeth.core.landscape.schema` (rows_table, runs_table, token_outcomes_table, tokens_table)

**Architectural patterns:**
- Multi-step resume validation (status -> checkpoint -> topology -> contract)
- Fork/aggregation/coalesce-aware row completion semantics
- Type fidelity restoration: stored JSON -> Pydantic schema -> typed row data
- SQLite bind limit awareness (_METADATA_CHUNK_SIZE = 500)
- Mixed-state token handling: rows with both buffered and non-buffered incomplete tokens are NOT excluded

**Concerns:**
- **C11 (MEDIUM): `get_unprocessed_rows()` query complexity.** The SQL query uses 3 scalar subqueries, an outer join, and multiple OR conditions. While correct (documented with the fork/aggregation/coalesce recovery semantics), this is a complex query that's difficult to reason about and test. The function is 130+ lines including the buffered-token post-processing. Consider extracting the query construction into a named helper.
- **C12 (MEDIUM): Double checkpoint lookup in `get_resume_point()`.** `get_resume_point()` calls `can_resume()` which calls `get_latest_checkpoint()`, then `get_resume_point()` calls `get_latest_checkpoint()` again. This is two database queries for the same data. The checkpoint should be passed through or cached.
- **C13 (LOW): `LandscapeRecorder` instantiation in `verify_contract_integrity()`.** A new `LandscapeRecorder` is created each time this method is called (line 484). If the RecoveryManager already has access to a recorder, this is wasteful. If not, the dependency should be injected at construction time.

---

### 1.6 core/checkpoint/serialization.py (213 lines)

**Purpose:** Type-preserving JSON serialization for checkpoint aggregation state. Distinct from canonical_json (which is for hashing, not round-trip fidelity).

**Key classes/functions:**
- `CheckpointEncoder(json.JSONEncoder)` -- Encodes datetime using collision-safe type envelopes (`__elspeth_type__`/`__elspeth_value__`)
- `_reject_nan_infinity()` -- Recursive NaN/Infinity validation
- `_escape_reserved_keys()` -- Prevents user data containing `__elspeth_type__` from being misinterpreted
- `checkpoint_dumps()` -- Full serialization pipeline: validate -> escape -> encode
- `_restore_types()` -- Recursive type restoration from envelopes (datetime, escaped dicts)
- `checkpoint_loads()` -- Full deserialization: parse -> restore types

**Dependencies:**
- `json` (standard library)
- No ELSPETH-internal dependencies (leaf module)

**Architectural patterns:**
- Collision-safe type envelopes (not shape-based matching)
- NaN/Infinity rejection (defense-in-depth for audit integrity)
- Escape/unescape for reserved keys (user data containing `__elspeth_type__` is wrapped)
- No legacy format support (per No Legacy Code policy)

**Concerns:**
- **C14 (LOW): Docstring inconsistency.** `checkpoint_loads()` docstring says "Supports both new collision-safe envelopes and legacy __datetime__ tags" but the code explicitly does NOT support legacy tags (per the comment in `_restore_types()`). The docstring should be corrected.
- This module is well-designed. The collision-safe envelope approach is robust and the escape mechanism handles edge cases correctly.

---

### 1.7 core/checkpoint/compatibility.py (123 lines)

**Purpose:** `CheckpointCompatibilityValidator` validates that a checkpoint can be safely resumed with the current pipeline configuration by checking topological compatibility.

**Key classes/functions:**
- `CheckpointCompatibilityValidator`:
  - `validate()` -- Three checks: (1) checkpoint node exists, (2) node config unchanged, (3) full topology hash matches
  - `compute_full_topology_hash()` -- Delegates to `canonical.compute_full_topology_hash()`
  - `_create_topology_mismatch_error()` -- Detailed error message for hash mismatches

**Dependencies:**
- `structlog` (logging)
- `elspeth.contracts` (Checkpoint, ResumeCheck)
- `elspeth.core.canonical` (compute_full_topology_hash, stable_hash)
- `elspeth.core.dag.ExecutionGraph`

**Architectural patterns:**
- Single Responsibility: only topology validation (status checks are in RecoveryManager)
- Full DAG validation (BUG-COMPAT-01 fix: not upstream-only)
- Hash-based comparison (deterministic via canonical JSON)

**Concerns:**
- **C15 (LOW): `compute_full_topology_hash()` is a trivial delegation.** The method just calls `canonical.compute_full_topology_hash(graph)`. The indirection exists only because it was previously a different implementation (upstream-only). Consider removing the wrapper and calling the canonical function directly.
- This is a well-factored, focused module with no significant concerns.

---

### 1.8 core/config.py (2,073 lines)

**Purpose:** Configuration schema and loading for ELSPETH pipelines. Uses Pydantic for validation and Dynaconf for multi-source loading. The single largest file in the analysis scope.

**Key classes/functions:**
- **Settings models (Pydantic, frozen):**
  - `SecretsConfig` -- Secret loading configuration (env or Azure Key Vault)
  - `TriggerConfig` -- Aggregation trigger configuration (count, timeout, condition)
  - `AggregationSettings` -- Batching configuration with trigger, output mode, plugin
  - `GateSettings` -- Config-driven routing with condition expressions and route maps
  - `CoalesceSettings` -- Fork/join merge configuration (policy, merge strategy, timeout)
  - `SourceSettings` -- Source plugin with on_success routing
  - `TransformSettings` -- Transform plugin with name, input, on_success, on_error
  - `SinkSettings` -- Sink plugin configuration
  - `LandscapeSettings` -- Audit trail database configuration (SQLite/PostgreSQL/SQLCipher)
  - `ConcurrencySettings`, `RetrySettings`, `PayloadStoreSettings`, `CheckpointSettings`
  - `TelemetrySettings` + `ExporterSettings` -- Observability configuration
  - `ElspethSettings` -- Top-level settings aggregating all subsystems
- **Loading pipeline:**
  - `load_settings()` -- Dynaconf -> key normalization -> env var expansion -> template expansion -> Pydantic validation
  - `resolve_config()` -- Settings -> dict with secrets fingerprinted for audit storage
- **Utility functions:**
  - `_lowercase_schema_keys()` -- Context-aware key normalization (preserves user data in options/routes/branches)
  - `_expand_env_vars()` -- `${VAR}` and `${VAR:-default}` expansion
  - `_expand_config_templates()` -- template_file/lookup_file/system_prompt_file expansion
  - `_fingerprint_config_for_audit()` -- Secret fingerprinting across all plugin option dicts
  - `_fingerprint_secrets()` -- Recursive HMAC fingerprinting of secret fields
  - `_sanitize_dsn()` -- Database URL password removal/fingerprinting
  - `_resolve_template_path()` -- Path traversal prevention for template files

**Dependencies:**
- `pydantic` (BaseModel, Field, field_validator, model_validator)
- `yaml` (safe_load for YAML parsing and lookup files)
- `dynaconf` (multi-source configuration loading)
- `ast` (for trigger condition validation)
- `elspeth.contracts.enums` (OutputMode, RunMode)
- `elspeth.engine.expression_parser` (ExpressionParser for condition validation -- note: core depends on engine)
- `elspeth.core.security` (fingerprinting -- lazy import)

**Architectural patterns:**
- Pydantic frozen models for immutable validated config
- Dynaconf for multi-source precedence (env > file > defaults)
- Fail-fast validation: expression parsing, URL validation, name character restrictions
- Secret fingerprinting: HMAC-based for audit, with collision detection
- Template file expansion with path traversal prevention
- Context-aware key normalization (user data preserved)
- Extra="forbid" on all models (rejects unknown keys)

**Concerns:**
- **C16 (HIGH): core/config.py imports from engine/.** `TriggerConfig.validate_condition_expression()` and `GateSettings.validate_condition_expression()` import `elspeth.engine.expression_parser`. This creates a dependency from core -> engine, inverting the expected dependency direction (engine should depend on core, not vice versa). The ExpressionParser is used for config-time validation, which is reasonable, but the import direction is wrong. The ExpressionParser should either live in core/ or the validation should be deferred to the DAG builder (which already lives in the engine's dependency chain).
- **C17 (MEDIUM): File size.** At 2,073 lines, config.py handles settings models, loading pipeline, environment variable expansion, template expansion, secret fingerprinting, DSN sanitization, and key normalization. Many of these are distinct concerns that could be separated (e.g., `config_secrets.py`, `config_loading.py`, `config_templates.py`).
- **C18 (MEDIUM): `_lowercase_schema_keys()` complexity.** This function has 4 context flags (`_preserve_nested`, `_in_sinks`) and 8 branches for determining child processing behavior. The logic is correct but the complexity arises from Dynaconf's uppercase-key behavior interacting with case-sensitive user data. This is inherent complexity, but the function would benefit from a more explicit state machine approach.
- **C19 (LOW): `_DYNACONF_INTERNAL_KEYS` maintenance burden.** The allowlist of Dynaconf internal keys must be manually maintained. If Dynaconf adds new internal keys, they would be rejected as "unknown YAML keys." The YAML-only check (line 2029-2038) mitigates this somewhat, but the allowlist is still fragile.
- **C20 (LOW): Validation timing.** Expression validation happens in Pydantic field validators (config load time), which imports the engine's ExpressionParser. This means config loading triggers engine module initialization, potentially causing issues if the engine has heavy dependencies.

---

### 1.9 core/canonical.py (315 lines)

**Purpose:** Canonical JSON serialization for deterministic hashing. Two-phase approach: normalize (pandas/numpy) then serialize (RFC 8785/JCS).

**Key classes/functions:**
- `_normalize_value()` -- Single-value normalization (float, numpy, pandas, datetime, Decimal, bytes)
- `_normalize_for_canonical()` -- Recursive normalization (dicts, lists, PipelineRow)
- `canonical_json()` -- Two-phase: normalize -> RFC 8785 serialize
- `stable_hash()` -- SHA-256 of canonical JSON
- `compute_full_topology_hash()` -- Full DAG topology hash for checkpoint validation
- `_edge_to_canonical_dict()` -- Edge normalization for topology hashing
- `sanitize_for_canonical()` -- Tier 3 boundary: replaces NaN/Infinity with None
- `repr_hash()` -- Fallback hash for non-canonical data (quarantine path)
- `CANONICAL_VERSION` -- Version string for hash algorithm identification

**Dependencies:**
- `rfc8785` (RFC 8785/JCS canonical JSON)
- `numpy`
- `pandas`
- `hashlib` (SHA-256)
- `base64` (bytes encoding)
- `networkx` (for topology hashing)
- `elspeth.contracts.schema_contract.PipelineRow` (lazy import for circular dependency avoidance)
- `elspeth.core.dag.ExecutionGraph` (TYPE_CHECKING only)

**Architectural patterns:**
- Two-phase canonicalization (our normalization + standard JCS)
- Strict NaN/Infinity rejection (defense-in-depth)
- Separate sanitization path for Tier 3 data
- repr_hash fallback for non-serializable data
- Version-tagged hashing for forward compatibility

**Concerns:**
- **C21 (MEDIUM): Hard dependency on numpy and pandas.** `canonical.py` imports `numpy` and `pandas` at module level. These are heavy dependencies that force every import of canonical.py to load the scientific computing stack. If canonical_json is used for non-data purposes (e.g., config hashing in the builder), this is unnecessary overhead. Consider lazy imports for numpy/pandas normalization.
- **C22 (LOW): `_normalize_for_canonical()` imports PipelineRow inside the function.** This is a circular dependency avoidance pattern. The import happens on every call. Since canonical_json is called frequently (every row hash), this should be moved to module-level with TYPE_CHECKING guard and a runtime lazy import cache.
- **C23 (LOW): `sanitize_for_canonical()` uses module name sniffing.** Lines 285-287 check `type(obj).__module__ == "numpy"` as a way to detect numpy floats without importing numpy. This is fragile (would break if numpy reorganizes internals). Since numpy is already imported at module level, this check is unnecessary.
- **C24 (LOW): `compute_full_topology_hash()` lives in canonical.py.** This function knows about ExecutionGraph topology (nodes, edges, config hashes). It's a cross-cutting concern that bridges canonical JSON and DAG structure. It might be better placed in the DAG package as `graph.compute_topology_hash()` using `canonical.stable_hash()` as a primitive.

---

### 1.10 core/templates.py (265 lines)

**Purpose:** Jinja2 template field extraction for development assistance. Helps developers discover which fields their templates reference so they can declare them in `required_input_fields`.

**Key classes/functions:**
- `extract_jinja2_fields()` -- Extract field names from template (returns frozenset)
- `_walk_ast()` -- Recursive AST walker for Jinja2 parse tree
- `extract_jinja2_fields_with_details()` -- Enhanced version returning access type (attr/item)
- `extract_jinja2_fields_with_names()` -- Name resolution against SchemaContract (original/normalized)

**Dependencies:**
- `jinja2` (Environment, AST node types)
- `elspeth.contracts.schema_contract.SchemaContract` (TYPE_CHECKING only)

**Architectural patterns:**
- AST-based analysis (no template execution)
- Multiple API levels (basic -> detailed -> name-resolved)
- Development helper, not runtime component
- Documented limitations (conditional access, dynamic keys, macros)

**Concerns:**
- This module is clean and well-designed. No significant concerns.
- Minor: The `Environment()` is created fresh on each call. For repeated calls, a cached environment would be slightly more efficient, but since this is a development helper, performance is not critical.

---

### 1.11 core/identifiers.py (34 lines)

**Purpose:** Validation for field names used throughout ELSPETH. Ensures names are valid Python identifiers, not keywords, and not duplicates.

**Key classes/functions:**
- `validate_field_names()` -- Validates a list of field names (identifier check, keyword check, duplicate check)

**Dependencies:**
- `keyword` (standard library)

**Architectural patterns:**
- Utility function, no state
- Centralized validation to avoid duplication across subsystems

**Concerns:**
- This is a well-scoped utility module. No concerns.
- Note: The function checks `type(name) is not str` (exact type check, not isinstance). This is correct per CLAUDE.md prohibition on defensive patterns -- if a non-string arrives, that's a bug in our code.

---

### 1.12 core/events.py (112 lines)

**Purpose:** Synchronous event bus for pipeline observability. Provides clean separation between domain logic (orchestrator) and presentation (CLI formatters).

**Key classes/functions:**
- `EventBusProtocol` -- Protocol for event bus implementations
- `EventBus` -- Production implementation: synchronous dispatch, exceptions propagate
- `NullEventBus` -- No-op implementation for library/testing use

**Dependencies:**
- None (standard library only)

**Architectural patterns:**
- Protocol-based design (EventBusProtocol)
- Null Object pattern (NullEventBus)
- Synchronous dispatch (handlers run in subscription order)
- Handlers are "our code" -- exceptions propagate (no try/except swallowing)
- NullEventBus deliberately does NOT inherit from EventBus (prevents substitution bugs)

**Concerns:**
- This is exceptionally well-designed. The explicit non-inheritance of NullEventBus with documented rationale is a textbook example of principled design.
- Minor: `_subscribers` dict uses `type` as key, which means subclass events won't be dispatched to parent class subscribers. This is intentional (event types are concrete) but worth noting.

---

## 2. Cross-Cutting Analysis

### 2.1 How DAG Construction Works (YAML Config -> Executable Graph)

The flow from YAML to executable graph is:

```
YAML file
  -> Dynaconf (multi-source loading, env var merge)
    -> _lowercase_schema_keys() (key normalization)
      -> _expand_env_vars() (${VAR} expansion)
        -> _expand_config_templates() (template_file expansion)
          -> ElspethSettings(**raw_config) (Pydantic validation)
            -> instantiate_plugins_from_config() (plugin instantiation)
              -> ExecutionGraph.from_plugin_instances() (facade)
                -> builder.build_execution_graph() (actual construction)
```

The builder performs these phases sequentially:
1. **Node creation:** Source, sinks, transforms, aggregations, gates, coalesce
2. **ID generation:** Deterministic via canonical_json + SHA-256 (for checkpoint compatibility)
3. **Producer/consumer registry:** Build connection maps for wiring validation
4. **Fork branch wiring:** Connect fork gates to coalesce or sink destinations
5. **Connection namespace validation:** No duplicates, no dangling, disjoint from sinks
6. **Schema resolution (pass 1):** Gate schema from upstream producer
7. **Edge creation:** Match producers to consumers, handle gate route labels
8. **Terminal routing:** on_success edges to sinks
9. **Divert edges:** Quarantine/error sink connections
10. **Topological sort:** NetworkX validates acyclicity and produces execution order
11. **Coalesce schema population:** Strategy-aware merge schema computation
12. **Schema resolution (pass 2):** Deferred gate schemas (post-coalesce)
13. **Schema compatibility validation (Phase 2):** Cross-plugin type checking
14. **Config freezing:** MappingProxyType wrapping of all NodeInfo configs
15. **Pipeline node sequence + step map:** Ordered processing nodes for audit trail

**Assessment:** The construction process is thorough and well-validated. The two-pass schema resolution handles the chicken-and-egg problem of gates depending on coalesce nodes. The explicit fail-fast approach (no fallback behavior) is correct for high-stakes pipelines.

---

### 2.2 How Checkpoint/Recovery Works

The crash recovery model follows this protocol:

**Checkpoint Creation (during run):**
```
CheckpointManager.create_checkpoint()
  -> Within transaction:
    -> Generate checkpoint_id (UUID)
    -> Compute full topology hash (canonical JSON of all nodes + edges)
    -> Compute node config hash (canonical JSON of current node's config)
    -> Serialize aggregation state (checkpoint_dumps with type envelopes)
    -> INSERT into checkpoints_table
  -> Return Checkpoint dataclass
```

**Resume Eligibility Check:**
```
RecoveryManager.can_resume(run_id, graph)
  -> Check run status (must be FAILED or INTERRUPTED, not COMPLETED/RUNNING)
  -> Load latest checkpoint (validates format version)
  -> CheckpointCompatibilityValidator.validate():
    -> Node exists in current graph?
    -> Node config hash matches?
    -> Full topology hash matches? (any change = incompatible)
  -> verify_contract_integrity() (schema contract present and hash-valid)
```

**Resume Execution:**
```
RecoveryManager.get_resume_point(run_id, graph)
  -> can_resume() check (redundant checkpoint load -- see C12)
  -> Deserialize aggregation state (checkpoint_loads with type restoration)
  -> Return ResumePoint (checkpoint, token_id, node_id, sequence, agg state)

RecoveryManager.get_unprocessed_rows(run_id)
  -> Complex SQL: find rows without terminal outcomes for all leaf tokens
  -> Exclude rows whose all incomplete tokens are buffered in checkpoint

RecoveryManager.get_unprocessed_row_data(run_id, payload_store, source_schema_class)
  -> For each unprocessed row:
    -> Retrieve payload from PayloadStore
    -> Re-validate through source Pydantic schema (type fidelity restoration)
    -> Return (row_id, row_index, row_data) tuples
```

**Key design decisions:**
- Full topology validation (not upstream-only) enforces "one run = one config"
- Type fidelity restoration is REQUIRED (no fallback to degraded types)
- Format version check rejects both older AND newer versions
- Missing schema contract = corruption (Tier 1 crash)
- Fork/aggregation/coalesce-aware completion semantics (delegation markers excluded)

---

### 2.3 Configuration Architecture

The two-layer Settings -> Runtime*Config pattern documented in CLAUDE.md is partially visible in this analysis:

**Layer 1 (config.py):** Pydantic models validate YAML input. All models use `frozen=True` and `extra="forbid"`. Validation includes expression parsing, name restrictions, policy requirements, and cross-field consistency checks.

**Layer 2 (contracts/config/runtime.py):** Runtime*Config dataclasses (not in scope of this analysis but referenced). These are consumed by engine components and satisfy Protocol interfaces.

**The gap:** config.py is the entry point for Layer 1. The `from_settings()` conversion to Layer 2 happens elsewhere (in contracts/config/runtime.py). The enforcement chain (Protocol + AST checker + alignment tests) ensures no field is silently dropped during conversion.

**Loading pipeline specifics:**
1. Dynaconf loads YAML + env vars with merge
2. Keys are normalized (context-aware lowercasing)
3. Environment variables expanded
4. Template files loaded (with path traversal protection)
5. Pydantic validates everything
6. `resolve_config()` creates an audit-safe copy with fingerprinted secrets

---

### 2.4 Canonical JSON (RFC 8785 Two-Phase)

**Phase 1 (our code):** `_normalize_for_canonical()` handles Python ecosystem types:
- `numpy.int64` -> `int`, `numpy.float64` -> `float` (with NaN/Infinity rejection)
- `pandas.Timestamp` -> UTC ISO 8601 string (naive timestamps assumed UTC)
- `NaT`/`pd.NA` -> `None`
- `datetime` -> UTC ISO 8601 string
- `Decimal` -> string (with non-finite rejection)
- `bytes` -> `{"__bytes__": base64}`
- `PipelineRow` -> `dict` (via `to_dict()`)
- `numpy.ndarray` -> list (with element-wise NaN/Infinity check)

**Phase 2 (rfc8785):** Standard JCS serialization produces deterministic output:
- Sorted keys
- No whitespace
- Specific float representation

**Used for:**
- Row hashing (every source row)
- Config hashing (DAG node IDs)
- Topology hashing (checkpoint compatibility)
- Audit record hashing

---

### 2.5 Cross-Cutting Dependencies

```
core/config.py
  -> engine/expression_parser.py  [INVERTED DEPENDENCY - C16]
  -> core/security/ (lazy)

core/dag/builder.py
  -> core/canonical.py
  -> core/dag/models.py
  -> contracts/ (types, enums, schema)

core/dag/graph.py
  -> core/dag/models.py
  -> contracts/ (types, enums, schema, compatibility)
  -> core/dag/builder.py (lazy import for from_plugin_instances)

core/canonical.py
  -> numpy, pandas (module-level)
  -> rfc8785
  -> networkx (for topology hashing)
  -> contracts/schema_contract.PipelineRow (lazy)
  -> core/dag.ExecutionGraph (TYPE_CHECKING)

core/checkpoint/manager.py
  -> core/canonical.py
  -> core/checkpoint/serialization.py
  -> core/landscape/ (database, schema)
  -> contracts/ (Checkpoint)

core/checkpoint/recovery.py
  -> core/checkpoint/manager.py
  -> core/checkpoint/compatibility.py
  -> core/checkpoint/serialization.py
  -> core/landscape/ (database, recorder, schema)
  -> contracts/ (multiple types)

core/checkpoint/compatibility.py
  -> core/canonical.py
  -> core/dag.ExecutionGraph
  -> contracts/ (Checkpoint, ResumeCheck)

core/templates.py
  -> jinja2
  -> contracts/schema_contract.SchemaContract (TYPE_CHECKING)

core/identifiers.py
  -> (none)

core/events.py
  -> (none)
```

**Key observations:**
- `core/canonical.py` is a critical dependency (used by DAG builder, checkpoint manager, compatibility validator, topology hashing)
- The inverted dependency from `core/config.py` to `engine/expression_parser.py` is the most significant coupling issue
- `core/checkpoint/` forms a cohesive subsystem with clear internal layering (serialization -> manager -> recovery -> compatibility)
- `core/events.py` and `core/identifiers.py` are true leaf modules with no internal dependencies

---

## 3. Concerns and Recommendations (Ranked by Severity)

### HIGH

**H1: Inverted dependency: core/config.py -> engine/expression_parser.py (C16)**
- **Impact:** Violates the dependency direction principle (core should not depend on engine)
- **Risk:** Engine initialization triggered during config loading; future engine changes could break config parsing
- **Recommendation:** Move `ExpressionParser` to `core/expressions.py` or defer expression validation to DAG construction time (the builder already has access to everything needed)

**H2: Monolithic builder function (C5)**
- **Impact:** 830 lines of sequential logic with closures; impossible to unit-test individual phases
- **Risk:** Future DAG features (new node types, new routing modes) will make this worse
- **Recommendation:** Refactor to a `DAGBuilder` class with named methods for each phase. The sequential dependency between phases can be enforced by a `build()` method that calls them in order. Individual phase methods become testable.

### MEDIUM

**M1: God class tendency in ExecutionGraph (C1)**
- **Impact:** 1,452 lines spanning construction, queries, traversal, schema validation, route resolution
- **Recommendation:** Extract `SchemaValidator` and `RouteResolver` as collaborator classes. ExecutionGraph becomes a thin wrapper that delegates to these.

**M2: config.py file size (C17)**
- **Impact:** 2,073 lines mixing settings models, loading pipeline, secret handling, template expansion
- **Recommendation:** Split into `config_models.py` (Pydantic models), `config_loading.py` (Dynaconf + env + templates), `config_secrets.py` (fingerprinting + DSN sanitization)

**M3: Double checkpoint lookup in get_resume_point() (C12)**
- **Impact:** Unnecessary database query on the resume path
- **Recommendation:** Cache the checkpoint from `can_resume()` or pass it through

**M4: Recovery SQL query complexity (C11)**
- **Impact:** 130+ line method with complex SQL subqueries
- **Recommendation:** Extract query construction into a named helper; add comprehensive SQL-level comments

**M5: Private attribute access across module boundary (C6)**
- **Impact:** `getattr(transform, "_output_schema_config", None)` in builder.py
- **Recommendation:** Add `output_schema_config` property to TransformProtocol or as an optional protocol method

**M6: Hard numpy/pandas dependency in canonical.py (C21)**
- **Impact:** Module-level imports force scientific stack loading for any canonical.py user
- **Recommendation:** Lazy-import numpy/pandas in `_normalize_value()` with a module-level cache

### LOW

C7 (assert in production), C8 (hash collision documentation), C9 (ValueError catch specificity), C10 (connection pooling), C13 (LandscapeRecorder instantiation), C14 (docstring inconsistency), C15 (trivial delegation), C18 (_lowercase_schema_keys complexity), C19 (Dynaconf allowlist maintenance), C20 (validation timing), C22 (PipelineRow lazy import), C23 (module name sniffing), C24 (topology hash placement), C2 (mutable setters), C3 (repeated iteration), C4 (frozen copy cost)

---

## 4. Tier Model Compliance

### Checkpoint Data (Tier 1 -- Our Data)

The checkpoint subsystem is **largely compliant** with the Tier 1 trust model:

**Correct patterns observed:**
- `CheckpointCorruptionError` is raised for any data integrity issue (crash on corruption)
- `_validate_checkpoint_compatibility()` rejects both older and newer format versions
- `verify_contract_integrity()` treats missing contracts as corruption (no backward compatibility)
- Aggregation state serialization rejects NaN/Infinity
- Topology hash comparison uses full DAG (no partial validation)
- ValueError from Checkpoint dataclass construction is caught and re-raised as CheckpointCorruptionError

**No violations detected.** The checkpoint subsystem correctly treats its own stored data as Tier 1 and crashes on any anomaly.

### DAG/Config (Tier 1 -- Our Data)

**Correct patterns observed:**
- `NodeInfo.config` is frozen after construction (MappingProxyType)
- Graph validation raises `GraphValidationError` on any structural issue
- Node ID length is enforced in `__post_init__`
- Schema compatibility violations raise errors (not warnings)
- Edge data is accessed directly (no `.get()` with defaults)
- Comment in `_edge_to_canonical_dict()`: "Edge data is Tier 1 (Our Data) -- crash on missing/wrong attributes"

**One potential concern:** `NodeConfig = dict[str, Any]` means node configs are untyped at the graph layer. The individual plugins validate their own configs via Pydantic, but the graph layer treats them as opaque dicts. This is documented as intentional but means the graph layer cannot detect config corruption -- it relies on plugin validation being correct. This is acceptable given that plugins are system-owned code.

---

## 5. Overall Assessment

### Strengths

1. **Deterministic node IDs** via canonical JSON hashing enable checkpoint/resume across restarts. This is a critical correctness property.

2. **Two-phase schema validation** (Phase 1: plugin self-validation at construction, Phase 2: cross-plugin compatibility in builder) catches incompatibilities before runtime.

3. **Full topology hashing** for checkpoint compatibility enforces "one run = one config" invariant.

4. **Type fidelity restoration** in recovery ensures resumed rows have correct types (not degraded strings from JSON round-trip).

5. **Collision-safe type envelopes** in checkpoint serialization prevent user data from being misinterpreted as type tags.

6. **Fork/aggregation/coalesce-aware recovery** correctly handles delegation markers and mixed-state tokens.

7. **Explicit routing** (no default_sink fallback) prevents silent configuration bugs.

8. **Frozen configs** (MappingProxyType) after construction prevent accidental mutation.

9. **Event bus design** (Protocol-based, non-inheriting NullEventBus) is textbook-quality.

### Weaknesses

1. **builder.py is a monolithic function** that's difficult to test in isolation.
2. **config.py is oversized** and mixes multiple concerns.
3. **Inverted dependency** from core -> engine for expression validation.
4. **ExecutionGraph** has too many responsibilities.
5. **Double checkpoint lookup** on the resume path.

### Confidence

**HIGH.** The analysis covers all 12 files completely. The concerns identified are based on direct code inspection and cross-referencing of dependencies, patterns, and CLAUDE.md requirements. The Tier 1 compliance assessment is based on systematic checking of error handling patterns at all data access points.

---

## 6. Summary Table

| File | Lines | Role | Primary Concern | Severity |
|------|-------|------|-----------------|----------|
| core/dag/models.py | 137 | Leaf types | _GateEntry missing slots=True | LOW |
| core/dag/graph.py | 1,452 | Graph wrapper | God class tendency | MEDIUM |
| core/dag/builder.py | 938 | Graph construction | Monolithic function | HIGH |
| core/checkpoint/manager.py | 267 | Checkpoint CRUD | None significant | LOW |
| core/checkpoint/recovery.py | 510 | Resume protocol | SQL complexity, double lookup | MEDIUM |
| core/checkpoint/serialization.py | 213 | Type-preserving JSON | Docstring inconsistency | LOW |
| core/checkpoint/compatibility.py | 123 | Topology validation | Trivial delegation | LOW |
| core/config.py | 2,073 | Config validation+loading | Inverted dependency, file size | HIGH |
| core/canonical.py | 315 | Deterministic hashing | numpy/pandas hard dependency | MEDIUM |
| core/templates.py | 265 | Jinja2 field extraction | None | CLEAN |
| core/identifiers.py | 34 | Name validation | None | CLEAN |
| core/events.py | 112 | Event bus | None | CLEAN |
