# ELSPETH Subsystem Catalog

This catalog provides detailed entries for all 20 identified subsystems, organized by architectural tier.

---

## Tier 1: Core Framework (High Coupling)

### 1. Engine Subsystem

**Location:** `engine/`

**Responsibility:** Full pipeline execution orchestration - coordinates run lifecycle, DAG traversal, and plugin execution.

**Key Components:**

| File | Lines | Responsibility |
|------|-------|----------------|
| `orchestrator.py` | ~3100 | Full run lifecycle management (init → source → process → sink → complete) |
| `processor.py` | ~1918 | Row processing through DAG with work queue for fork/join |
| `executors.py` | ~1903 | Transform, gate, sink execution with audit recording |
| `coalesce_executor.py` | ~798 | Fork/join merge barrier with policy-driven merging |
| `retry.py` | ~146 | Tenacity-based retry with exponential backoff |
| `tokens.py` | ~283 | Token lifecycle (create, fork, coalesce, expand) |
| `triggers.py` | ~301 | Aggregation trigger evaluation (count, timeout, condition) |
| `expression_parser.py` | ~580 | Safe AST-based expression evaluation (no eval) |
| `spans.py` | ~298 | OpenTelemetry span factory |
| `clock.py` | ~11 | Testable time abstraction |
| `batch_adapter.py` | ~226 | Batch transform output routing |

**Dependencies (Inbound):**
- CLI → Orchestrator.run()
- Configuration → PipelineConfig

**Dependencies (Outbound):**
- Landscape → LandscapeRecorder for all audit operations
- DAG → ExecutionGraph for topology
- Plugins → Protocol implementations

**Patterns Observed:**
- Phase-based execution (DATABASE → GRAPH → PROCESSING → EXPORT)
- Work queue DAG traversal prevents stack overflow
- Explicit validation before processing
- Telemetry after Landscape success (Landscape = source of truth)

**Concerns:**
- Batch aggregation semantics are complex (buffer/trigger/flush/output_mode interplay)
- Coalesce step mapping requires careful topology alignment

---

### 2. Landscape Subsystem

**Location:** `core/landscape/`

**Responsibility:** Audit trail backbone - records every operation for complete traceability.

**Key Components:**

| File | Lines | Responsibility |
|------|-------|----------------|
| `recorder.py` | ~2700 | High-level recording API (47+ methods) |
| `database.py` | ~321 | Connection management, schema validation |
| `schema.py` | ~375 | SQLAlchemy table definitions |
| `repositories.py` | ~250 | Row → Object conversion with Tier 1 validation |
| `lineage.py` | ~180 | `explain()` queries for lineage |
| `exporter.py` | ~200 | Audit data export (JSON, CSV) |
| `formatters.py` | ~150 | Data serialization, datetime handling |
| `journal.py` | ~200 | JSONL change journaling |
| `reproducibility.py` | ~130 | Grade computation (FULL → ATTRIBUTABLE_ONLY) |

**Dependencies (Inbound):**
- Engine → LandscapeRecorder
- MCP → LandscapeDB (read-only)
- CLI → explain, export

**Dependencies (Outbound):**
- Contracts → Audit types (Run, Token, NodeState, etc.)
- SQLAlchemy Core

**Patterns Observed:**
- Repository pattern for string→enum conversion with Tier 1 validation
- Composite PK `(node_id, run_id)` requires denormalized queries
- JSONL journaling as backup stream
- Grade-based reproducibility tracking

**Concerns:**
- Composite PK joins are error-prone (use `node_states.run_id` directly)
- Large payloads require content-addressable storage separation

---

### 3. Contracts Subsystem

**Location:** `contracts/`

**Responsibility:** Cross-boundary type definitions - leaf module with NO outbound dependencies.

**Key Components:**

| File | Lines | Responsibility |
|------|-------|----------------|
| `audit.py` | ~350 | Audit types: Run, Node, Token, NodeState variants |
| `enums.py` | ~250 | Status enums (RunStatus, Determinism, RowOutcome, etc.) |
| `types.py` | ~30 | NewType aliases (NodeID, SinkName, etc.) |
| `data.py` | ~250 | PluginSchema, validation, compatibility |
| `engine.py` | ~50 | Engine contracts (PendingOutcome, RetryPolicy) |
| `errors.py` | ~300 | Error classification and exception types |
| `events.py` | ~150 | Telemetry event definitions |
| `results.py` | ~200 | Plugin result contracts (TransformResult, GateResult) |
| `config/` | ~700 | Settings→Runtime configuration system |

**Dependencies (Inbound):**
- ALL subsystems import contracts

**Dependencies (Outbound):**
- NONE (leaf module)

**Patterns Observed:**
- Enum values are (str, Enum) for direct DB storage
- Frozen dataclasses for immutable audit records
- NodeState variants with Literal type discrimination
- Protocol-based verification for runtime config

**Concerns:**
- Field alignment between Settings and Runtime*Config must be maintained
- EXEMPT_SETTINGS list must be accurate

---

### 4. DAG Subsystem

**Location:** `core/dag.py`

**Responsibility:** Execution graph construction and validation using NetworkX.

**Key Classes:**
- `ExecutionGraph` - ~1000+ LOC, wraps NetworkX MultiDiGraph
- `NodeInfo` - Node metadata with immutable schemas
- `GraphValidationError` - Validation failure exception

**Key Methods:**
- `from_plugin_instances()` - Factory for production graph construction
- `topological_order()` - Execution sequence
- `validate_edge_compatibility()` - Schema contract enforcement

**Dependencies (Inbound):**
- Orchestrator → ExecutionGraph
- Checkpoint → topology hashing

**Dependencies (Outbound):**
- NetworkX
- Contracts (RoutingMode, EdgeInfo, SchemaConfig)
- canonical.py → stable_hash for deterministic node IDs

**Patterns Observed:**
- MultiDiGraph supports multiple edges (fork routing)
- Two-phase validation: contract (field names) → type (schema compatibility)
- Deterministic node ID generation for checkpoint resume

**Concerns:**
- Complex graph construction logic for gates/coalesce/aggregation
- All fork branches must have explicit destinations

---

### 5. Configuration Subsystem

**Location:** `core/config.py` + `contracts/config/`

**Responsibility:** Settings validation (Pydantic) and runtime config (frozen dataclasses).

**Key Components:**
- `core/config.py` - ElspethSettings, plugin settings, Dynaconf loading
- `contracts/config/protocols.py` - Runtime*Protocol definitions
- `contracts/config/runtime.py` - Runtime*Config dataclasses with `from_settings()`
- `contracts/config/alignment.py` - Field mapping documentation
- `contracts/config/defaults.py` - POLICY_DEFAULTS, INTERNAL_DEFAULTS

**Pattern:**
```
User YAML → Settings (Pydantic) → from_settings() → Runtime*Config → Engine
```

**Key Rule:** Every Settings field MUST be mapped in `from_settings()` or documented in EXEMPT_SETTINGS.

**Concerns:**
- Field orphaning risk (P2-2026-01-21 bug)
- AST checker and alignment tests enforce mapping

---

## Tier 2: Infrastructure Services

### 6. Telemetry Subsystem

**Location:** `telemetry/`

**Responsibility:** Real-time operational visibility alongside Landscape audit trail.

**Key Components:**

| File | Responsibility |
|------|----------------|
| `manager.py` | Central hub with async export thread, backpressure modes |
| `protocols.py` | ExporterProtocol definition |
| `filtering.py` | Granularity filtering (lifecycle/rows/full) |
| `buffer.py` | Ring buffer with overflow tracking |
| `factory.py` | Exporter instantiation from config |
| `exporters/console.py` | Console output (JSON/pretty) |
| `exporters/otlp.py` | OpenTelemetry Protocol export |
| `exporters/datadog.py` | Datadog direct integration |

**Design Principles:**
- Telemetry emitted AFTER Landscape recording
- Individual exporter failures isolated
- Aggregate logging every 100 failures (Warning Fatigue prevention)
- Graceful degradation after 10 consecutive total failures

**Concerns:**
- Thread safety: `_events_dropped` needs lock protection
- Queue size tuning for backpressure

---

### 7. Plugin System Subsystem

**Location:** `plugins/` (base, protocols, manager, discovery)

**Responsibility:** Plugin discovery, validation, and management via pluggy.

**Key Components:**

| File | Responsibility |
|------|----------------|
| `protocols.py` | SourceProtocol, TransformProtocol, SinkProtocol, GateProtocol |
| `hookspecs.py` | pluggy hook specifications |
| `manager.py` | PluginManager - discovery and instantiation |
| `discovery.py` | Dynamic plugin discovery via file scanning |
| `validation.py` | Plugin contract validation |
| `context.py` | PluginContext - plugin execution context |
| `config_base.py` | Plugin configuration base classes |
| `base.py` | BaseSource, BaseTransform, BaseSink |

**Plugin Counts:**
- Sources: 4 (csv, json, null, azure_blob)
- Transforms: 11+ (field_mapper, passthrough, truncate, keyword_filter, etc.)
- LLM Transforms: 6 (azure_llm, azure_batch, azure_multi_query, openrouter variants)
- Sinks: 4 (csv, json, database, azure_blob)
- Clients: 4 (http, llm, replayer, verifier)

**Patterns Observed:**
- All plugins are SYSTEM-OWNED (not user extensions)
- Protocol-based with pluggy hooks
- Dynamic discovery via folder scanning
- Batch-aware transforms use BatchTransformMixin

---

### 8. Checkpoint Subsystem

**Location:** `core/checkpoint/`

**Responsibility:** Crash recovery via checkpoints and resume validation.

**Key Components:**
- `CheckpointManager` - Create checkpoints at row boundaries
- `CheckpointCompatibilityValidator` - Validate resume safety
- `RecoveryManager` - Full resume logic

**Key Invariant:** One run_id = one configuration. ANY topology change invalidates resume.

**Patterns Observed:**
- Full topology hash (not just upstream) - BUG-COMPAT-01 fix
- Aggregation state preserved as JSON with `allow_nan=False`
- Checkpoints deleted after successful completion

---

### 9. Payload Store Subsystem

**Location:** `core/payload_store.py`

**Responsibility:** Content-addressable blob storage with integrity verification.

**Key Features:**
- SHA-256 based addressing (automatic deduplication)
- Integrity verified on retrieval via timing-safe HMAC
- Path traversal defense with containment validation

**Pattern:**
```
store(content) → SHA-256 hash
retrieve(hash) → content (with integrity check)
```

---

### 10. Rate Limiting Subsystem

**Location:** `core/rate_limit/`

**Responsibility:** External call throttling with optional SQLite persistence.

**Key Components:**
- `RateLimiter` - pyrate-limiter wrapper
- `RateLimitRegistry` - Central limiter management
- `NoOpLimiter` - Testing mock

**Pattern:** Sliding window rate limiting with configurable requests/minute.

---

## Tier 3: Plugin Implementations

### 11. Sources Subsystem

**Location:** `plugins/sources/`

**Available Plugins:**
- `csv` - CSV file loading with delimiter, encoding, skip_rows
- `json` - JSON/JSONL file loading
- `null` - Empty source for testing
- `azure_blob` - Azure Blob Storage source

**Common Features:**
- Field normalization (snake_case conversion)
- Validation failure handling (quarantine/skip/fail)
- Schema: dynamic or explicit fields

---

### 12. Transforms Subsystem

**Location:** `plugins/transforms/`

**Available Plugins:**
- `passthrough` - No-op transform
- `field_mapper` - Rename/select fields
- `truncate` - Truncate string fields
- `keyword_filter` - Keyword-based filtering
- `json_explode` - Explode JSON arrays to rows
- `batch_replicate` - Replicate rows (deaggregation)
- `batch_stats` - Compute batch statistics

**Azure Sub-plugins:**
- `content_safety` - Azure Content Safety API
- `prompt_shield` - Azure Prompt Shield API

---

### 13. Sinks Subsystem

**Location:** `plugins/sinks/`

**Available Plugins:**
- `csv` - CSV file output with header modes
- `json` - JSON/JSONL output
- `database` - SQLAlchemy database insert
- `azure_blob` - Azure Blob Storage sink

**Features:**
- Resume support (append mode)
- Display headers (field → display name mapping)
- Content hashing for artifacts

---

### 14. LLM Plugins Subsystem

**Location:** `plugins/llm/`

**Available Plugins:**

| Plugin | Provider | Mode |
|--------|----------|------|
| `azure_llm` | Azure OpenAI | Row-level, pooled |
| `azure_batch_llm` | Azure OpenAI | Batch API |
| `azure_multi_query` | Azure OpenAI | Multi-query per row |
| `openrouter_llm` | OpenRouter | Row-level, pooled |
| `openrouter_batch` | OpenRouter | Batch API |
| `openrouter_multi_query` | OpenRouter | Multi-query per row |

**Key Features:**
- Jinja2 prompt templating with audit metadata
- FIFO output ordering via RowReorderBuffer
- AIMD backoff for rate limiting
- Concurrent row processing with backpressure

---

### 15. Clients Subsystem

**Location:** `plugins/clients/`

**Available Clients:**
- `AuditedHTTPClient` - HTTP with automatic recording
- `AuditedLLMClient` - LLM with automatic recording
- `ReplayerClient` - Replay recorded calls
- `VerifierClient` - Verify against recorded calls

**Pattern:** All clients automatically record to Landscape and emit telemetry.

---

## Tier 4: User Interfaces

### 16. CLI Subsystem

**Location:** `cli.py`, `cli_helpers.py`

**Responsibility:** Primary command-line interface (Typer-based).

**Commands:**
- `run` - Execute pipeline (requires `--execute` flag)
- `explain` - Lineage exploration (TUI or JSON)
- `validate` - Config validation
- `plugins list` - Plugin discovery
- `purge` - Payload cleanup
- `resume` - Continue failed run
- `health` - System health check

**Lines:** ~2150 (cli.py) + ~160 (cli_helpers.py)

---

### 17. TUI Subsystem

**Location:** `tui/`

**Responsibility:** Interactive terminal UI for lineage exploration (Textual-based).

**Key Components:**
- `ExplainApp` - Main Textual application
- `ExplainScreen` - Screen state machine
- `LineageTree` - Tree visualization widget
- `NodeDetailPanel` - Detail display widget

**Layout:**
```
┌─────────────────┬─────────────────┐
│  Lineage Tree   │  Detail Panel   │
│  (green border) │  (blue border)  │
└─────────────────┴─────────────────┘
```

---

### 18. MCP Server Subsystem

**Location:** `mcp/`

**Responsibility:** Read-only Model Context Protocol server for Landscape analysis.

**Key Tools:**
- `list_runs`, `get_run`, `get_run_summary`
- `list_rows`, `list_tokens`, `list_nodes`
- `list_operations`, `get_operation_calls`
- `explain_token` - Complete lineage
- `get_errors` - Error catalog
- `diagnose` - Emergency assessment
- `query` - Ad-hoc SQL (SELECT only)

**Design:** Claude-optimized for investigation workflows.

---

## Tier 5: Testing Infrastructure

### 19. ChaosLLM Subsystem

**Location:** `testing/chaosllm/`

**Responsibility:** Fake LLM server for load testing and fault injection.

**Components:**
- `server.py` - Starlette ASGI server (OpenAI/Azure compatible)
- `cli.py` - Command-line interface
- `error_injector.py` - Configurable error rates
- `latency_simulator.py` - Delay injection
- `response_generator.py` - Synthetic responses
- `metrics.py` - Request tracking

**Use Cases:**
- AIMD backoff testing
- Fault tolerance validation
- Circuit breaker testing

---

### 20. Testing Utils Subsystem

**Location:** `testing/`

**Responsibility:** Test helpers and fixtures.

**Components:**
- `chaosllm_mcp/` - MCP analysis for ChaosLLM results
- Shared test utilities

---

## Summary Statistics

| Category | Count |
|----------|-------|
| **Total Subsystems** | 20 |
| **Core Framework** | 5 |
| **Infrastructure** | 5 |
| **Plugin Implementations** | 5 |
| **User Interfaces** | 3 |
| **Testing** | 2 |
| **Total Python LOC** | ~58,000 |
| **Total Test LOC** | ~187,000 |
