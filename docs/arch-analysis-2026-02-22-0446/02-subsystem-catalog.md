# Subsystem Catalog

**Date:** 2026-02-22 | **Branch:** RC3.3-architectural-remediation

This catalog documents every first-level subsystem in ELSPETH: its responsibility, internal structure, dependencies, and top concerns. Subsystems without dedicated analysis files are inferred from dependency data and marked accordingly.

---

## Contracts

**Location:** `src/elspeth/contracts/` | **Size:** ~7,500 lines, ~30 files | **Layer:** L0 (foundation)

**Responsibility:** Type definitions, protocol interfaces, data transfer objects, enums, and error types that define the contract surface between all other subsystems.

**Internal Architecture:**
Flat package with per-concern modules. Key clusters: config protocols and runtime dataclasses (`config/`), schema contracts and pipeline row model (`schema_contract.py`, `contract_builder.py`), plugin context god object (`plugin_context.py`), result types (`results.py`), event types (`events.py`), and enum definitions (`enums.py`).

**Key Components:**
- `plugin_context.py` -- God object bundling LandscapeRecorder, RateLimitRegistry, AuditedHTTPClient, AuditedLLMClient, and hashing utilities. The single largest coupling vector in the codebase.
- `config/protocols.py` -- Runtime-checkable protocols defining what engine components expect from configuration.
- `config/runtime.py` -- Frozen dataclasses with `from_settings()` for the Settings-to-Runtime bridge.
- `schema_contract.py` -- PipelineRow, SchemaContract, FieldContract -- the data model for pipeline data flow.
- `events.py` -- TelemetryEvent base class and all concrete event types.
- `results.py` -- TransformResult, GateResult, ExceptionResult.
- `enums.py` -- NodeStateStatus, RunStatus, RowOutcome, TriggerType, BackpressureMode, etc.

**Dependencies:**
- Inbound: Every subsystem imports from contracts (8 inbound).
- Outbound: core (11 imports), engine (1 import), plugins (3 imports).
- Layer violations: **HIGH** -- L0 imports upward into L1 (core), L2 (engine), and L3 (plugins). The `PluginContext` god object is the primary cause, importing LandscapeRecorder, RateLimitRegistry, AuditedHTTPClient, AuditedLLMClient. `results.py` imports MaxRetriesExceeded from engine. `node_state_context.py` imports BufferEntry from plugins.

**Top Concerns:**
- P1: PluginContext god object creates bidirectional cycles with core and plugins -- the number one coupling vector.
- P2: 11 upward imports into core violate the L0 foundation principle.
- P2: Untyped `dict[str, Any]` crossing into audit trail at multiple boundaries (10 open bugs).

**Confidence:** Medium -- inferred from dependency analysis and cross-references in other analysis files.

---

## Core: Services (Security, Rate Limiting, Retention, Utilities)

**Location:** `src/elspeth/core/security/`, `core/rate_limit/`, `core/retention/`, `core/logging.py`, `core/operations.py`, `core/payload_store.py`, `core/events.py` | **Size:** ~2,200 lines, 11 files | **Layer:** L1

**Responsibility:** Cross-cutting infrastructure services: secret management with HMAC fingerprinting, SSRF prevention with DNS pinning, per-service rate limiting, payload retention/purge, content-addressable storage, structured logging, synchronous event bus, and operation lifecycle tracking.

**Internal Architecture:**
Four distinct clusters. Security (`config_secrets.py`, `fingerprint.py`, `secret_loader.py`, `web.py`) handles secrets and SSRF with protocol-based abstractions and lazy Azure imports. Rate limiting (`limiter.py`, `registry.py`) wraps pyrate-limiter with per-service caching and a null-object pattern. Retention (`purge.py`) manages payload expiration with set-difference anti-join for content-addressable dedup safety. Utilities are standalone modules with minimal coupling.

**Key Components:**
- `security/web.py` -- SSRF prevention via SSRFSafeRequest frozen dataclass with DNS-pinned IP. Architecturally sound; caller verification needed.
- `security/config_secrets.py` -- Two-phase secret loading (fetch all, then apply all) with HMAC fingerprints.
- `rate_limit/limiter.py` -- pyrate-limiter wrapper with SQLite persistence option.
- `retention/purge.py` -- Payload purge with active-run exclusion and reproducibility grade degradation.
- `payload_store.py` -- Content-addressable filesystem storage with atomic writes, path traversal prevention, and timing-safe integrity checks.
- `events.py` -- Synchronous event bus (zero dependencies, protocol-based).

**Dependencies:**
- Inbound: engine, plugins, cli, mcp, tui (8 inbound total across all core).
- Outbound: contracts (type imports), pyrate-limiter, structlog.
- Layer violations: None within this cluster.

**Top Concerns:**
- P1: SSRF caller-site audit needed -- defense is only effective if callers use `connection_url` + `host_header`, not `original_url`.
- P2: Untyped resolution records in `config_secrets.py` (dict at Tier 1 boundary).
- P2: PurgeResult mutable with vestigial `bytes_freed` field.
- P3: Spin-wait polling in rate limiter `acquire()`.

**Confidence:** High.

---

## Core: Landscape (Audit Trail)

**Location:** `src/elspeth/core/landscape/` | **Size:** ~5,000 lines (estimated), ~10 files | **Layer:** L1

**Responsibility:** The audit backbone -- records every operation, row state, node state, routing event, and artifact for complete traceability. Schema definition, recording, lineage queries, reproducibility grading, and export.

**Internal Architecture:**
Built on SQLAlchemy Core (no ORM). `schema.py` defines all tables. `recorder.py` is the central recording API used by every executor. `database.py` manages connection lifecycle. `lineage.py` provides the `explain()` query for full token tracing. `reproducibility.py` tracks grade degradation after payload purge. `formatters.py` provides serialization utilities.

**Key Components:**
- `recorder.py` -- LandscapeRecorder: the most-imported class in the codebase. Every executor depends on it for audit recording.
- `schema.py` -- Table definitions including the composite PK pattern on `nodes` (`node_id`, `run_id`).
- `database.py` -- LandscapeDB: connection management with SQLite and SQLCipher support.
- `lineage.py` -- Token lineage query used by MCP `explain_token` and CLI `explain`.

**Dependencies:**
- Inbound: contracts (PluginContext), engine (all executors), plugins (via context), mcp (all analyzers), tui, cli.
- Outbound: contracts (enums, types), SQLAlchemy.
- Layer violations: None.

**Top Concerns:**
- P2: LandscapeRecorder is the single largest runtime dependency -- every executor, the MCP server, and the CLI all depend on it.
- P3: The `(db, recorder)` pair is threaded through every MCP analyzer function signature.

**Confidence:** Medium -- inferred from dependency analysis and references in engine/MCP analyses.

---

## Core: DAG and Configuration

**Location:** `src/elspeth/core/dag/`, `core/config.py`, `core/templates.py`, `core/identifiers.py`, `core/canonical.py` | **Size:** ~3,000 lines (estimated), ~10 files | **Layer:** L1

**Responsibility:** DAG construction, validation, and graph models (NetworkX-based). Configuration loading (Dynaconf + Pydantic). Deterministic JSON canonicalization (RFC 8785). ID generation. Jinja2 field extraction.

**Internal Architecture:**
The DAG subsystem (`dag/builder.py`, `dag/graph.py`, `dag/models.py`) compiles pipeline YAML into an execution graph, validates schema contracts across edges, and provides topological sort. Configuration (`config.py`) loads multi-source settings with Pydantic validation. `canonical.py` implements two-phase canonicalization (normalize then RFC 8785).

**Key Components:**
- `dag/builder.py` -- Builds ExecutionGraph from plugin instances.
- `dag/graph.py` -- ExecutionGraph with NetworkX backing.
- `config.py` -- ElspethSettings, all *Settings Pydantic models.
- `canonical.py` -- `canonical_json()`, `stable_hash()`, `repr_hash()`.

**Dependencies:**
- Inbound: engine (orchestrator, processor), cli, contracts (runtime configs import Settings).
- Outbound: contracts (protocols), plugins (SourceProtocol, TransformProtocol, SinkProtocol), engine (ExpressionParser).
- Layer violations: **MEDIUM** -- `core/config.py` imports ExpressionParser from engine (L2). DAG modules import plugin protocols from plugins (L3).

**Top Concerns:**
- P2: Bidirectional cycle between core and engine via ExpressionParser import.
- P2: Plugin protocols live in `plugins/protocols.py` but are imported by core DAG -- should be in contracts.
- P3: `canonical.py` imported by contracts, creating an L0-to-L1 dependency.

**Confidence:** Medium -- inferred from dependency analysis.

---

## Engine: Execution Layer

**Location:** `src/elspeth/engine/` | **Size:** ~5,500 lines, 14 files | **Layer:** L2

**Responsibility:** Pipeline execution: DAG traversal, transform/gate/sink/aggregation execution with full audit recording, retry management, token lifecycle, trigger evaluation, expression parsing, coalesce barriers, and batch adapter bridging.

**Internal Architecture:**
Four executors (`executors/transform.py`, `executors/gate.py`, `executors/sink.py`, `executors/aggregation.py`) follow a consistent audit-open-execute-close pattern. `processor.py` drives DAG traversal via a work queue. `retry.py` wraps tenacity. `tokens.py` manages token lifecycle (create, fork, coalesce, expand). `triggers.py` evaluates aggregation trigger conditions. `coalesce_executor.py` implements fork/join barriers with four merge policies. `expression_parser.py` provides safe AST-based expression evaluation. `batch_adapter.py` bridges synchronous orchestrator with async batch transforms.

**Key Components:**
- `executors/transform.py` (488 lines) -- TransformExecutor with NodeStateGuard, batch mixin detection, contract propagation.
- `executors/aggregation.py` (943 lines) -- Largest executor; full batch lifecycle with checkpoint/restore.
- `coalesce_executor.py` (1,083 lines) -- Most complex component; stateful barrier with 4 policies, 3 merge strategies, bounded memory.
- `expression_parser.py` (657 lines) -- Safe AST-based parser with whitelist validation and immutable operator tables.
- `executors/state_guard.py` (203 lines) -- Context manager guaranteeing terminal node state.
- `tokens.py` (407 lines) -- Token lifecycle with deepcopy for fork/expand isolation.

**Dependencies:**
- Inbound: cli (orchestrator wiring), contracts (MaxRetriesExceeded import).
- Outbound: contracts (types, enums, errors, protocols), core.landscape (LandscapeRecorder), core.canonical (stable_hash), plugins (BatchTransformMixin, TransformProtocol, SinkProtocol).
- Layer violations: None significant from engine outward. contracts imports engine (MaxRetriesExceeded) -- fixable by moving to contracts.

**Top Concerns:**
- P3: GateExecutor uses manual begin/complete instead of NodeStateGuard (3 separate try/except blocks).
- P3: TokenManager accepts unused `payload_store` parameter (dead code).
- P3: Truthiness checks in spans.py (`if node_id:` instead of `if node_id is not None:`).

**Confidence:** High.

---

## Engine: Orchestration

**Location:** `src/elspeth/engine/orchestrator/` | **Size:** ~3,500 lines (estimated), 5 files | **Layer:** L2

**Responsibility:** Full run lifecycle management: phase orchestration, source ingestion, row processing coordination, aggregation flushing, outcome recording, export, and validation.

**Internal Architecture:**
Split into focused modules: `core.py` (main orchestrator class, run lifecycle), `aggregation.py` (flush coordination), `export.py` (artifact export), `outcomes.py` (terminal state recording), `validation.py` (pre-run validation). The orchestrator owns the EventBus, TelemetryManager, and coordinates all executors.

**Key Components:**
- `core.py` (~2,300 lines) -- Orchestrator class, the integration hub for all engine components.

**Dependencies:**
- Inbound: cli (creates and invokes orchestrator).
- Outbound: All engine executors, core.landscape, core.checkpoint, core.dag, contracts, telemetry.
- Layer violations: None.

**Top Concerns:**
- P2: `core.py` is the second-largest file in the codebase at ~2,300 lines.

**Confidence:** Medium -- inferred from dependency analysis and engine execution analysis.

---

## Plugins: Sources and Sinks

**Location:** `src/elspeth/plugins/sources/`, `plugins/sinks/` | **Size:** ~2,800 lines, 7 files | **Layer:** L3

**Responsibility:** Data ingestion (CSV, JSON, Null sources) and output (CSV, JSON, Database sinks) with trust-tier-compliant validation at boundaries.

**Internal Architecture:**
Sources use a streaming iterator pattern (`load()` yields `SourceRow`). Sinks use batch writes with lazy initialization. Both clusters share `BaseSource`/`BaseSink` from `plugins/base.py` and config models from `plugins/config_base.py`. Field normalization (`field_normalization.py`) is a pure utility with versioned, auditable resolution.

**Key Components:**
- `csv_source.py` -- Comprehensive Tier 3 handling: UnicodeDecodeError, csv.Error, column mismatch, Pydantic validation, contract violation all quarantined.
- `json_source.py` -- NaN/Infinity rejection via `parse_constant` hook. Surrogateescape handling for broken encodings.
- `json_sink.py` -- JSON array format uses atomic temp-file + `os.replace()` (P0 data loss resolved).
- `database_sink.py` -- SQLAlchemy Core with canonical JSON hash before INSERT (proves intent).
- `field_normalization.py` -- 9-step normalization pipeline, collision detection, versioned algorithm.

**Dependencies:**
- Inbound: engine (executors invoke plugins), cli (instantiation).
- Outbound: contracts (SourceRow, PipelineRow, ArtifactDescriptor), plugins/base, core.canonical (database_sink only).
- Layer violations: None.

**Top Concerns:**
- P1: DRY violation -- 4 display-header methods duplicated verbatim between csv_sink.py and json_sink.py.
- P1: JSONL sink full-file hash on every write (O(N^2) total cost vs CSVSink's incremental O(N)).
- P1: JSONL sink missing `newline=""` on file open (Windows portability).
- P2: FieldResolution has mutable list/dict inside frozen dataclass.
- P2: DatabaseSink auto-commits per batch with no rollback capability.

**Confidence:** High.

---

## Plugins: Transforms

**Location:** `src/elspeth/plugins/transforms/` | **Size:** ~3,500 lines, 15 files | **Layer:** L3

**Responsibility:** Row processing plugins: field mapping, truncation, keyword filtering, JSON deaggregation, batch statistics, batch replication, web scraping with SSRF prevention, and Azure content safety/prompt shield transforms.

**Internal Architecture:**
Three clusters. Pure row transforms (FieldMapper, PassThrough, Truncate, KeywordFilter) are stateless 1:1 processors. Deaggregation/batch transforms (JSONExplode, BatchReplicate, BatchStats) handle 1:N or N:M/N:1 with `is_batch_aware` or `creates_tokens`. External-call transforms (WebScrapeTransform, AzureContentSafety, AzurePromptShield) implement Tier 3 boundary validation on HTTP/API responses.

**Key Components:**
- `web_scrape.py` -- URL fetch with SSRF prevention via SSRFSafeRequest, payload storage, content extraction. 4-file cluster.
- `azure/content_safety.py` -- Azure Content Safety API with exemplary Tier 3 boundary validation. Uses BatchTransformMixin.
- `azure/prompt_shield.py` -- Azure Prompt Shield API with strict bool validation. Structural near-duplicate of content_safety.
- `json_explode.py` -- 1:N deaggregation with `creates_tokens = True` and heterogeneous-type handling.
- `batch_replicate.py` -- N:M replication with max_copies bound.
- `keyword_filter.py` -- Regex scanning with partial ReDoS protection.

**Dependencies:**
- Inbound: engine (TransformExecutor invokes via TransformProtocol).
- Outbound: contracts (PipelineRow, TransformResult, PluginContext), plugins/base, plugins/batching (mixin), plugins/pooling (executor), core.security.web (SSRF), plugins/clients (HTTP, LLM).
- Layer violations: None.

**Top Concerns:**
- P1: BatchReplicate quarantined rows buried in success_reason metadata -- not recorded as distinct terminal tokens.
- P2: AzureContentSafety/AzurePromptShield ~200 lines structural duplication.
- P2: `assert` guards stripped in `-O` mode (web_scrape, azure transforms).
- P3: `_get_fields_to_scan()` triplicated across KeywordFilter and both Azure transforms.
- P3: KeywordFilter silently skips non-string configured fields (fail-open for security transform).
- P3: `validate_input` config field stored but never used in FieldMapper and PassThrough.

**Confidence:** High.

---

## Plugins: Batching and Pooling

**Location:** `src/elspeth/plugins/batching/`, `plugins/pooling/` | **Size:** ~2,400 lines, 8 files | **Layer:** L3

**Responsibility:** Two-level concurrency infrastructure. Batching (row-level): concurrent sub-task processing with FIFO output ordering via BatchTransformMixin and RowReorderBuffer. Pooling (query-level): within-row parallel API calls with AIMD throttle and ReorderBuffer.

**Internal Architecture:**
Batching provides `BatchTransformMixin` (mixin for transforms), `RowReorderBuffer` (blocking FIFO buffer with backpressure), and `OutputPort` (protocol decoupling transforms from downstream). Pooling provides `PooledExecutor` (ThreadPoolExecutor with semaphore, dispatch gate, AIMD retry), `ReorderBuffer` (polling-based FIFO), and `AIMDThrottle` (TCP-style congestion control). The two layers compose: BatchTransformMixin handles row-level concurrency while PooledExecutor handles query-level concurrency within a single row.

**Key Components:**
- `batching/mixin.py` -- BatchTransformMixin: three thread roles (orchestrator, worker pool, release thread).
- `batching/row_reorder_buffer.py` -- Blocking reorder buffer with backpressure and eviction for retry correctness.
- `pooling/executor.py` -- PooledExecutor: semaphore-controlled parallel API calls with AIMD backoff.
- `pooling/throttle.py` -- AIMDThrottle: additive increase / multiplicative decrease state machine.

**Dependencies:**
- Inbound: plugins/transforms (Azure safety, LLM transforms), engine (TransformExecutor detects BatchTransformMixin).
- Outbound: contracts (TransformResult, ExceptionResult, TokenInfo).
- Layer violations: None.

**Top Concerns:**
- P2: Two reorder buffer implementations with overlapping logic but different access patterns (maintenance risk).
- P2: `_batch_lock` in PooledExecutor serializes row-level parallelism for multi-query transforms.
- P3: `flush_batch_processing()` uses polling loop instead of condition-variable wait.
- P3: `CapacityError.retryable` is dead code (never checked).

**Confidence:** High.

---

## Plugins: Core Infrastructure and LLM/Clients

**Location:** `src/elspeth/plugins/base.py`, `plugins/protocols.py`, `plugins/config_base.py`, `plugins/schema_factory.py`, `plugins/llm/`, `plugins/clients/` | **Size:** ~4,000 lines (estimated), ~15 files | **Layer:** L3

**Responsibility:** Plugin base classes and protocols, configuration base models, schema factory, LLM transform implementations (Azure, OpenRouter, multi-query), and audited HTTP/LLM client wrappers.

**Internal Architecture:**
`base.py` provides BaseSource, BaseTransform, BaseSink. `protocols.py` defines SourceProtocol, TransformProtocol, SinkProtocol, BatchTransformProtocol. `clients/http.py` provides AuditedHTTPClient (records all calls to Landscape). `clients/llm.py` provides AuditedLLMClient. LLM transforms use BatchTransformMixin and PooledExecutor for concurrent API calls.

**Key Components:**
- `protocols.py` -- Plugin interface protocols. Imported by core DAG modules (creates L3-to-L1 reverse dependency).
- `clients/http.py` -- AuditedHTTPClient: wraps httpx with Landscape call recording.
- `clients/llm.py` -- AuditedLLMClient: wraps LiteLLM with call recording.

**Dependencies:**
- Inbound: contracts (PluginContext imports clients), core (DAG imports protocols), engine (executors import protocols).
- Outbound: contracts, core.landscape (via PluginContext).
- Layer violations: **HIGH** -- Plugin protocols imported by core DAG (L1). AuditedHTTPClient and AuditedLLMClient imported by contracts PluginContext (L0).

**Top Concerns:**
- P1: Plugin protocols belong in contracts (L0), not plugins (L3). Current location forces upward imports.
- P2: PluginContext imports AuditedHTTPClient and AuditedLLMClient from plugins, creating L0-to-L3 cycle.
- P3: LLM plugin duplication (~6 files with shared logic per MEMORY.md).

**Confidence:** Medium -- inferred from dependency analysis.

---

## Telemetry

**Location:** `src/elspeth/telemetry/` | **Size:** ~2,800 lines, 10 files | **Layer:** L2

**Responsibility:** Operational visibility alongside the Landscape audit trail. Asynchronous event export to OTLP, Azure Monitor, Datadog, or console via a background thread with backpressure management.

**Internal Architecture:**
Central `TelemetryManager` receives events from the engine, filters by granularity, queues to a background thread, and dispatches to configured exporters with per-exporter failure isolation. Factory (`factory.py`) handles pluggy-based exporter discovery. Four exporter implementations (OTLP, Azure Monitor, Datadog, Console) each implement `ExporterProtocol`. Filtering (`filtering.py`) is a single-function pattern-match on event types.

**Key Components:**
- `manager.py` -- TelemetryManager: queue-based async dispatch, BLOCK/DROP backpressure, health metrics.
- `factory.py` -- Exporter discovery and configuration via pluggy.
- `filtering.py` -- Granularity-based event selection (LIFECYCLE/ROWS/FULL).
- `exporters/otlp.py` -- OpenTelemetry OTLP gRPC export with synthetic span construction.
- `exporters/azure_monitor.py` -- Azure Monitor export reusing OTLP span utilities.
- `exporters/datadog.py` -- Datadog export via ddtrace.
- `protocols.py` -- ExporterProtocol defining the 5-method lifecycle contract.

**Dependencies:**
- Inbound: engine (orchestrator emits events), cli (creates manager).
- Outbound: contracts (events, config protocols, enums).
- Layer violations: None.

**Top Concerns:**
- P2: Private symbol sharing -- Azure Monitor imports `_derive_trace_id`, `_generate_span_id`, `_SyntheticReadableSpan` from OTLP module. Should be extracted to shared `_span_utils.py`.
- P2: Duplicated event serialization logic across three exporters (divergence risk).
- P3: Per-exporter persistent failures never independently disable a broken exporter.
- P3: `BackpressureMode.SLOW` defined in enum but unimplemented (dead code per no-legacy policy).

**Confidence:** High.

---

## MCP (Landscape Analysis Server)

**Location:** `src/elspeth/mcp/` | **Size:** 3,817 lines, 7 files | **Layer:** L4

**Responsibility:** Read-only MCP protocol server exposing 23 tools for LLM-driven audit database analysis. Provides diagnostics, lineage queries, performance reports, error analysis, and ad-hoc SQL.

**Internal Architecture:**
Four-layer decomposition: `server.py` (MCP protocol, Tier 3 argument validation, tool dispatch), `analyzer.py` (facade delegating to submodules), `analyzers/queries.py` (CRUD queries with SQL safety validation), `analyzers/reports.py` (computed analysis), `analyzers/diagnostics.py` (emergency diagnostics), `analyzers/contracts.py` (schema contract queries), `types.py` (22 TypedDict return types). Successfully refactored from a ~2,355-line monolith to the current modular structure.

**Key Components:**
- `server.py` (864 lines) -- MCP protocol, 23-tool registration, if/elif dispatch, auto-discovery of audit databases.
- `analyzers/queries.py` (774 lines) -- Core CRUD plus hand-rolled SQL read-only validator.
- `analyzers/reports.py` (710 lines) -- Run summary, DAG structure, performance, LLM usage, outcome analysis.
- `analyzers/diagnostics.py` (449 lines) -- `diagnose()`, `get_failure_context()`, `get_recent_activity()`.

**Dependencies:**
- Inbound: None (leaf node, invoked externally via MCP protocol).
- Outbound: core.landscape (database, recorder, schema, lineage), contracts (enums).
- Layer violations: None.

**Top Concerns:**
- P2: `_ArgSpec` and `inputSchema` in list_tools() are dual representations that can silently diverge.
- P2: if/elif dispatch chain (23 branches) requires 3-place updates per new tool.
- P2: `get_run_summary()` issues 11 separate queries.
- P3: `high_variance` filter uses truthiness on numeric values (excludes zero incorrectly).
- P3: `diagnose()` counts quarantined rows across all historical runs (no time scoping).

**Confidence:** High.

---

## TUI (Terminal UI)

**Location:** `src/elspeth/tui/` | **Size:** 1,134 lines, 6 files | **Layer:** L4

**Responsibility:** Interactive terminal lineage explorer using Textual framework, providing visual DAG navigation and node detail inspection.

**Internal Architecture:**
`ExplainApp` (Textual App subclass) wraps `ExplainScreen` (plain Python class, NOT a Textual Screen) which manages a discriminated union state machine. `LineageTree` builds a tree model from Landscape data. `NodeDetailPanel` renders node state information with Tier 1 validation. `types.py` provides TypedDict contracts.

**Key Components:**
- `explain_app.py` (123 lines) -- Textual App wrapper rendering Static text widgets.
- `screens/explain_screen.py` (404 lines) -- State machine, data loading, widget coordination.
- `widgets/lineage_tree.py` (213 lines) -- Tree model (not a Textual Widget).
- `widgets/node_detail.py` (234 lines) -- Detail panel with audit data validation.

**Dependencies:**
- Inbound: cli (invokes ExplainApp from `explain` command).
- Outbound: core.landscape (database, recorder), contracts (NodeType).
- Layer violations: None.

**Top Concerns:**
- P1: TUI is non-interactive -- renders Static text widgets, not proper Textual Widgets. Refresh, arrow keys, and node selection do not work.
- P1: Token loading always deferred and never completed -- tokens never appear in tree.
- P2: ExplainScreen is a plain Python class misleadingly named as if it were a Textual Screen.
- P2: `--no-tui` text output is the only fully functional path. Recommend removal per no-legacy-code policy, or complete rewrite as proper Textual widgets.

**Confidence:** High.

---

## CLI

**Location:** `src/elspeth/cli.py`, `cli_helpers.py`, `cli_formatters.py` | **Size:** 2,490 lines, 3 files | **Layer:** L4

**Responsibility:** Typer-based CLI with commands: run, explain, validate, resume, purge, health, plugins list. Integration layer connecting configuration, DAG construction, plugin instantiation, orchestration, and output formatting.

**Internal Architecture:**
Monolithic `cli.py` (2,094 lines) contains all commands and shared infrastructure (`_orchestrator_context`, `_load_settings_with_secrets`, `_execute_pipeline_with_instances`). `cli_helpers.py` (212 lines) provides plugin instantiation and database URL resolution. `cli_formatters.py` (184 lines) provides EventBus formatter factories for console and JSON output.

**Key Components:**
- `cli.py` -- All commands plus 650 lines of shared infrastructure. Highest fanout (9 outbound dependencies).
- `cli_helpers.py` -- `instantiate_plugins_from_config()` returns untyped `dict[str, Any]`.
- `cli_formatters.py` -- EventBus formatter factories (console + JSON). Former "x3 duplication" is resolved.

**Dependencies:**
- Inbound: testing (sub-app registration).
- Outbound: contracts, core (config, dag, landscape, checkpoint, payload_store, rate_limit, security), engine, plugins, telemetry, tui, cli_helpers, cli_formatters.
- Layer violations: cli_helpers imports private `_get_plugin_manager` from cli (backwards dependency).

**Top Concerns:**
- P2: `_orchestrator_context()` has split lifecycle -- caller owns db, context manager owns registry/telemetry.
- P2: Error handling boilerplate duplicated across 4 commands calling `_load_settings_with_secrets()`.
- P2: `instantiate_plugins_from_config()` returns untyped dict -- should be a frozen PluginBundle dataclass.
- P2: `resume` command at 450 lines should be extracted.
- P3: Silent passphrase resolution failure in `explain` command.
- P3: Inconsistent error formatting (rich in validate, plain text elsewhere).

**Confidence:** High.

---

## Testing

**Location:** `src/elspeth/testing/` | **Size:** ~2,000 lines (estimated) | **Layer:** L4

**Responsibility:** Test infrastructure: ChaosLLM server (fault injection for LLM transforms), ChaosWeb server, ChaosEngine, and associated test utilities.

**Internal Architecture:**
Provides chaos testing servers that simulate failure modes for external dependencies (LLM APIs, web endpoints). Used by the test suite and registered as a CLI sub-app for manual testing.

**Key Components:**
- `chaosllm/` -- ChaosLLM server with ErrorInjector, LatencySimulator, ResponseGenerator.

**Dependencies:**
- Inbound: cli (sub-app registration).
- Outbound: None (leaf node for internal imports).
- Layer violations: None.

**Top Concerns:**
- P3: Unsandboxed Jinja2 in ChaosLLM generator (per MEMORY.md cross-cutting concerns).

**Confidence:** Medium -- inferred from dependency analysis and MEMORY.md references.

---

## Dependency Cycle Summary

Six bidirectional cycles exist, three at HIGH severity:

| Cycle | Severity | Fix Strategy |
|-------|----------|-------------|
| contracts <-> core | HIGH | Move canonical_json/hashing to contracts; invert Settings->Runtime dependency |
| contracts <-> plugins | HIGH | Move plugin protocols to contracts; refactor PluginContext via DI |
| contracts <-> engine | MEDIUM | Move MaxRetriesExceeded to contracts |
| core <-> engine | MEDIUM | Move ExpressionParser to core or contracts |
| core <-> plugins | MEDIUM | Move plugin protocols to contracts (eliminates this cycle too) |
| cli <-> cli_helpers | LOW | Move plugin manager singleton to separate module |

The PluginContext god object is the single largest coupling vector, creating or contributing to 3 of the 6 cycles. Refactoring it via protocol-based dependency injection would break the contracts-core and contracts-plugins cycles simultaneously.
