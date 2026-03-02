# Architecture Analysis: contracts/ Subsystem

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Analyst:** Claude Opus 4.6
**Files analyzed:** 37 Python files (4 in contracts/config/, 33 in contracts/ root)

---

## Per-File Analysis

### contracts/config/ (4 files)

#### contracts/config/alignment.py
- **Purpose:** Machine-readable documentation of Settings-to-Runtime field name mappings. Enables AST checker and test verification that all Settings fields reach runtime.
- **Key types:** `FIELD_MAPPINGS` (Final dict), `SETTINGS_TO_RUNTIME` (Final dict), `EXEMPT_SETTINGS` (Final set), `RUNTIME_TO_SUBSYSTEM` (Final dict). Helper functions: `get_runtime_field_name()`, `get_settings_field_name()`, `is_exempt_settings()`.
- **Frozen vs mutable:** No dataclasses. All module-level constants are `Final` (immutable by convention).
- **Dependencies:** Only `typing.Final`. Pure data module.
- **Completeness:** Covers 5 Settings-to-Runtime pairs. TelemetrySettings exporter rename documented. EXEMPT_SETTINGS comprehensive (16 entries). Clean and well-structured.

#### contracts/config/defaults.py
- **Purpose:** Default value registries for runtime configuration. Two categories: INTERNAL_DEFAULTS (hardcoded, not in Settings) and POLICY_DEFAULTS (for plugin RetryPolicy).
- **Key types:** `INTERNAL_DEFAULTS` (Final dict), `POLICY_DEFAULTS` (Final dict). Helper functions: `get_internal_default()`, `get_policy_default()`.
- **Frozen vs mutable:** No dataclasses. Constants are `Final`.
- **Dependencies:** Only `typing.Final`. Pure data module.
- **Completeness:** INTERNAL_DEFAULTS has 2 subsystems (retry, telemetry). POLICY_DEFAULTS has 5 fields. Documented self-referentially with design rationale. Note: Comment says POLICY_DEFAULTS duplicated from engine/retry.py but should be authoritative source here.

#### contracts/config/protocols.py
- **Purpose:** Runtime protocols defining what engine components EXPECT from configuration. Enables structural typing verification with mypy.
- **Key types:** `RuntimeRetryProtocol`, `ServiceRateLimitProtocol`, `RuntimeRateLimitProtocol`, `RuntimeConcurrencyProtocol`, `RuntimeCheckpointProtocol`, `RuntimeTelemetryProtocol`. All `@runtime_checkable`.
- **Frozen vs mutable:** N/A (Protocol classes, not instantiated).
- **Dependencies:** `typing.Protocol`, `typing.runtime_checkable`. TYPE_CHECKING imports for `ExporterConfig`, `BackpressureMode`, `TelemetryGranularity`.
- **Completeness:** All 5 Runtime*Config classes have corresponding protocols. Property-based interface. Well-documented field origins.

#### contracts/config/runtime.py
- **Purpose:** Frozen dataclasses implementing Runtime*Protocol interfaces, with factory methods (`from_settings()`, `from_policy()`, `default()`, `no_retry()`).
- **Key types:** `RuntimeRetryConfig`, `RuntimeRateLimitConfig`, `RuntimeConcurrencyConfig`, `RuntimeCheckpointConfig`, `ExporterConfig`, `RuntimeTelemetryConfig`. Helper functions: `_merge_policy_with_defaults()`, `_validate_int_field()`, `_validate_float_field()`.
- **Frozen vs mutable:** ALL dataclasses are `frozen=True, slots=True`. Excellent.
- **Dependencies:** `math`, `collections.abc.Mapping`, `types.MappingProxyType`, contracts/config/defaults, contracts/engine (RetryPolicy), contracts/enums. Lazy imports for Settings classes to preserve leaf boundary.
- **Completeness:** All 6 runtime configs present. `from_settings()` methods with explicit field mapping. Validation in `__post_init__`. `ExporterConfig.options` frozen via MappingProxyType snapshot. `RuntimeRetryConfig.from_policy()` validates/coerces external data with clear error messages. Clean separation of concerns.

### contracts/ root (33 files)

#### contracts/aggregation_checkpoint.py
- **Purpose:** Three-level typed checkpoint state for aggregation buffers, replacing `dict[str, Any]`.
- **Key types:** `AggregationTokenCheckpoint`, `AggregationNodeCheckpoint`, `AggregationCheckpointState`. All with `to_dict()`/`from_dict()` for wire format compatibility.
- **Frozen vs mutable:** All three are `frozen=True, slots=True`.
- **Dependencies:** Only `dataclasses`, `typing.Any`.
- **Completeness:** Full three-level hierarchy (state -> node -> token). `from_dict()` methods crash on corruption (Tier 1). **Issue:** `AggregationNodeCheckpoint.from_dict()` uses `.get()` for `count_fire_offset` and `condition_fire_offset` (line 164-165), which is inconsistent with the Tier 1 crash-on-corruption policy -- these should either be required fields or explicitly documented as optional with a comment explaining why `.get()` is appropriate.

#### contracts/audit.py
- **Purpose:** Audit trail contracts for all Landscape tables. The heart of Tier 1 data integrity.
- **Key types:** `Run`, `Node`, `Edge`, `Row`, `Token`, `TokenParent`, `NodeStateOpen`, `NodeStatePending`, `NodeStateCompleted`, `NodeStateFailed` (discriminated union as `NodeState`), `Call`, `Artifact`, `RoutingEvent`, `Batch`, `BatchMember`, `BatchOutput`, `Checkpoint`, `RowLineage`, `ExportStatusUpdate` (TypedDict), `BatchStatusUpdate` (TypedDict), `ValidationErrorRecord`, `NonCanonicalMetadata`, `TransformErrorRecord`, `TokenOutcome`, `Operation`, `SecretResolution`.
- **Frozen vs mutable:** MIXED. NodeState variants are `frozen=True`. `NonCanonicalMetadata`, `TokenOutcome`, `Operation`, `SecretResolution` are `frozen=True, slots=True`. **CONCERN:** `Run`, `Node`, `Edge`, `Row`, `Token`, `TokenParent`, `Call`, `Artifact`, `RoutingEvent`, `Batch`, `BatchMember`, `BatchOutput`, `Checkpoint`, `RowLineage`, `ValidationErrorRecord`, `TransformErrorRecord` are all **mutable** (no `frozen=True`). These are Tier 1 audit records that should be immutable after creation.
- **Dependencies:** `dataclasses`, `datetime`, `typing`, `contracts/enums` (13 enum imports).
- **Completeness:** Comprehensive coverage of all Landscape tables. Enum validation in `__post_init__`. `_validate_enum()` helper ensures Tier 1 crash behavior. `Operation` has lifecycle invariant validation. `SecretResolution` has thorough fingerprint format validation. The `NodeState` discriminated union using `Literal` type narrowing is elegant.

#### contracts/batch_checkpoint.py
- **Purpose:** Typed checkpoint state for Azure Batch LLM transforms, replacing `dict[str, Any]`.
- **Key types:** `RowMappingEntry`, `BatchCheckpointState`.
- **Frozen vs mutable:** Both `frozen=True, slots=True`.
- **Dependencies:** Only `dataclasses`, `typing.Any`.
- **Completeness:** Clean Tier 1 deserialization with direct key access (crash on corruption). Wire-format compatible with previous untyped dict.

#### contracts/call_data.py
- **Purpose:** Frozen dataclasses for LLM and HTTP call audit data, replacing 23+ `dict[str, Any]` construction sites.
- **Key types:** `CallPayload` (Protocol), `RawCallPayload`, `LLMCallRequest`, `LLMCallResponse`, `LLMCallError`, `HTTPCallRequest`, `HTTPCallResponse`, `HTTPCallError`.
- **Frozen vs mutable:** All 7 dataclasses are `frozen=True, slots=True`.
- **Dependencies:** `contracts/token_usage.TokenUsage`.
- **Completeness:** Excellent. Covers all three phases of LLM and HTTP calls (request, response, error). `LLMCallRequest.extra_kwargs` collision detection prevents audit field overwriting. `HTTPCallRequest` handles standard, SSRF-safe, and redirect hop variants. `RawCallPayload` bridges pre-serialized dicts from PluginContext. `raw_response` on `LLMCallResponse` is intentionally `dict[str, Any]` (Tier 3 SDK data). `CallPayload` protocol enables structural subtyping.

#### contracts/checkpoint.py
- **Purpose:** Checkpoint and recovery domain contracts (not persisted to audit trail).
- **Key types:** `ResumeCheck`, `ResumePoint`.
- **Frozen vs mutable:** `ResumeCheck` is `frozen=True`. `ResumePoint` is **mutable** (just `@dataclass`).
- **Dependencies:** `contracts/aggregation_checkpoint.AggregationCheckpointState`, `contracts/audit.Checkpoint`.
- **Completeness:** `ResumeCheck` has good invariant enforcement (reason required for can_resume=False). `ResumePoint` validates aggregation_state type. **Issue:** `ResumePoint` should probably be frozen since it represents a point-in-time snapshot.

#### contracts/cli.py
- **Purpose:** CLI-related type contracts for pipeline execution results and progress events.
- **Key types:** `ProgressEvent` (frozen), `ExecutionResult` (TypedDict).
- **Frozen vs mutable:** `ProgressEvent` is `frozen=True`. `ExecutionResult` is a TypedDict (inherently immutable at type level).
- **Dependencies:** `contracts/enums.RunStatus`.
- **Completeness:** Clean and focused. `ExecutionResult` uses `RunStatus` enum (not string) for status field.

#### contracts/coalesce_metadata.py
- **Purpose:** Typed metadata for coalesce merge/failure audit records, replacing 4 `dict[str, Any]` sites.
- **Key types:** `ArrivalOrderEntry`, `CoalesceMetadata`.
- **Frozen vs mutable:** Both `frozen=True, slots=True`.
- **Dependencies:** `dataclasses.replace`, `types.MappingProxyType`.
- **Completeness:** Comprehensive factory methods for all 4 coalesce scenarios (late_arrival, failure, select_not_arrived, merge). `with_collisions()` uses `dataclasses.replace()` for immutable updates. Immutable collections via `tuple` and `MappingProxyType`.

#### contracts/contract_builder.py
- **Purpose:** Contract builder for first-row inference and locking (OBSERVED/FLEXIBLE mode).
- **Key types:** `ContractBuilder` (mutable class, not dataclass).
- **Frozen vs mutable:** Mutable (manages state through first-row inference). This is appropriate -- it's a builder pattern.
- **Dependencies:** `contracts/schema_contract.SchemaContract`.
- **Completeness:** Handles unsupported types gracefully (falls back to `object()`). Locks contract after first row.

#### contracts/contract_propagation.py
- **Purpose:** Contract propagation through transform pipeline. Handles field addition, removal, and renaming.
- **Key types:** Functions: `propagate_contract()`, `narrow_contract_to_output()`, `merge_contract_with_output()`.
- **Frozen vs mutable:** N/A (pure functions operating on immutable SchemaContract).
- **Dependencies:** `structlog`, `contracts/schema_contract`, `contracts/type_normalization`.
- **Completeness:** Three distinct propagation modes. `narrow_contract_to_output()` handles field renames with metadata preservation. `merge_contract_with_output()` preserves original names from input. **Note:** TODO comment on line 104 about extracting shared inference logic.

#### contracts/contract_records.py
- **Purpose:** Bridge between SchemaContract (runtime) and Landscape storage (JSON serialization). Audit records for schema contracts.
- **Key types:** `FieldAuditRecord`, `ContractAuditRecord`, `ValidationErrorWithContract`.
- **Frozen vs mutable:** All three are `frozen=True, slots=True`.
- **Dependencies:** `contracts/errors` (violation types), `contracts/type_normalization.CONTRACT_TYPE_MAP`.
- **Completeness:** Full round-trip serialization with integrity verification via hash. `from_json()` validates modes and sources. `to_schema_contract()` verifies hash on restore (Tier 1 requirement). `ValidationErrorWithContract` bridges violation types to audit records.

#### contracts/data.py
- **Purpose:** Pydantic-based schema system for plugins. PluginSchema base class with runtime validation.
- **Key types:** `PluginSchema` (Pydantic BaseModel), `SchemaValidationError`, `CompatibilityResult`, functions: `validate_row()`, `check_compatibility()`.
- **Frozen vs mutable:** `PluginSchema` is mutable (frozen=False, per Tier 3 trust). `CompatibilityResult` is a mutable dataclass.
- **Dependencies:** `pydantic`, type annotation utilities.
- **Completeness:** Thorough compatibility checking with Union type handling, Annotated unwrapping, and strict mode support. `_types_compatible()` handles numeric coercion rules per Data Manifesto. **Note:** `hasattr(t, "__name__")` in `_type_name()` (line 225) -- this is at a framework boundary (type introspection) so is legitimate.

#### contracts/engine.py
- **Purpose:** Engine-related type contracts (PendingOutcome and RetryPolicy).
- **Key types:** `PendingOutcome` (frozen dataclass), `RetryPolicy` (TypedDict, total=False).
- **Frozen vs mutable:** `PendingOutcome` is `frozen=True, slots=True`. `RetryPolicy` is a TypedDict.
- **Dependencies:** `contracts/enums.RowOutcome`.
- **Completeness:** Small, focused. `PendingOutcome` documents the durability-before-outcome pattern clearly.

#### contracts/enums.py
- **Purpose:** All status codes, modes, and kinds used across subsystem boundaries.
- **Key types:** 15 StrEnums: `RunStatus`, `NodeStateStatus`, `ExportStatus`, `BatchStatus`, `TriggerType`, `NodeType`, `Determinism`, `RoutingKind`, `RoutingMode`, `RowOutcome`, `CallType`, `CallStatus`, `RunMode`, `TelemetryGranularity`, `BackpressureMode`, `OutputMode`. Plus `_IMPLEMENTED_BACKPRESSURE_MODES` (frozenset) and `error_edge_label()` function.
- **Frozen vs mutable:** All StrEnums are inherently immutable.
- **Dependencies:** Only `enum.StrEnum`.
- **Completeness:** Comprehensive. StrEnum enables direct DB storage via `.value`. `RowOutcome.is_terminal` property is clean. `Determinism` enum enforces "no unknown" policy. `error_edge_label()` prevents label drift between DAG construction and audit recording.

#### contracts/errors.py
- **Purpose:** Error types, reason schemas, and control-flow exceptions. The largest file in contracts (878 lines).
- **Key types:** TypedDicts: `ExecutionError`, `CoalesceFailureReason`, `ConfigGateReason`, `TransformSuccessReason`, `TemplateErrorEntry`, `RowErrorEntry`, `UsageStats`, `QueryFailureDetail`, `ErrorDetail`, `TransformErrorReason`, `SourceQuarantineReason`. Literal types: `TransformActionCategory`, `TransformErrorCategory`. Exceptions: `BatchPendingError`, `GracefulShutdownError`, `AuditIntegrityError`, `OrchestrationInvariantError`, `FrameworkBugError`, `PluginContractViolation`. Contract violations: `ContractViolation`, `MissingFieldViolation`, `TypeMismatchViolation`, `ExtraFieldViolation`, `ContractMergeError`. Union: `RoutingReason`. Function: `violations_to_error_reason()`.
- **Frozen vs mutable:** N/A for TypedDicts and exceptions.
- **Dependencies:** TYPE_CHECKING for `BatchCheckpointState`.
- **Completeness:** Very thorough. `TransformErrorReason` is massive (80+ fields) covering every possible error context. `TransformErrorCategory` Literal has 40+ categories. Exception hierarchy well-organized: control flow (BatchPendingError, GracefulShutdownError), framework bugs (FrameworkBugError, OrchestrationInvariantError), audit integrity (AuditIntegrityError), plugin bugs (PluginContractViolation), data violations (ContractViolation hierarchy). **CONCERN:** `TransformErrorReason` TypedDict has grown organically and has too many optional fields. This is essentially `dict[str, Any]` with documentation. Consider splitting into discriminated sub-types by error category.

#### contracts/events.py
- **Purpose:** Observability events for pipeline execution. Consumed by CLI formatters and telemetry exporters.
- **Key types:** Enums: `PipelinePhase`, `PhaseAction`, `RunCompletionStatus`. Dataclasses: `PhaseStarted`, `PhaseCompleted`, `PhaseError`, `RunSummary`, `TelemetryEvent` (base), `TransformCompleted`, `GateEvaluated`, `TokenCompleted`, `RunStarted`, `RunFinished`, `PhaseChanged`, `FieldResolutionApplied`, `RowCreated`, `ExternalCallCompleted`. Helper: `_event_field_to_serializable()`.
- **Frozen vs mutable:** ALL event dataclasses are `frozen=True, slots=True`. Excellent.
- **Dependencies:** `copy`, `dataclasses`, `datetime`, `enum.StrEnum`, `types.MappingProxyType`, contracts/call_data, contracts/enums, contracts/token_usage.
- **Completeness:** Comprehensive lifecycle, row-level, and external call events. `FieldResolutionApplied` snapshots and freezes mapping. `ExternalCallCompleted` validates XOR constraint (state_id vs operation_id). Custom `to_dict()` handles MappingProxyType serialization that `dataclasses.asdict()` cannot. `_event_field_to_serializable()` handles recursive serialization.

#### contracts/header_modes.py
- **Purpose:** Sink header mode resolution (NORMALIZED, ORIGINAL, CUSTOM).
- **Key types:** `HeaderMode` (Enum), functions: `parse_header_mode()`, `resolve_headers()`.
- **Frozen vs mutable:** `HeaderMode` is inherently immutable.
- **Dependencies:** TYPE_CHECKING for `SchemaContract`.
- **Completeness:** Clean bridge between SchemaContract original names and sink output. Three modes cover all use cases.

#### contracts/identity.py
- **Purpose:** Token identity and data carrier for DAG traversal.
- **Key types:** `TokenInfo`.
- **Frozen vs mutable:** `frozen=True, slots=True`. Uses `replace()` for immutable updates.
- **Dependencies:** `contracts/schema_contract.PipelineRow`.
- **Completeness:** Clean. `with_updated_data()` preserves all lineage fields. All fork/join/expand group IDs present.

#### contracts/node_state_context.py
- **Purpose:** Typed node state context metadata for the Landscape audit trail. Replaces `dict[str, Any]` in executor code.
- **Key types:** `NodeStateContext` (Protocol), `PoolConfigSnapshot`, `PoolStatsSnapshot`, `QueryOrderEntry`, `PoolExecutionContext`, `GateEvaluationContext`, `AggregationFlushContext`.
- **Frozen vs mutable:** All 6 dataclasses are `frozen=True, slots=True`. Protocol is not runtime_checkable (mypy only).
- **Dependencies:** TYPE_CHECKING for `TransformResult`, `BufferEntry`.
- **Completeness:** Good coverage. `from_executor_stats()` is Tier 1 factory with direct key access. All types have `to_dict()`. **Note:** `AggregationFlushContext.trigger_type` is `str` rather than `TriggerType` enum -- inconsistent with audit.py's `Batch.trigger_type`.

#### contracts/payload_store.py
- **Purpose:** PayloadStore protocol for content-addressable blob storage.
- **Key types:** `IntegrityError` (Exception), `PayloadStore` (Protocol, runtime_checkable).
- **Frozen vs mutable:** N/A.
- **Dependencies:** Only `typing`.
- **Completeness:** Clean protocol with store/retrieve/exists/delete. `IntegrityError` for hash mismatch detection. Consolidated from multiple files to prevent circular imports.

#### contracts/plugin_context.py
- **Purpose:** Plugin execution context carrying everything a plugin needs during execution. The largest mutable object in contracts.
- **Key types:** `ValidationErrorToken`, `TransformErrorToken`, `PluginContext`.
- **Frozen vs mutable:** `ValidationErrorToken` and `TransformErrorToken` are mutable dataclasses. `PluginContext` is **mutable** (by design -- it accumulates state during execution).
- **Dependencies:** Heavy TYPE_CHECKING imports: LandscapeRecorder, BatchCheckpointState, RuntimeConcurrencyConfig, ContractViolation, TokenInfo, PipelineRow, SchemaContract, RateLimitRegistry, AuditedHTTPClient, AuditedLLMClient. Runtime: `copy`, `logging`, `contextlib`, `dataclasses`, `datetime`.
- **Completeness:** Very comprehensive. 17 fields covering run metadata, Phase 3 integrations, batch identity, schema contracts, state/call recording, audited clients, telemetry callback, and checkpoint API. `record_call()` has XOR enforcement (state_id vs operation_id), telemetry emission, and token_id consistency validation. **CONCERNS:** (1) `PluginContext` is a God Object with 17 fields and 200+ lines of method code. (2) `ValidationErrorToken` and `TransformErrorToken` should be frozen. (3) `record_call()` has complex logic that arguably belongs in the engine, not in a contract type.

#### contracts/results.py
- **Purpose:** Operation outcomes and results (TransformResult, GateResult, RowResult, etc.).
- **Key types:** `ExceptionResult`, `FailureInfo`, `TransformResult`, `GateResult`, `RowResult`, `ArtifactDescriptor`, `SourceRow`.
- **Frozen vs mutable:** `RowResult` and `ArtifactDescriptor` are `frozen=True`. `TransformResult`, `GateResult`, `ExceptionResult`, `FailureInfo`, `SourceRow` are **mutable**.
- **Dependencies:** contracts/url, contracts/enums, contracts/errors, contracts/identity, contracts/routing.
- **Completeness:** Thorough. `TransformResult` has strong invariant validation in `__post_init__` (5 validation rules). Factory methods enforce correct construction. `ArtifactDescriptor` enforces `SanitizedDatabaseUrl`/`SanitizedWebhookUrl` types. `SourceRow` handles quarantine flow. **CONCERNS:** (1) `TransformResult` is mutable but has audit fields (input_hash, output_hash) set post-construction by executors. This is by design but creates a window where the object is partially constructed. (2) `GateResult.row` is `dict[str, Any]` rather than `PipelineRow` -- inconsistency with `TransformResult.row`.

#### contracts/routing.py
- **Purpose:** Flow control and edge definitions for DAG traversal.
- **Key types:** `RoutingAction`, `RouteDestinationKind` (StrEnum), `RouteDestination`, `RoutingSpec`, `EdgeInfo`.
- **Frozen vs mutable:** All 4 dataclasses are `frozen=True, slots=True`.
- **Dependencies:** `copy`, `contracts/enums`, `contracts/errors.RoutingReason`, `contracts/types`.
- **Completeness:** Excellent. `RoutingAction` has 5 invariant validations in `__post_init__`. Factory methods (`continue_()`, `route()`, `fork_to_paths()`) enforce correct construction. Deep-copies reason dicts. `RouteDestination` validates payload-by-kind constraints.

#### contracts/schema_contract_factory.py
- **Purpose:** Factory for creating SchemaContract from YAML configuration.
- **Key types:** Function: `create_contract_from_config()`, `map_schema_mode()`.
- **Frozen vs mutable:** N/A (pure factory functions).
- **Dependencies:** contracts/schema_contract (FieldContract, SchemaContract).
- **Completeness:** Clean bridge from config to runtime. Validates mode and field requirements. Maps lowercase YAML to uppercase runtime mode.

#### contracts/schema_contract.py
- **Purpose:** Core schema contract system: FieldContract, SchemaContract, PipelineRow.
- **Key types:** `FieldContract` (frozen dataclass), `SchemaContract` (frozen dataclass with computed indices), `PipelineRow` (class with `__slots__`).
- **Frozen vs mutable:** `FieldContract` is `frozen=True, slots=True`. `SchemaContract` is `frozen=True, slots=True` with MappingProxyType indices. `PipelineRow` is effectively immutable (MappingProxyType for data, raises TypeError on `__setitem__`).
- **Dependencies:** `hashlib`, `types.MappingProxyType`, contracts/errors, contracts/type_normalization.
- **Completeness:** Core of the schema system. O(1) name resolution via precomputed indices. Dual-name access on PipelineRow (original and normalized). Contract validation (required fields, type checking, FIXED mode extra rejection). Merge logic for coalesce points. Checkpoint serialization/restoration with hash integrity. `PipelineRow` implements Mapping protocol (keys, `__iter__`, `__contains__`, `get()`). Deep copy support for fork/expand. **Note:** `type(data) is not dict` check in PipelineRow.__init__ is an intentional Tier 1 strictness (no subclass coercion).

#### contracts/schema.py
- **Purpose:** Schema configuration types for config-driven plugin schemas (YAML parsing).
- **Key types:** `FieldDefinition` (frozen dataclass), `SchemaConfig` (frozen dataclass).
- **Frozen vs mutable:** Both `frozen=True`.
- **Dependencies:** `re`, `dataclasses`.
- **Completeness:** Thorough field spec parsing with clear error messages. Handles both string and dict YAML forms. Validates field name identifiers, type names, duplicates. Contract fields (guaranteed_fields, required_fields, audit_fields) with subset validation. `get_effective_guaranteed_fields()` and `get_effective_required_fields()` merge explicit and implicit contracts.

#### contracts/sink.py
- **Purpose:** Sink output validation result.
- **Key types:** `OutputValidationResult`.
- **Frozen vs mutable:** `frozen=True`.
- **Dependencies:** Only `dataclasses`.
- **Completeness:** Clean value object with factory methods. Covers field matching, order mismatches, and diagnostic details.

#### contracts/token_usage.py
- **Purpose:** LLM token usage with explicit unknown semantics. The precedent-setting dataclass for the dict-to-frozen-dataclass pattern.
- **Key types:** `TokenUsage`.
- **Frozen vs mutable:** `frozen=True, slots=True`.
- **Dependencies:** Only `dataclasses`.
- **Completeness:** Exemplary. `None = unknown` semantics eliminate fabrication bugs. `from_dict()` is the only Tier 3 path. `to_dict()` omits None keys. `is_known`/`has_data` properties distinguish full vs partial data. Clean factory methods.

#### contracts/transform_contract.py
- **Purpose:** Bridge between PluginSchema (Pydantic) and SchemaContract (frozen dataclass).
- **Key types:** Functions: `create_output_contract_from_schema()`, `validate_output_against_contract()`.
- **Frozen vs mutable:** N/A (pure functions).
- **Dependencies:** contracts/data.PluginSchema, contracts/errors, contracts/schema_contract, contracts/type_normalization.
- **Completeness:** Handles Optional/Union types, Annotated unwrapping, multi-type union rejection. Maps Pydantic extra modes to SchemaContract modes (allow->FLEXIBLE, forbid->FIXED, ignore->FLEXIBLE).

#### contracts/type_normalization.py
- **Purpose:** Type normalization for schema contracts. Converts numpy/pandas types to Python primitives.
- **Key types:** `CONTRACT_TYPE_MAP` (dict), `ALLOWED_CONTRACT_TYPES` (frozenset), function: `normalize_type_for_contract()`.
- **Frozen vs mutable:** Constants only.
- **Dependencies:** `math`, `datetime`. Lazy imports for `numpy`, `pandas`.
- **Completeness:** Single source of truth for type registry. Handles numpy integers, floats, bools, strings, pandas Timestamps, NaT, NA. Rejects NaN/Infinity (Tier 1 audit integrity). Rejects unsupported types. **Issue:** Lazy numpy/pandas import means this function will fail if numpy/pandas are not installed, but contracts is supposed to be a leaf module.

#### contracts/types.py
- **Purpose:** Semantic type aliases using NewType for compile-time type safety.
- **Key types:** `NodeID`, `CoalesceName`, `BranchName`, `SinkName`, `GateName`, `AggregationName` (all NewType of str). `StepResolver` (Callable type alias).
- **Frozen vs mutable:** N/A (type aliases).
- **Dependencies:** `collections.abc.Callable`, `typing.NewType`.
- **Completeness:** Good semantic differentiation. Prevents accidental misuse of string values across subsystems.

#### contracts/url.py
- **Purpose:** URL sanitization types guaranteeing secrets cannot leak into the audit trail.
- **Key types:** `SanitizedDatabaseUrl`, `SanitizedWebhookUrl`.
- **Frozen vs mutable:** Both `frozen=True`.
- **Dependencies:** `json`, `urllib.parse`. Lazy imports from `elspeth.core.config` and `elspeth.core.security.fingerprint`.
- **Completeness:** Thorough. `SanitizedDatabaseUrl` validates no password in `__post_init__`. `SanitizedWebhookUrl` handles query params, fragment params, and Basic Auth. `SENSITIVE_PARAMS` covers 16 common parameter names. Fingerprint computed from secret values only (not full URL). **Issue:** Lazy imports from `core.config` and `core.security` break the leaf module invariant. These are documented with a FIX reference but remain.

#### contracts/__init__.py
- **Purpose:** Package re-exports. Single import point for all contract types.
- **Key types:** Re-exports everything from all submodules.
- **Frozen vs mutable:** N/A.
- **Dependencies:** All 32 contract modules.
- **Completeness:** 463 lines of re-exports. `__all__` has 160+ entries, grouped by category. Well-organized with clear section headers. Settings classes explicitly NOT re-exported (documented).

---

## Overall Analysis

### 1. Contract Architecture

The contracts subsystem is organized **by concern**, not by subsystem. This is the correct choice for a cross-cutting type package:

| Concern | Files | Types |
|---------|-------|-------|
| **Audit trail** | audit.py, contract_records.py, call_data.py, coalesce_metadata.py, node_state_context.py, token_usage.py | 40+ dataclasses/TypedDicts for Landscape tables |
| **Schema contracts** | schema_contract.py, schema.py, schema_contract_factory.py, contract_builder.py, contract_propagation.py, transform_contract.py, type_normalization.py, header_modes.py | FieldContract, SchemaContract, PipelineRow, and propagation logic |
| **Configuration** | config/ (4 files) | Protocols, Runtime*Config, defaults, alignment |
| **Results & routing** | results.py, routing.py, engine.py, identity.py | TransformResult, GateResult, RoutingAction, TokenInfo |
| **Errors** | errors.py | 5 exception classes, 10+ TypedDicts, 3 Literal types |
| **Events** | events.py, cli.py | 14 telemetry/lifecycle event types |
| **Infrastructure** | payload_store.py, url.py, sink.py, data.py, types.py | Protocols, URL sanitization, type aliases |
| **Checkpoints** | checkpoint.py, aggregation_checkpoint.py, batch_checkpoint.py | Typed checkpoint state hierarchies |

The package successfully serves as a **leaf module** with minimal outbound dependencies (lazy imports for numpy/pandas/core). All cross-boundary types are centralized here.

### 2. Protocol Pattern

Five `@runtime_checkable` protocols in `config/protocols.py` define what engine components expect from configuration:

- `RuntimeRetryProtocol` -> consumed by `RetryManager`
- `RuntimeRateLimitProtocol` -> consumed by `RateLimitRegistry`
- `RuntimeConcurrencyProtocol` -> consumed by `ThreadPoolExecutor/Orchestrator`
- `RuntimeCheckpointProtocol` -> consumed by checkpoint system
- `RuntimeTelemetryProtocol` -> consumed by `TelemetryManager`

Additionally:
- `PayloadStore` protocol in payload_store.py (runtime_checkable)
- `CallPayload` protocol in call_data.py (runtime_checkable)
- `NodeStateContext` protocol in node_state_context.py (NOT runtime_checkable, mypy only)

The protocol pattern is well-implemented. Property-based interfaces, clear documentation of field origins, and structural typing verification.

### 3. Config Contracts (Settings-to-Runtime)

The Settings-to-Runtime mapping is the most sophisticated part of the contracts subsystem:

```
USER YAML -> Settings (Pydantic) -> Runtime*Config (frozen dataclass) -> Engine Components
```

Three-layer enforcement:
1. **mypy (structural typing):** Verifies Runtime*Config satisfies Runtime*Protocol
2. **AST checker (`scripts.check_contracts`):** Verifies `from_settings()` uses all Settings fields
3. **Alignment tests:** Verifies field mappings documented in alignment.py are accurate

This is a strong pattern. The P2-2026-01-21 bug (exponential_base orphaned) that motivated it is well-prevented.

### 4. Schema Contracts (DAG-time Validation)

The schema contract system is a four-phase pipeline:

1. **Phase 1 - Core:** `FieldContract`, `SchemaContract`, `PipelineRow` (schema_contract.py)
2. **Phase 2 - Source:** `ContractBuilder` for first-row inference (contract_builder.py)
3. **Phase 3 - Pipeline:** `propagate_contract()`, `narrow_contract_to_output()`, `merge_contract_with_output()` (contract_propagation.py)
4. **Phase 4 - Audit:** `ContractAuditRecord`, `FieldAuditRecord` with hash integrity verification (contract_records.py)

SchemaContract provides:
- O(1) dual-name resolution (original and normalized)
- Three enforcement modes (FIXED, FLEXIBLE, OBSERVED)
- Immutable with frozen pattern (`with_field()`, `with_locked()` return new instances)
- Deterministic version hashing for checkpoint integrity
- Merge logic for coalesce points (type conflict detection)

This is well-designed and comprehensive.

### 5. Frozen Dataclass Usage Assessment

**GOOD (frozen=True):** 30+ dataclasses across audit types (NodeState variants, TokenOutcome, Operation, SecretResolution, NonCanonicalMetadata), all config/runtime types, all call_data types, all event types, all checkpoint types, all routing types, schema contracts, identity, sink, coalesce metadata, node state context types.

**PROBLEMATIC (mutable when they should not be):**

| Type | File | Concern |
|------|------|---------|
| `Run` | audit.py | Tier 1 audit record -- should be frozen |
| `Node` | audit.py | Tier 1 audit record -- should be frozen |
| `Edge` | audit.py | Tier 1 audit record -- should be frozen |
| `Row` | audit.py | Tier 1 audit record -- should be frozen |
| `Token` | audit.py | Tier 1 audit record -- should be frozen |
| `TokenParent` | audit.py | Tier 1 audit record -- should be frozen |
| `Call` | audit.py | Tier 1 audit record -- should be frozen |
| `Artifact` | audit.py | Tier 1 audit record -- should be frozen |
| `RoutingEvent` | audit.py | Tier 1 audit record -- should be frozen |
| `Batch` | audit.py | Tier 1 audit record -- should be frozen |
| `BatchMember` | audit.py | Tier 1 audit record -- should be frozen |
| `BatchOutput` | audit.py | Tier 1 audit record -- should be frozen |
| `Checkpoint` | audit.py | Tier 1 audit record -- should be frozen |
| `RowLineage` | audit.py | Tier 1 audit record -- should be frozen |
| `ValidationErrorRecord` | audit.py | Tier 1 audit record -- should be frozen |
| `TransformErrorRecord` | audit.py | Tier 1 audit record -- should be frozen |
| `ResumePoint` | checkpoint.py | Point-in-time snapshot -- should be frozen |
| `TransformResult` | results.py | Has audit fields set post-construction |
| `GateResult` | results.py | Has audit fields set post-construction |
| `ExceptionResult` | results.py | Wrapper -- should be frozen |
| `FailureInfo` | results.py | Value object -- should be frozen |
| `ValidationErrorToken` | plugin_context.py | Value object -- should be frozen |
| `TransformErrorToken` | plugin_context.py | Value object -- should be frozen |

**Analysis:** 16 of the mutable types are Tier 1 audit records in audit.py. This is the single largest gap. These types represent database records that should never be modified after construction. The mutability appears to be historical -- the newer types (NodeState variants, Operation, SecretResolution, TokenOutcome) are frozen, suggesting a gradual migration toward immutability.

`TransformResult` and `GateResult` are mutable by design -- executors set audit fields (input_hash, output_hash, duration_ms) after construction. This is a compromise, but could be addressed by separating construction data from audit data (e.g., a wrapper or post-construction `with_audit()` method).

**APPROPRIATELY MUTABLE:**
- `PluginContext` -- accumulates state during execution
- `PluginSchema` -- Pydantic model for Tier 3 data validation
- `ContractBuilder` -- builder pattern for first-row inference
- `SourceRow` -- partially constructed at source, completed by engine
- `CompatibilityResult` -- simple result container

### 6. Type Safety Assessment: dict[str, Any] Remaining

Despite significant progress, `dict[str, Any]` still appears at important boundaries:

| Location | Field | Concern |
|----------|-------|---------|
| `PluginContext.config` | `dict[str, Any]` | Plugin config passed as untyped dict |
| `PluginContext.record_call` params | `request_data: dict[str, Any]` | External call payloads |
| `GateResult.row` | `dict[str, Any]` | Gate output is untyped dict, not PipelineRow |
| `AggregationNodeCheckpoint.contract` | `dict[str, Any]` | Opaque contract dict |
| `AggregationTokenCheckpoint.row_data` | `dict[str, Any]` | Opaque row data |
| `BatchCheckpointState.requests` | `dict[str, dict[str, Any]]` | Original API requests |
| `LLMCallRequest.messages` | `list[dict[str, Any]]` | LLM message format |
| `LLMCallResponse.raw_response` | `dict[str, Any]` | Tier 3 SDK data (intentional) |
| `RawCallPayload.data` | `dict[str, Any]` | Pre-serialized payloads |
| `TransformErrorReason` TypedDict | 80+ optional fields | Essentially untyped |

The first four in this list are the most concerning -- they are at Tier 1/2 boundaries where typed contracts should exist.

### 7. Known Issues (10 Open Bugs)

Per MEMORY.md, there are 10 open P2/P3 bugs about `dict[str, Any]` crossing into the audit trail. The contracts subsystem has already addressed several of these:

**Addressed:**
- `TokenUsage` (dffe74a6) -- precedent-setting
- `CoalesceMetadata` (4f7e43be) -- coalesce executor
- `call_data.py` (LLM/HTTP DTOs) -- 23+ construction sites replaced
- `node_state_context.py` (pool/gate/aggregation context) -- executor metadata
- `aggregation_checkpoint.py` -- three-level checkpoint hierarchy
- `batch_checkpoint.py` -- Azure batch checkpoint state

**Remaining (likely matching the 10 open bugs):**
- plugins/clients untyped dicts flowing to Landscape
- engine executor untyped error/reason dicts
- core/landscape recorder accepting untyped params

### 8. Completeness Gaps (Missing Contracts)

Types that cross subsystem boundaries but lack formal contracts:

1. **Landscape Recorder Method Signatures:** `record_call()`, `record_validation_error()`, `record_transform_error()` accept `dict[str, Any]` parameters. These should accept typed DTOs.

2. **DAG Graph Model:** The execution graph (nodes, edges, topology) has no contract types -- it uses NetworkX directly. Node metadata and edge properties are untyped dicts.

3. **Plugin Protocol Types:** Plugin interfaces (SourceProtocol, TransformProtocol, SinkProtocol) are not defined in contracts -- they live in the plugin system. This is arguably correct (plugins are system code), but the protocols would benefit from being in contracts for cross-reference.

4. **Orchestrator State:** Run state, counters, and progress tracking are not contract-typed. The orchestrator uses ad-hoc dicts for metrics.

5. **Checkpoint Recovery Protocol:** No protocol defining what a checkpointable component must implement. `get_checkpoint()`/`set_checkpoint()` is on PluginContext but not formalized as a protocol.

6. **Telemetry Exporter Protocol:** No protocol in contracts for telemetry exporters. They exist in the telemetry subsystem.

7. **GateResult.row is dict[str, Any]:** While TransformResult uses PipelineRow, GateResult still uses a plain dict. This creates an asymmetry in the processing pipeline.

### 9. Cross-Cutting Dependencies

**Who imports contracts?** (Based on the architecture):
- `core/` -- imports enums, audit types, config contracts
- `engine/` -- imports results, routing, identity, errors, events, engine contracts
- `plugins/` -- imports PluginContext, TransformResult, GateResult, SourceRow, PipelineRow
- `telemetry/` -- imports events, enums
- `cli.py` -- imports cli contracts, events
- `mcp/` -- imports audit types for query results
- `tui/` -- imports audit types for display

**Contracts' own dependencies:**
- `contracts/` is designed as a leaf module with no imports from `core/` or `engine/` at module level
- Lazy imports exist in `url.py` (core.config, core.security), `runtime.py` (core.config), `type_normalization.py` (numpy, pandas), `contract_records.py` (core.canonical), `schema_contract.py` (core.canonical)
- These lazy imports are documented with FIX references but represent a partial violation of the leaf module principle

### 10. Concerns and Recommendations (Ranked by Severity)

**SEVERITY: HIGH**

1. **16 mutable Tier 1 audit records in audit.py.** `Run`, `Node`, `Edge`, `Row`, `Token`, `TokenParent`, `Call`, `Artifact`, `RoutingEvent`, `Batch`, `BatchMember`, `BatchOutput`, `Checkpoint`, `RowLineage`, `ValidationErrorRecord`, `TransformErrorRecord` should all be `frozen=True`. This is the single most important remediation. Per CLAUDE.md: "Bad data in the audit trail = crash immediately" -- mutable audit records can be accidentally modified after construction, silently corrupting the legal record.

2. **TransformErrorReason is effectively untyped.** With 80+ optional fields and no structural discrimination, it provides almost no type safety over `dict[str, Any]`. Consider splitting into discriminated sub-TypedDicts by error category (e.g., `LLMErrorReason`, `ValidationErrorReason`, `BatchErrorReason`) with a tagged union.

3. **GateResult.row is dict[str, Any].** TransformResult uses PipelineRow, but GateResult uses a plain dict. This creates a trust-tier inconsistency in the processing pipeline. Gate output should be PipelineRow for consistency.

**SEVERITY: MEDIUM**

4. **PluginContext is a God Object.** 17 fields, 200+ lines of method code, mixes concerns (configuration, state management, call recording, telemetry, checkpointing). Consider splitting into composition-based sub-contexts (e.g., `CallRecordingContext`, `CheckpointContext`).

5. **Lazy imports partially violate leaf module invariant.** `url.py`, `runtime.py`, `type_normalization.py`, `contract_records.py`, and `schema_contract.py` all lazily import from `core/`. While documented, this creates fragile runtime dependencies. Consider extracting the needed primitives (fingerprint, canonical_json) into a truly leaf-level utility.

6. **AggregationNodeCheckpoint.from_dict() uses .get() for Tier 1 data.** Lines 164-165 use `.get()` for `count_fire_offset` and `condition_fire_offset`, which is inconsistent with the Tier 1 crash-on-corruption policy applied to other fields.

7. **AggregationFlushContext.trigger_type is str, not TriggerType enum.** Inconsistent with `Batch.trigger_type` in audit.py which uses the `TriggerType` enum.

**SEVERITY: LOW**

8. **ResumePoint should be frozen.** It represents a point-in-time snapshot for resume operations and should not be mutable.

9. **ValidationErrorToken and TransformErrorToken should be frozen.** They are value objects returned from recording operations.

10. **ExceptionResult and FailureInfo should be frozen.** They are value objects carrying error information.

11. **TODO on line 104 of contract_propagation.py.** "Extract shared field inference logic" between `propagate_contract()` and `narrow_contract_to_output()` -- 90% overlap acknowledged but not addressed.

12. **type_normalization.py lazy imports numpy/pandas.** If numpy/pandas are not installed, `normalize_type_for_contract()` will fail at runtime. This function is called during schema contract validation, which happens for all pipelines. The contracts package should handle the case where numpy/pandas are not installed (they are optional dependencies).

### 11. Confidence Assessment

| Aspect | Confidence | Rationale |
|--------|------------|-----------|
| Per-file analysis accuracy | **High** | Read all 37 files in full, verified types and patterns |
| Frozen vs mutable assessment | **High** | Checked every dataclass declaration |
| Contract architecture understanding | **High** | Traced all dependency chains and usage patterns |
| Missing contract identification | **Medium** | Based on architectural knowledge, may miss some edge cases in engine/plugin interactions not visible from contracts alone |
| Severity rankings | **Medium** | Based on CLAUDE.md principles and three-tier trust model; actual impact depends on how these types are used at call sites |

**Overall Confidence: High.** The contracts subsystem is well-designed and significantly more mature than typical Python projects. The main issues are (1) historical mutable audit records that predate the frozen dataclass convention, (2) an overgrown TransformErrorReason TypedDict, and (3) the GateResult/PipelineRow inconsistency. The config contracts system (Protocol + frozen dataclass + from_settings() + AST checker) is exemplary.

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Total files | 37 (4 config + 33 root) |
| Dataclasses | ~60 |
| Frozen dataclasses | ~40 (67%) |
| Mutable dataclasses needing freezing | ~20 (33%) |
| TypedDicts | ~12 |
| Protocols | 8 |
| Enums | 16 (all StrEnum) |
| Exception classes | 7 |
| NewType aliases | 6 |
| Literal types | 3 |
| Functions (non-method) | ~15 |
| Lines of code | ~5,500 |
| `__init__.py` re-exports | ~160 |
