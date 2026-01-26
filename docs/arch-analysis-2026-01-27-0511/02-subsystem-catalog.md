# Subsystem Catalog

This document provides detailed analysis of each ELSPETH subsystem, produced through parallel exploration agents.

---

## 1. Landscape (Audit Trail)

**Location:** `src/elspeth/core/landscape/`

**Responsibility:** Audit backbone providing complete traceability - records every operation in the SDA pipeline through a comprehensive database schema with hash integrity preservation.

**Key Components:**
- `schema.py` - SQLAlchemy Core table definitions for runs, nodes, edges, rows, tokens, node_states, calls, artifacts, routing_events, batches, checkpoints
- `database.py` - LandscapeDB connection manager with SQLite/PostgreSQL support, schema validation, WAL configuration
- `recorder.py` - LandscapeRecorder high-level API for recording audit entries
- `repositories.py` - Repository layer for data model deserialization, enum type coercion at Tier 1 boundary
- `models.py` - Dataclass definitions for all audit entities with discriminated union types
- `lineage.py` - LineageResult and explain() function for composing complete token/row lineage
- `exporter.py` - LandscapeExporter for CSV/JSON audit export with optional HMAC signing

**Public API:**
- `LandscapeRecorder` - Main recording interface with begin_run(), complete_run(), record_row(), create_token(), begin_node_state(), complete_node_state(), record_call(), record_routing_event()
- `LandscapeDB` - Database connection with in-memory and from_url() factories
- `explain()` - Query complete lineage for token/row

**Dependencies:**
- **Inbound:** Engine (uses LandscapeRecorder), Checkpoint (uses schema), Retention (queries for purge)
- **Outbound:** SQLAlchemy Core, canonical (hash computation), contracts (enums)

**Patterns Observed:**
- **Tier 1 Trust Model:** Enum validation crashes on bad data via `_validate_enum()` - no silent coercion
- **Composite Primary Key:** nodes_table uses (node_id, run_id) composite PK; node_states denormalizes run_id for direct filtering
- **Hash-Based Integrity:** source_data_hash, content_hash preserved for verification after payload purge
- **Transaction Atomicity:** All state transitions use engine.begin() context manager

**Concerns:**
- None observed - Architecture complete and consistent with Data Manifesto

**Confidence:** **High** - Comprehensive schema with explicit integrity constraints

---

## 2. Checkpoint (Recovery)

**Location:** `src/elspeth/core/checkpoint/`

**Responsibility:** Crash recovery mechanism capturing run progress at token boundaries with topology validation.

**Key Components:**
- `manager.py` - CheckpointManager for creating and loading checkpoints with topology validation
- `recovery.py` - RecoveryManager for resume eligibility and row retrieval
- `compatibility.py` - CheckpointCompatibilityValidator for topology matching

**Public API:**
- `CheckpointManager.create_checkpoint()`, `get_latest_checkpoint()`
- `RecoveryManager.can_resume()`, `get_resume_point()`, `get_unprocessed_rows()`
- `ResumeCheck`, `ResumePoint` result types

**Dependencies:**
- **Inbound:** Engine (resume operations)
- **Outbound:** Landscape (checkpoints_table), PayloadStore, canonical (topology hash), DAG

**Patterns Observed:**
- **Topology Validation:** Three-level validation (node exists, config unchanged, upstream topology unchanged)
- **Transaction Boundary:** Topology hashes computed INSIDE create_checkpoint transaction
- **No Legacy Code:** Rejects pre-topology-validation checkpoints

**Concerns:**
- None observed - Error messages detailed and actionable

**Confidence:** **High** - Comprehensive validation prevents resume with incompatible graph

---

## 3. Retention (Purge)

**Location:** `src/elspeth/core/retention/`

**Responsibility:** Manage payload purge based on retention policy while preserving audit trail hashes.

**Key Components:**
- `purge.py` - PurgeManager for identifying and deleting expired payloads

**Public API:**
- `PurgeManager.find_expired_payload_refs()`, `purge_payloads()`
- `PurgeResult` with deleted_count, bytes_freed, skipped_count

**Dependencies:**
- **Inbound:** Landscape (queries for expired runs)
- **Outbound:** PayloadStore (deletes content), reproducibility module

**Patterns Observed:**
- **Content-Addressable Deduplication:** Excludes refs used by non-expired runs
- **Composite Join Safety:** Uses node_states_table.run_id directly
- **Graceful Degradation:** Hashes remain after payload deletion

**Concerns:**
- bytes_freed always 0 (PayloadStore.delete() doesn't return size) - documented for future

**Confidence:** **High** - Correct deduplication and audit integrity preservation

---

## 4. Engine (Orchestrator)

**Location:** `src/elspeth/engine/`

**Responsibility:** Coordinates complete pipeline execution from row loading through sink output.

**Key Components:**
- `orchestrator.py` (2058 lines) - Full run lifecycle management
- `processor.py` (1048 lines) - Row-level processing through transforms
- `executors.py` (1654 lines) - Plugin execution wrappers with audit recording
- `tokens.py` (263 lines) - Token lifecycle management
- `coalesce_executor.py` (582 lines) - Stateful barrier for merging parallel paths
- `retry.py` - Retry logic with tenacity integration
- `batch_adapter.py` - SharedBatchAdapter for async batch transforms

**Public API:**
- `Orchestrator.run()` - Execute pipeline, returns RunResult
- `RowProcessor.process_row()`, `process_existing_row()`
- `TokenManager.create_initial_token()`, `fork_token()`, `coalesce_tokens()`, `expand_token()`
- `TransformExecutor`, `GateExecutor`, `AggregationExecutor`, `SinkExecutor`

**Dependencies:**
- **Inbound:** CLI, Settings
- **Outbound:** Landscape/LandscapeRecorder, Plugins, DAG, OpenTelemetry

**Patterns Observed:**
- **Work Queue Pattern:** deque[_WorkItem] for fork operations with iteration guard
- **Executor Wrapper Pattern:** begin_node_state() → plugin → complete_node_state()
- **Token Identity Tracking:** row_id (stable) vs token_id (changes on fork/coalesce)
- **Fork/Join Semantics:** COPY edges, configurable merge policies (require_all, quorum, first, best_effort)
- **Retry with LLM Error Classification:** Distinguishes retryable vs non-retryable errors

**Concerns:**
- **_process_single_token() Complexity:** 390 lines handling transforms + gates + coalesce
- **Coalesce Late Arrival Handling:** Dual return path could be clearer
- **No Deadlock Detection:** Missing branch never arrives at coalesce

**Confidence:** **High** (95%) - Core execution well-documented, minor concerns are edge cases

---

## 5. DAG (Execution Graph)

**Location:** `src/elspeth/core/dag.py`

**Responsibility:** Validate and represent execution graph structure, manage plugin topology, enforce schema compatibility.

**Key Components:**
- `ExecutionGraph` - Main API for graph manipulation and validation
- `NodeInfo` - Metadata for each node (type, plugin_name, schemas, config)
- `GraphValidationError` - Raised on structural violations

**Public API:**
- `ExecutionGraph.from_plugin_instances()` - Factory (correct method per CLAUDE.md)
- `get_sink_id_map()`, `get_transform_id_map()`, `get_aggregation_id_map()`
- `get_branch_to_coalesce_map()`, `get_route_resolution_map()`
- `validate()` - PHASE 1: structural validation
- `validate_edge_compatibility()` - PHASE 2: schema compatibility

**Dependencies:**
- **Inbound:** CLI, Engine
- **Outbound:** NetworkX (topology operations), contracts

**Patterns Observed:**
- **Deterministic Node IDs:** canonical JSON hash of config + sequence number
- **MultiDiGraph:** Allows multiple edges between same node pair
- **Two-Phase Validation:** Structural then schema compatibility
- **Pass-Through Schema Inheritance:** Gates/coalesce inherit from upstream

**Concerns:**
- **Dynamic Schema Bypass:** Dynamic schemas (None) bypass field compatibility checks
- **Node ID Hash Collision:** First 12 hex chars (48 bits) - extremely unlikely but not documented

**Confidence:** **Very High** (98%) - Well-structured with proven NetworkX

---

## 6. Tokens Subsystem

**Location:** `src/elspeth/engine/tokens.py`

**Responsibility:** Manage token lifecycle and maintain lineage metadata for audit trail.

**Key Components:**
- `TokenManager` - Main API for token operations
- `TokenInfo` (from contracts) - Token identity container

**Public API:**
- `create_initial_token()`, `create_token_for_existing_row()`
- `fork_token()`, `coalesce_tokens()`, `expand_token()`, `update_row_data()`

**Dependencies:**
- **Inbound:** RowProcessor
- **Outbound:** LandscapeRecorder, PayloadStore

**Patterns Observed:**
- **Defensive Deepcopy on Fork:** Prevents nested mutable object sharing
- **Step Position Authority:** TokenManager never owns step - receives from caller
- **Identity Immutability:** row_id never changes, only token_id

**Concerns:**
- **Deepcopy Performance:** Could be expensive for large nested structures
- **No Deepcopy on Coalesce:** Assumes merge strategy returns new objects

**Confidence:** **High** (92%) - Clean delegation to LandscapeRecorder

---

## 7. Plugin Framework

**Location:** `src/elspeth/plugins/`

**Responsibility:** Manages plugin discovery, registration, lifecycle, base classes, and protocols.

**Key Components:**
- `hookspecs.py` - pluggy hook specifications
- `protocols.py` - Runtime protocols (SourceProtocol, TransformProtocol, etc.)
- `base.py` - Abstract base classes (BaseSource, BaseTransform, BaseSink)
- `manager.py` - PluginManager for registration and lookup
- `context.py` - PluginContext providing run metadata and call recording
- `discovery.py` - Dynamic plugin discovery

**Public API:**
- `PluginManager.register()`, `get_source_by_name()`, `get_transform_by_name()`, `get_sink_by_name()`
- `PluginContext.record_call()`, `record_validation_error()`, `record_transform_error()`

**Dependencies:**
- **Inbound:** Engine layer
- **Outbound:** Contracts, Core services (Landscape, PayloadStore)

**Patterns Observed:**
- **pluggy-based Hook System:** Extensible discovery without inheritance
- **Protocol-Driven Design:** Runtime-checkable Protocols for type safety
- **Three-Tier Trust Model:** Validation errors (Tier 3), transform errors (Tier 2)
- **Determinism Metadata:** All plugins expose determinism and version

**Concerns:**
- Error recording requires state_id to be set by executor

**Confidence:** **High** - Well-structured with clear separation of concerns

---

## 8. Source Plugins

**Location:** `src/elspeth/plugins/sources/`

**Responsibility:** Load data from external sources with validation and quarantine handling.

**Key Components:**
- `csv_source.py` - CSV file loader with multiline support
- `json_source.py` - JSON array/JSONL loader
- `null_source.py` - No-op source for testing

**Patterns Observed:**
- **External Data Coercion at Boundary:** Sources create schemas with `allow_coercion=True`
- **Row Validation with Quarantine:** Invalid rows yielded as SourceRow.quarantined()
- **Line Number Tracking:** Physical line numbers for accurate audit trail

**Confidence:** **High** - Clear error handling and audit integration

---

## 9. Transform Plugins

**Location:** `src/elspeth/plugins/transforms/`

**Responsibility:** Process rows with batching, mapping, filtering, truncation.

**Key Components:**
- `passthrough.py`, `field_mapper.py`, `json_explode.py`, `keyword_filter.py`
- `batch_replicate.py`, `batch_stats.py`, `truncate.py`

**Patterns Observed:**
- **Type Coercion Disabled:** `allow_coercion=False` - wrong types crash (upstream bug)
- **Batch-Aware Processing:** `is_batch_aware=True` for aggregation
- **Token Creation Flag:** `creates_tokens=True` for deaggregation

**Confidence:** **High** - Clear patterns well-documented

---

## 10. Sink Plugins

**Location:** `src/elspeth/plugins/sinks/`

**Responsibility:** Write rows to external destinations with content hashing.

**Key Components:**
- `csv_sink.py` - CSV writer with append/resume support
- `json_sink.py` - JSON array and JSONL writer
- `database_sink.py` - Generic SQL database sink

**Patterns Observed:**
- **Content Hashing for Audit:** SHA-256 hash computed after every write
- **Fsync for Durability:** flush() calls os.fsync()
- **Resume Capability:** supports_resume, configure_for_resume()

**Confidence:** **High** - Rigorous audit integration and durability

---

## 11. LLM Integration

**Location:** `src/elspeth/plugins/llm/`

**Responsibility:** Integrate with LLM providers with prompt templating and batch processing.

**Key Components:**
- `base.py` - BaseLLMTransform with LLMConfig
- `azure.py`, `azure_batch.py`, `azure_multi_query.py` - Azure OpenAI
- `openrouter.py`, `openrouter_multi_query.py` - OpenRouter
- `templates.py` - Jinja2 prompt rendering

**Patterns Observed:**
- **Client-Per-Transform:** Each transform creates own AuditedLLMClient
- **Temperature Defaults to 0.0:** Determinism by default
- **Retryable Error Classification:** For engine retry logic

**Confidence:** **High** - Proper error classification and audit integration

---

## 12. Azure Integration

**Location:** `src/elspeth/plugins/azure/`

**Responsibility:** Azure-specific authentication and Blob Storage.

**Key Components:**
- `auth.py` - Unified authentication (connection string, SAS, Managed Identity, Service Principal)
- `blob_source.py` - Azure Blob source with CSV/JSON support
- `blob_sink.py` - Azure Blob sink with atomic upload

**Patterns Observed:**
- **Mutually Exclusive Auth Methods:** @model_validator enforces exactly one method
- **Multi-Format Support:** Configurable CSV delimiters and JSON parsing

**Confidence:** **Medium** - Auth validation logic not fully explored

---

## 13. Contracts

**Location:** `src/elspeth/contracts/`

**Responsibility:** Defines cross-subsystem data types enforcing audit-critical trust boundaries.

**Key Components:**
- `enums.py` - Status codes (RunStatus, NodeStateStatus, RowOutcome, Determinism)
- `results.py` - Operation outcomes (TransformResult, GateResult, SourceRow)
- `data.py` - Schema system (PluginSchema, check_compatibility)
- `identity.py` - Token identity (TokenInfo)
- `errors.py` - Error contracts (ExecutionError, RoutingReason)
- `audit.py` - Audit trail records
- `events.py` - Observability events
- `url.py` - Sanitized URLs with HMAC fingerprints

**Patterns Observed:**
- **Trust-Boundary Enforcement:** TypedDicts and factory methods enforce construction
- **Determinism Classification:** Every plugin MUST declare Determinism
- **Secret Fingerprinting:** SanitizedDatabaseUrl prevents credential leaks at type level

**Confidence:** **High** - Type system enforces invariants

---

## 14. Configuration

**Location:** `src/elspeth/core/config.py`

**Responsibility:** Loads, validates, and provides frozen settings from YAML via Pydantic.

**Key Components:**
- `ElspethSettings` - Top-level frozen Pydantic model
- `GateSettings`, `CoalesceSettings`, `AggregationSettings` - Routing/batching config
- `TriggerConfig` - Batch trigger definitions

**Patterns Observed:**
- **Frozen Models:** All settings frozen after construction
- **Reserved Edge Labels:** frozenset {"continue"} prevents DAG collisions
- **Expression Validation:** Gate conditions validated at load time

**Confidence:** **High** - Pydantic validators enforce invariants at load time

---

## 15. Canonical JSON

**Location:** `src/elspeth/core/canonical.py`

**Responsibility:** Produces deterministic RFC 8785 JSON for audit-safe hashing.

**Key Components:**
- `canonical_json()` - Two-phase deterministic JSON production
- `stable_hash()` - SHA-256 of canonical JSON
- `compute_upstream_topology_hash()` - For checkpoint validation

**Patterns Observed:**
- **Two-Phase Normalization:** Our code normalizes types, rfc8785 applies standard
- **Strict NaN/Infinity Rejection:** Raises ValueError, no silent conversion
- **Pandas/NumPy Normalization:** Timestamp → UTC ISO, numpy types → primitives

**Confidence:** **High** - Explicit rejection prevents silent data corruption

---

## 16. Events

**Location:** `src/elspeth/core/events.py`, `src/elspeth/contracts/events.py`

**Responsibility:** Observability events and event bus for CLI/formatter consumption.

**Key Components:**
- `EventBus` - Synchronous publisher-subscriber
- `NullEventBus` - No-op implementation
- `PhaseStarted`, `PhaseCompleted`, `PhaseError`, `RunCompleted` events

**Patterns Observed:**
- **Protocol-Based Design:** EventBusProtocol allows both implementations
- **Immutable Events:** frozen=True, slots=True dataclasses
- **Exit Code Mapping:** 0=success, 1=partial, 2=failure

**Confidence:** **High** - Protocol prevents substitution bugs

---

## 17. TUI (Explain Interface)

**Location:** `src/elspeth/tui/`

**Responsibility:** Interactive terminal UI for exploring pipeline lineage.

**Key Components:**
- `ExplainApp` - Textual App with grid layout
- `LineageTree` - Widget for tree rendering
- `types.py` - TUI data contracts

**Patterns Observed:**
- **Data Contract Enforcement:** TypedDicts require correct structure
- **Textual Bindings:** Keyboard shortcuts for navigation

**Concerns:**
- **Placeholder Widgets:** TUI is skeleton only
- **Data Loading:** No Landscape query integration shown

**Confidence:** **Medium** - Structure sound but implementation incomplete

---

## Cross-Subsystem Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────┐
│                            CLI Layer                                 │
│  cli.py → instantiate_plugins_from_config() → ExecutionGraph        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Engine Layer                                │
│  Orchestrator → RowProcessor → Executors → TokenManager             │
│       │              │             │              │                  │
│       └──────────────┼─────────────┼──────────────┘                  │
│                      ▼             ▼                                 │
│               ┌──────────────────────────┐                          │
│               │     Plugin Framework     │                          │
│               │  Sources | Transforms | Sinks | LLM | Azure         │
│               └──────────────────────────┘                          │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          Core Layer                                  │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌─────────────┐         │
│  │Landscape│←→│Checkpoint│←→│ Retention │←→│PayloadStore │         │
│  └─────────┘  └──────────┘  └───────────┘  └─────────────┘         │
│       │                                                              │
│       └──────────────┬──────────────────────────────────┐           │
│                      ▼                                   ▼           │
│               ┌────────────┐                    ┌──────────────┐    │
│               │ Canonical  │                    │  Contracts   │    │
│               │   JSON     │                    │ (types/enums)│    │
│               └────────────┘                    └──────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Summary Statistics

| Subsystem | Files | LOC (est.) | Confidence |
|-----------|-------|------------|------------|
| Landscape | 13 | ~3,500 | High |
| Checkpoint | 3 | ~1,200 | High |
| Retention | 2 | ~400 | High |
| Engine | 14 | ~7,500 | High |
| DAG | 1 | ~1,000 | Very High |
| Tokens | 1 | ~300 | High |
| Plugin Framework | 10 | ~2,500 | High |
| Source Plugins | 3 | ~500 | High |
| Transform Plugins | 7 | ~1,200 | High |
| Sink Plugins | 3 | ~800 | High |
| LLM Integration | 10 | ~3,500 | High |
| Azure Integration | 4 | ~1,300 | Medium |
| Contracts | 18 | ~2,000 | High |
| Configuration | 1 | ~1,200 | High |
| Canonical JSON | 1 | ~250 | High |
| Events | 2 | ~350 | High |
| TUI | 6 | ~500 | Medium |

**Total Estimated LOC:** ~28,000 (source only, excluding tests)
