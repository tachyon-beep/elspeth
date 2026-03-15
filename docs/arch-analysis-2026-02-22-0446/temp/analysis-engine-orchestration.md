# Engine Orchestration Layer: Architecture Analysis

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Analyst:** Claude Opus 4.6
**Scope:** engine/orchestrator/ (6 files), engine/processor.py, engine/dag_navigator.py

## File Inventory

| File | Lines | Purpose |
|------|-------|---------|
| `orchestrator/core.py` | 2,364 | Orchestrator class -- run lifecycle, resume, plugin coordination |
| `orchestrator/aggregation.py` | 441 | Aggregation timeout checks and end-of-source flush |
| `orchestrator/export.py` | 472 | Post-run landscape export + schema reconstruction for resume |
| `orchestrator/outcomes.py` | 256 | Row outcome accumulation + coalesce timeout/flush helpers |
| `orchestrator/types.py` | 202 | PipelineConfig, RunResult, AggregationFlushResult, ExecutionCounters |
| `orchestrator/validation.py` | 162 | Pre-run route/sink/quarantine destination validation |
| `engine/processor.py` | 1,882 | RowProcessor -- DAG traversal work queue, token processing |
| `engine/dag_navigator.py` | 302 | Pure topology queries for DAG traversal |
| **Total** | **6,081** | |

---

## Per-File Analysis

### 1. orchestrator/core.py (2,364 lines)

**Purpose:** The `Orchestrator` class is the top-level entry point for pipeline execution. It manages the complete run lifecycle: database initialization, graph registration, source loading, row processing, sink writing, checkpointing, export, graceful shutdown, and resume.

**Key classes/functions:**
- `Orchestrator.__init__()` -- Accepts LandscapeDB, event bus, checkpoint manager, clock, rate limit registry, concurrency config, telemetry manager, coalesce limits.
- `Orchestrator.run()` -- Main entry point. Creates a run in Landscape, delegates to `_execute_run()`, handles success/failure/interrupt/BatchPending, manages telemetry and export.
- `Orchestrator.resume()` -- Resumes a failed/interrupted run from checkpoint. Retrieves unprocessed rows, reconstructs schema, delegates to `_process_resumed_rows()`.
- `Orchestrator._execute_run()` -- Core execution: registers graph nodes/edges in Landscape, validates routes, builds processor, iterates source, processes rows, handles aggregation flush, writes to sinks.
- `Orchestrator._process_resumed_rows()` -- Parallel to `_execute_run()` for resume path. Processes pre-stored rows instead of loading from source.
- `Orchestrator._build_processor()` -- Constructs `RowProcessor` with all dependencies (retry, coalesce, traversal context, aggregation state).
- `Orchestrator._build_dag_traversal_context()` -- Translates `ExecutionGraph` topology into the `DAGTraversalContext` consumed by `RowProcessor`.
- `Orchestrator._write_pending_to_sinks()` -- Extracted sink-write orchestration with grouping by PendingOutcome.
- `Orchestrator._cleanup_plugins()` -- Lifecycle teardown: calls `on_complete()` then `close()` on all plugins with error collection.
- `Orchestrator._assign_plugin_node_ids()` -- Sets `node_id` on all plugin instances after graph registration.
- `Orchestrator._shutdown_handler_context()` -- SIGINT/SIGTERM handler context manager for graceful shutdown.
- `Orchestrator._maybe_checkpoint()` -- Post-sink checkpoint creation with frequency control.

**Dependencies:**
- `core.landscape` (LandscapeDB, LandscapeRecorder) -- audit trail
- `core.dag` (ExecutionGraph) -- DAG topology
- `core.operations` (track_operation) -- operation tracking
- `core.canonical` (repr_hash, sanitize_for_canonical, stable_hash) -- hashing
- `core.config` (AggregationSettings, ElspethSettings, GateSettings) -- configuration
- `core.checkpoint` (CheckpointManager, RecoveryManager) -- crash recovery
- `core.events` (EventBusProtocol, NullEventBus) -- CLI observability
- `contracts` -- extensive (PipelineRow, RowOutcome, RunStatus, TokenInfo, etc.)
- `engine.processor` (RowProcessor, DAGTraversalContext, make_step_resolver) -- row processing
- `engine.retry` (RetryManager) -- retry logic
- `engine.spans` (SpanFactory) -- tracing
- `engine.coalesce_executor` (CoalesceExecutor) -- fork/join merge
- `engine.tokens` (TokenManager) -- token lifecycle
- `engine.executors` (SinkExecutor) -- sink writes
- `plugins.protocols` -- plugin interfaces
- `telemetry` -- operational visibility
- Orchestrator submodules (aggregation, export, outcomes, validation)

**Data flow:**
```
PipelineConfig + ExecutionGraph + Settings
        |
        v
   run() / resume()
        |
        v
   _execute_run() / _process_resumed_rows()
        |
        +----> Source.load() -> SourceRow iterator
        |            |
        |            v
        +----> processor.process_row() -> list[RowResult]
        |            |
        |            v
        +----> accumulate_row_outcomes() -> pending_tokens dict
        |            |
        |            v
        +----> _write_pending_to_sinks() -> SinkExecutor.write()
        |
        v
   RunResult
```

**State management:**
- `self._sequence_number` -- monotonic counter for checkpoint ordering
- `self._current_graph` -- set during execution for checkpointing, cleared after
- `counters: ExecutionCounters` -- mutable counters for rows processed/succeeded/failed/etc.
- `pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome]]]` -- tokens awaiting sink write
- `interrupted_by_shutdown: bool` -- graceful shutdown flag
- Phase tracking via event bus emissions

**Error handling:**
- Three distinct exception types: `BatchPendingError` (control flow, not an error), `GracefulShutdownError` (interrupt, run is resumable), general `Exception` (run fails).
- Each path correctly finalizes the run in Landscape (COMPLETED, INTERRUPTED, FAILED).
- Plugin cleanup in `finally` block ensures resources are released even on failure.
- Telemetry flush in `finally` with preservation of pending exceptions.

**Concerns:**
1. **CRITICAL -- `_execute_run()` is ~830 lines of deeply nested code.** This single method spans lines 986-1813 and contains the entire execution lifecycle: graph registration (~200 lines), source loading with quarantine handling (~200 lines), the processing loop (~150 lines), aggregation/coalesce flush (~50 lines), field resolution recording (~50 lines), sink writes (~50 lines), progress reporting (~50 lines), schema contract recording (~30 lines), and shutdown handling. The nesting depth reaches 6 levels (method > try > with > try > for > if).
2. **HIGH -- `_process_resumed_rows()` duplicates ~60% of `_execute_run()`.** Lines 2075-2364 repeat: counter initialization, pending_tokens setup, agg_transform_lookup building, the processing loop pattern (timeout check, process row, accumulate outcomes, coalesce check, shutdown check), end-of-source flush, coalesce flush, sink writes. The extraction of `accumulate_row_outcomes()` and other helpers reduced but did not eliminate this duplication.
3. **MEDIUM -- The quarantine handling block in `_execute_run()` is ~130 lines (1375-1524).** This inline block handles quarantine token creation, audit trail recording (node_state, routing_event), telemetry, progress emission, and shutdown check. It is a complete mini-pipeline that could be extracted.
4. **MEDIUM -- `run()` has significant ceremony around telemetry and event emission.** Each exit path (success, BatchPending, GracefulShutdown, failure) must emit RunFinished telemetry and RunSummary events with correct metrics. This creates 4 nearly identical blocks of event emission code.
5. **LOW -- Repeated `graph.get_*()` calls.** `get_source()`, `get_sink_id_map()`, `get_transform_id_map()`, `get_config_gate_id_map()` are called in both `_execute_run()` (lines 1032-1036) and again (lines 1184-1190) after the graph phase. The second set overwrites the first. One set should be removed.

---

### 2. orchestrator/aggregation.py (441 lines)

**Purpose:** Stateless helper functions for aggregation timeout checking and end-of-source buffer flushing. Called by the orchestrator's processing loop.

**Key functions:**
- `find_aggregation_transform()` -- Finds the batch-aware transform for a given aggregation node ID.
- `handle_incomplete_batches()` -- Recovery: marks EXECUTING batches as FAILED, retries FAILED batches, leaves DRAFT batches.
- `check_aggregation_timeouts()` -- Called BEFORE each row to flush timed-out aggregation batches. Returns `AggregationFlushResult`.
- `flush_remaining_aggregation_buffers()` -- Called at end-of-source to flush any remaining buffered rows. Returns `AggregationFlushResult`.
- `_route_aggregation_outcome()` -- Routes non-failed aggregation results to pending_tokens.
- `_require_sink_name()` -- Invariant: outcomes that route to sinks must have sink_name set.

**Dependencies:**
- `contracts` (PendingOutcome, RowOutcome, TokenInfo, TriggerType, OrchestrationInvariantError, NodeID)
- `orchestrator.types` (AggregationFlushResult, PipelineConfig)
- `processor.RowProcessor` (TYPE_CHECKING)
- `plugins.protocols.TransformProtocol` (TYPE_CHECKING)

**Data flow:**
```
PipelineConfig + RowProcessor + pending_tokens (mutable)
        |
        v
check_aggregation_timeouts() / flush_remaining_aggregation_buffers()
        |
        v
processor.handle_timeout_flush() -> (completed_results, work_items)
        |
        +----> Terminal results -> pending_tokens
        |
        +----> Work items -> processor.process_token() -> pending_tokens
        |
        v
AggregationFlushResult (counters)
```

**State management:** Stateless. All state is passed in via parameters and returned via `AggregationFlushResult`.

**Error handling:** `OrchestrationInvariantError` for Tier 1 violations (sink not found), `RuntimeError` for internal bugs (missing batch-aware transform, missing current_node_id).

**Concerns:**
1. **HIGH -- Massive code duplication between `check_aggregation_timeouts()` and `flush_remaining_aggregation_buffers()`.** The work_items processing loop (lines 249-294 and 384-429) is identical -- same outcome routing switch, same counter updates, same invariant checks. The only differences are: (a) the trigger condition (timeout vs end-of-source), (b) the iterator (filtered aggregation_settings vs all). The `accumulate_row_outcomes()` helper was created to solve exactly this pattern but was not used here.
2. **MEDIUM -- `_route_aggregation_outcome()` only handles COMPLETED.** The docstring says ROUTED and COALESCED are handled inline. This creates an inconsistency where the routing switch in the two main functions must handle all outcomes except COMPLETED and FAILED separately.

---

### 3. orchestrator/export.py (472 lines)

**Purpose:** Two distinct responsibilities: (1) post-run landscape audit trail export to JSON/CSV format, and (2) Pydantic schema reconstruction from JSON schema for pipeline resume.

**Key functions:**
- `export_landscape()` -- Exports audit trail to a configured sink (JSON or CSV format).
- `_export_csv_multifile()` -- Writes separate CSV files per record type.
- `reconstruct_schema_from_json()` -- Reconstructs a Pydantic model class from a JSON schema dictionary.
- `_json_schema_to_python_type()` -- Maps JSON Schema types to Python types (string, datetime, Decimal, arrays, nested objects, nullable types, $ref resolution).
- `_create_schema_model()` -- Builds a Pydantic model from properties and required fields.
- `_model_name_for_field()` -- Generates deterministic nested model names.

**Dependencies:**
- `core.landscape.exporter` (LandscapeExporter)
- `core.landscape.formatters` (CSVFormatter)
- `core.landscape.recorder` (LandscapeRecorder)
- `contracts.plugin_context` (PluginContext)
- `contracts` (PluginSchema)
- Standard library: csv, os, re, pathlib, json
- Pydantic: ConfigDict, create_model

**Data flow:**
- Export path: `LandscapeDB -> LandscapeExporter -> Sink.write() / CSV files`
- Schema reconstruction path: `JSON dict -> _json_schema_to_python_type() -> Pydantic model class`

**State management:** Stateless. Pure functions.

**Error handling:** ValueError for malformed schemas, missing properties, unsupported types. Follows Tier 1 trust model (crash on corruption).

**Concerns:**
1. **MEDIUM -- Two unrelated responsibilities in one module.** `export_landscape()` is a post-run operation. `reconstruct_schema_from_json()` is a resume utility. They share no state, no helper functions, and no conceptual overlap. Schema reconstruction belongs closer to the resume/checkpoint subsystem.
2. **MEDIUM -- CSV export writes directly to filesystem** (lines 168-172) rather than through the sink abstraction. The JSON export uses `sink.write()` but CSV export bypasses it, which means CSV export does not benefit from sink-level error handling or audit recording.
3. **LOW -- `_json_schema_to_python_type()` is complex (165 lines)** with deep branching for anyOf patterns, $ref resolution, format specifiers, array items, nested objects, and additionalProperties. This is inherent complexity from JSON Schema, but the function would benefit from being split into sub-handlers by type category.

---

### 4. orchestrator/outcomes.py (256 lines)

**Purpose:** Row outcome accumulation into `ExecutionCounters` and coalesce timeout/flush handling. Extracted to eliminate duplication between `_execute_run()` and `_process_resumed_rows()`.

**Key functions:**
- `accumulate_row_outcomes()` -- The central outcome switch: maps `RowOutcome` variants to counter increments and pending_tokens routing. Handles COMPLETED, ROUTED, FAILED, QUARANTINED, FORKED, CONSUMED_IN_BATCH, COALESCED, EXPANDED, BUFFERED.
- `handle_coalesce_timeouts()` -- Per-row coalesce timeout check. Iterates registered coalesce names, checks timeouts, routes merged tokens through processor.
- `flush_coalesce_pending()` -- End-of-source coalesce flush. Flushes all pending coalesce operations, routes merged tokens through processor.

**Dependencies:**
- `contracts` (PendingOutcome, RowOutcome, TokenInfo, OrchestrationInvariantError, CoalesceName, NodeID)
- `orchestrator.types` (ExecutionCounters)
- `engine.coalesce_executor` (CoalesceExecutor, TYPE_CHECKING)
- `engine.processor` (RowProcessor, TYPE_CHECKING)

**Data flow:**
```
list[RowResult] -> accumulate_row_outcomes() -> ExecutionCounters (mutated) + pending_tokens (mutated)

CoalesceExecutor -> handle_coalesce_timeouts() / flush_coalesce_pending()
    -> processor.process_token() -> accumulate_row_outcomes()
```

**State management:** Stateless. Mutates externally-owned `ExecutionCounters` and `pending_tokens`.

**Error handling:** `OrchestrationInvariantError` for invalid CoalesceOutcome state (both merged and failed, or neither).

**Concerns:**
1. **MEDIUM -- `handle_coalesce_timeouts()` and `flush_coalesce_pending()` share ~70% identical code.** Both iterate over coalesce outcomes, check merged_token/failure_reason invariants, route merged tokens through `processor.process_token()` + `accumulate_row_outcomes()`, and increment `rows_coalesce_failed`. The only difference is the source of outcomes (check_timeouts vs flush_pending) and the iteration pattern.
2. **LOW -- `_require_sink_name()` is duplicated** between outcomes.py (line 35) and aggregation.py (line 34). Both have identical signatures and logic, though slightly different error messages.

---

### 5. orchestrator/types.py (202 lines)

**Purpose:** Leaf module containing data definitions for the orchestrator package. Designed to have no imports from other orchestrator submodules to prevent circular imports.

**Key types:**
- `RowPlugin = TransformProtocol` -- Type alias for row-processing plugins.
- `PipelineConfig` -- Dataclass holding source, transforms, sinks, gates, aggregation_settings, coalesce_settings.
- `RunResult` -- Result of a pipeline run with all counter fields.
- `AggregationFlushResult` -- Frozen dataclass for aggregation flush results with `__add__` for combining.
- `ExecutionCounters` -- Mutable counters accumulated during execution with `accumulate_flush_result()` and `to_run_result()` conversion.
- `RouteValidationError` -- Exception for invalid route configuration.

**Dependencies:** Minimal. `contracts.RunStatus`, `plugins.protocols.TransformProtocol` at runtime. Config types under TYPE_CHECKING only.

**Data flow:** Pure data definitions. No processing logic.

**Concerns:**
1. **LOW -- `PipelineConfig` is a mutable dataclass** but acts as configuration (should be immutable). Its fields are mutable (list, dict) and could be mutated after construction. However, freezing it would require copying all collections, which adds overhead for marginal safety.
2. **LOW -- `RunResult` and `ExecutionCounters` have overlapping fields.** `ExecutionCounters.to_run_result()` copies 11 fields between them. This is acceptable given their different mutability requirements (counters are mutable during execution, result is the final snapshot).

---

### 6. orchestrator/validation.py (162 lines)

**Purpose:** Pre-run validation of route destinations, transform error sinks, and source quarantine destinations. Validates that all configured destinations reference existing sinks.

**Key functions:**
- `validate_route_destinations()` -- Validates gate route destinations against available sinks.
- `validate_transform_error_sinks()` -- Validates transform `on_error` destinations.
- `validate_source_quarantine_destination()` -- Validates source `on_validation_failure` destination.

**Dependencies:**
- `contracts` (RouteDestination, RouteDestinationKind, GateName)
- `orchestrator.types` (RouteValidationError)

**Data flow:** Takes configuration inputs, raises `RouteValidationError` if invalid. Pure validation, no side effects.

**Concerns:**
1. **LOW -- `validate_source_quarantine_destination()` accesses `source._on_validation_failure`** (line 149), a private attribute. This should use a public property or protocol method.

---

### 7. engine/processor.py (1,882 lines)

**Purpose:** `RowProcessor` processes rows through the DAG-defined pipeline topology. It implements the core work queue model: tokens enter, traverse transforms/gates/aggregations following DAG edges, and exit with terminal outcomes.

**Key classes/functions:**
- `DAGTraversalContext` -- Frozen dataclass with precomputed DAG traversal data (node_step_map, node_to_plugin, first_transform_node_id, node_to_next, coalesce_node_map, branch_first_node). All dicts frozen to `MappingProxyType`.
- `_FlushContext` -- Parametric context capturing differences between timeout/count-triggered aggregation flushes.
- `make_step_resolver()` -- Factory for the `StepResolver` closure used by both RowProcessor and orchestrator.
- `RowProcessor.__init__()` -- Accepts recorder, span_factory, run_id, source_node_id, edge_map, route_resolution_map, traversal, aggregation_settings, retry_manager, coalesce_executor, branch maps, sink_names, clock, max_workers, telemetry_manager. Constructs internal DAGNavigator, TokenManager, TransformExecutor, GateExecutor, AggregationExecutor.
- `RowProcessor.process_row()` -- Entry point for new source rows. Creates initial token, records source node_state, starts work queue drain.
- `RowProcessor.process_existing_row()` -- Entry point for resume (row exists in DB, new token only).
- `RowProcessor.process_token()` -- Entry point for mid-pipeline tokens (coalesce continuations).
- `RowProcessor._drain_work_queue()` -- BFS work queue: dequeues items, calls `_process_single_token()`, appends child items.
- `RowProcessor._process_single_token()` -- The core traversal loop: iterates nodes via `node_to_next`, dispatches to transform/gate/aggregation handlers. Handles COMPLETED, ROUTED, FORKED, QUARANTINED, FAILED, EXPANDED, CONSUMED_IN_BATCH, COALESCED, BUFFERED outcomes.
- `RowProcessor._execute_transform_with_retry()` -- Transform execution with retry logic for transient failures (LLMClientError, ConnectionError, TimeoutError, OSError, CapacityError).
- `RowProcessor._process_batch_aggregation_node()` -- Buffering and flush logic for batch-aware transforms.
- `RowProcessor.handle_timeout_flush()` -- External entry for timeout/end-of-source aggregation flush.
- `RowProcessor._handle_flush_error()` / `_route_passthrough_results()` / `_route_transform_results()` -- Shared aggregation flush result routing.
- `RowProcessor._maybe_coalesce_token()` -- Checks if current token should enter coalesce handling.
- `RowProcessor._notify_coalesce_of_lost_branch()` -- Notifies coalesce executor when a forked branch is diverted.
- Telemetry emission methods: `_emit_transform_completed()`, `_emit_gate_evaluated()`, `_emit_token_completed()`.
- Public facades: `check_aggregation_timeout()`, `get_aggregation_buffer_count()`, `get_aggregation_checkpoint_state()`.

**Dependencies:**
- `contracts` -- extensive (RowResult, SourceRow, TokenInfo, TransformResult, PipelineRow, RowOutcome, RouteDestination)
- `engine.dag_navigator` (DAGNavigator, WorkItem) -- topology queries
- `engine.executors` (TransformExecutor, GateExecutor, AggregationExecutor, SinkExecutor, GateOutcome) -- individual node executors
- `engine.retry` (RetryManager, MaxRetriesExceeded) -- retry handling
- `engine.tokens` (TokenManager) -- token lifecycle
- `engine.spans` (SpanFactory) -- tracing
- `engine.clock` (Clock, DEFAULT_CLOCK) -- time abstraction
- `engine.coalesce_executor` (CoalesceExecutor) -- fork/join merge
- `core.landscape` (LandscapeRecorder) -- audit recording
- `core.config` (AggregationSettings, GateSettings) -- configuration
- `plugins.protocols` (TransformProtocol, BatchTransformProtocol) -- plugin interfaces
- `plugins.clients.llm` (LLMClientError) -- retryable error classification
- `plugins.pooling` (CapacityError) -- thread pool errors

**Data flow:**
```
SourceRow / existing row_id
    |
    v
process_row() / process_existing_row() / process_token()
    |
    v
_drain_work_queue(initial_item)
    |
    +---> dequeue WorkItem from deque
    |
    +---> _process_single_token(token, node_id, ...)
    |        |
    |        +---> while node_id is not None:
    |        |        |
    |        |        +---> _maybe_coalesce_token()
    |        |        |
    |        |        +---> TransformProtocol -> _execute_transform_with_retry()
    |        |        |        |
    |        |        |        +---> Success -> update token, advance node
    |        |        |        +---> Error -> QUARANTINED/ROUTED/FAILED
    |        |        |        +---> Multi-row -> expand_token() -> EXPANDED + children
    |        |        |        +---> Batch-aware -> _process_batch_aggregation_node()
    |        |        |
    |        |        +---> GateSettings -> execute_config_gate()
    |        |                 |
    |        |                 +---> Sink route -> ROUTED
    |        |                 +---> Fork -> FORKED + children
    |        |                 +---> Jump -> set node_id
    |        |                 +---> Continue -> advance node
    |        |
    |        +---> End of chain -> COMPLETED with sink_name
    |
    +---> append child_items to queue
    |
    v
list[RowResult] (one per terminal token)
```

**State management:**
- `_aggregation_executor` holds mutable aggregation buffer state
- `_coalesce_executor` holds mutable coalesce barrier state
- `_token_manager` creates tokens (writes to Landscape via recorder)
- `_sequence_number` is NOT on processor (it is on Orchestrator)
- Work queue is local to `_drain_work_queue()` (per-row, not persistent)

**Error handling:**
- `MaxRetriesExceeded` -> FAILED outcome with FailureInfo
- Transform error with `on_error="discard"` -> QUARANTINED
- Transform error with `on_error=<sink>` -> ROUTED to error sink
- `OrchestrationInvariantError` -> crash (Tier 1 violation)
- `MAX_WORK_QUEUE_ITERATIONS` guard -> crash (infinite loop protection)
- Inner traversal max iterations -> crash (cycle detection)
- Coalesce ordering invariant checks at entry and after gate jumps

**Concerns:**
1. **CRITICAL -- `_process_single_token()` is ~375 lines (1482-1882) with deep nesting.** It handles transforms (success, error with discard, error with routing, multi-row expansion, batch aggregation), gates (sink routing, fork, jump, continue), coalesce, and terminal COMPLETED. The transform error handling alone is ~50 lines of duplicated pattern (quarantine check, error hash, record outcome, notify coalesce, build RowResult). This is the most complex method in the entire engine.
2. **HIGH -- `_execute_transform_with_retry()` is ~160 lines (949-1106)** and the no-retry path (lines 974-1077) duplicates significant error handling logic. The LLMClientError handler (lines 985-1031) and the generic transient error handler (lines 1034-1077) are nearly identical: both validate on_error, call ctx.record_transform_error(), record DIVERT routing_event, and return TransformResult.error(). This should be a shared helper.
3. **HIGH -- `_process_batch_aggregation_node()` is ~135 lines (814-947)** with complex control flow for buffer/flush/passthrough/transform modes. The flush path delegates to shared helpers, but the non-flush path (lines 908-947) has its own inline buffered/consumed outcome recording.
4. **MEDIUM -- RowProcessor constructor has 18 parameters.** This is a symptom of the class being responsible for too many concerns: token creation, transform execution, gate evaluation, aggregation handling, coalesce handling, retry, routing, telemetry, and tracing. The DAGNavigator extraction was a step in the right direction but more decomposition is needed.
5. **MEDIUM -- Branch routing logic is scattered.** `_branch_to_coalesce`, `_branch_to_sink`, `BranchName` lookups appear in `_process_single_token()` (lines 1516, 1790-1794, 1861-1864), `_notify_coalesce_of_lost_branch()` (line 1377), and `_derive_coalesce_from_tokens()` (line 540). Branch routing decisions should be centralized.

---

### 8. engine/dag_navigator.py (302 lines)

**Purpose:** Pure topology queries extracted from RowProcessor. Resolves next-nodes, creates work items, resolves terminal sinks, and walks the DAG. All methods are pure queries on immutable data.

**Key classes/functions:**
- `WorkItem` -- Frozen dataclass with token, current_node_id, coalesce_node_id, coalesce_name, on_success_sink. Has invariant: coalesce_node_id and coalesce_name must be both set or both None.
- `DAGNavigator.__init__()` -- Accepts all routing maps, wraps in MappingProxyType.
- `DAGNavigator.from_traversal_context()` -- Factory from DAGTraversalContext.
- `DAGNavigator.create_work_item()` -- Creates WorkItem with coalesce node/name resolution.
- `DAGNavigator.create_continuation_work_item()` -- Creates child work items for fork children and non-fork continuations. Distinguishes fork origin (route to branch-start) from mid-branch continuation (advance to next node).
- `DAGNavigator.resolve_plugin_for_node()` -- Returns plugin/gate for a node, None for structural nodes, crash for unknown nodes.
- `DAGNavigator.resolve_next_node()` -- Next processing node from traversal map.
- `DAGNavigator.resolve_coalesce_sink()` -- Terminal sink for coalesce outcomes.
- `DAGNavigator.resolve_jump_target_sink()` -- Walks DAG from gate jump target to find terminal on_success sink.

**Dependencies:**
- `contracts.errors` (OrchestrationInvariantError)
- `contracts.types` (CoalesceName, NodeID)
- `core.config` (GateSettings)
- `plugins.protocols` (TransformProtocol)

**Data flow:** Pure queries. Reads from immutable topology maps, returns nodes/sinks/WorkItems.

**State management:** Immutable. All maps wrapped in MappingProxyType. No mutable state.

**Error handling:** `OrchestrationInvariantError` for unknown nodes, missing coalesce names, cycles in traversal map, unresolvable sinks.

**Concerns:**
1. **LOW -- `resolve_jump_target_sink()` (lines 191-241) walks the DAG linearly** which is O(N) per call. For pipelines with many gate jumps, this could be precomputed. However, gate jumps are rare in practice, so this is acceptable.
2. **LOW -- `from_traversal_context()` is unused** -- RowProcessor constructs DAGNavigator directly in its `__init__()` rather than using this factory. The factory could be removed to reduce dead code.

---

## Overall Analysis

### 1. Orchestration Model

A pipeline run proceeds through clearly defined phases:

1. **DATABASE** -- Create run in Landscape, record secret resolutions.
2. **GRAPH** -- Register all nodes and edges from ExecutionGraph, validate routes.
3. **SOURCE** -- Call `source.load()`, begin source_load operation tracking.
4. **PROCESS** -- Iterate source rows, process through DAG, accumulate outcomes. Includes per-row aggregation timeout checks, coalesce timeout checks, and graceful shutdown checks.
5. **SINK** -- Write accumulated pending_tokens to sinks via SinkExecutor.
6. **EXPORT** (optional) -- Export audit trail to configured sink.

Run finalization records COMPLETED, INTERRUPTED, or FAILED status. Checkpoints are deleted on success. Resume follows the same phases but skips SOURCE (uses stored payloads).

The model is fundamentally **synchronous and single-threaded**. Rows are processed one at a time through the DAG. Concurrency (max_workers) exists within transform execution (via TransformExecutor's thread pool) but the outer loop is sequential.

### 2. Processor Architecture

The processor uses a **breadth-first work queue** implemented with `collections.deque`. The queue is seeded with one initial WorkItem per source row and drained to completion before the next source row is processed.

**Work queue lifecycle:**
1. Source row -> `process_row()` -> create initial token -> seed work queue
2. `_drain_work_queue()`: while queue is not empty, dequeue -> `_process_single_token()`
3. `_process_single_token()`: traverse nodes linearly via `node_to_next`. At each node, dispatch to transform/gate/aggregation handler. If fork or expansion occurs, append child WorkItems to queue.
4. Terminal states (COMPLETED, ROUTED, FAILED, QUARANTINED) produce RowResult and no children.
5. Non-terminal states (FORKED, EXPANDED) produce parent RowResult AND child WorkItems.

**Safety guards:**
- `MAX_WORK_QUEUE_ITERATIONS = 10,000` -- outer queue loop guard
- `max_inner_iterations = len(node_to_next) + 1` -- per-token traversal guard
- Coalesce ordering invariant checks at entry and after gate jumps

The work queue model is sound for DAG traversal with forks/joins. BFS ensures all children of a fork are processed before downstream coalesce handling, which is correct for barrier semantics.

### 3. Aggregation Handling

Aggregations are stateful transforms that buffer rows until a trigger fires:

- **Count trigger** -- fires when buffer reaches N rows. Handled inside `_process_batch_aggregation_node()` during normal row processing.
- **Timeout trigger** -- fires when buffer age exceeds M seconds. Checked by `check_aggregation_timeouts()` BEFORE each row is processed.
- **Condition trigger** -- expression-based, time-aware. Handled alongside timeout in `check_aggregation_timeouts()`.
- **End-of-source trigger** -- fires at end of source iteration. Handled by `flush_remaining_aggregation_buffers()`.

Two output modes:
- **Passthrough** -- original tokens continue with enriched data. 1:1 input/output ratio required.
- **Transform** -- N input tokens consumed, M output tokens created via expand_token. Original tokens get CONSUMED_IN_BATCH.

The separation between `AggregationExecutor` (buffer management, trigger evaluation) and `RowProcessor` (routing, outcome recording) is clean. The shared flush helpers (`_FlushContext`, `_handle_flush_error`, `_route_passthrough_results`, `_route_transform_results`) eliminated earlier duplication between count-triggered and timeout-triggered paths.

**Known limitation:** True idle timeout (no rows arriving) requires source-level heartbeat rows or source completion. This is documented.

### 4. Export Pipeline

Export happens AFTER run completion, in a separate phase. Two formats:
- **JSON** -- All records written to a single sink via `sink.write()`.
- **CSV** -- Records grouped by type, written to separate files in a directory.

Export status is tracked in Landscape (PENDING -> COMPLETED/FAILED). Export failure after successful run results in PARTIAL status.

Schema reconstruction (`reconstruct_schema_from_json()`) is used during resume to restore type fidelity (datetime, Decimal) from JSON payloads. This is complex but necessary -- JSON loses type information that Pydantic models preserve.

### 5. Outcome Determination

Every row reaches exactly one terminal state. The outcome is determined by the processing path:

| Outcome | Determined By |
|---------|--------------|
| COMPLETED | Token traverses all nodes, reaches end of chain. `sink_name` from last transform's `on_success`. |
| ROUTED | Gate routes to a named sink, or transform error routes to `on_error` sink. |
| FORKED | Gate forks to multiple paths. Parent token gets FORKED, children are new tokens. |
| QUARANTINED | Source validation failure, or transform error with `on_error="discard"`. |
| FAILED | Transform error (after retry exhaustion), coalesce failure, aggregation flush error. |
| CONSUMED_IN_BATCH | Row buffered into aggregation in transform mode. Terminal for this token. |
| COALESCED | Fork children merged by coalesce executor. Merged token is new. |
| EXPANDED | Transform produces multi-row output. Parent gets EXPANDED, children are new tokens. |
| BUFFERED | Row buffered in aggregation passthrough mode. Non-terminal (becomes COMPLETED on flush). |

Outcomes are recorded in two places:
1. **Immediately** -- by processor for FAILED, QUARANTINED, CONSUMED_IN_BATCH, BUFFERED, FORKED, EXPANDED.
2. **Deferred** -- by SinkExecutor.write() for COMPLETED and ROUTED (after sink durability).

This deferred recording is critical for crash safety: a checkpoint before sink write would incorrectly mark a token as complete.

### 6. Run Validation

Validation happens at multiple stages:

**Before processing (fail-fast):**
- Route destinations reference existing sinks (`validate_route_destinations`)
- Transform `on_error` destinations reference existing sinks (`validate_transform_error_sinks`)
- Source `on_validation_failure` destination references existing sink (`validate_source_quarantine_destination`)
- Schema contracts validated at DAG construction time (in ExecutionGraph)

**During processing (per-row):**
- Quarantine destination validation for each quarantined source row
- Coalesce ordering invariant (token cannot start past coalesce point)
- Coalesce ordering invariant after gate jumps
- Work queue iteration guards

**After processing:**
- Run finalization with status
- Checkpoint cleanup on success

### 7. Cross-Cutting Dependencies

The orchestration layer depends on 14+ subsystems:

```
orchestrator/core.py imports from:
  core.landscape (recorder, exporter)
  core.dag (ExecutionGraph)
  core.operations (track_operation)
  core.canonical (hashing)
  core.config (settings types)
  core.checkpoint (CheckpointManager, RecoveryManager)
  core.events (EventBusProtocol)
  contracts (~30 imports)
  engine.processor (RowProcessor)
  engine.retry (RetryManager)
  engine.spans (SpanFactory)
  engine.coalesce_executor (CoalesceExecutor)
  engine.tokens (TokenManager)
  engine.executors (SinkExecutor)
  plugins.protocols
  telemetry
```

This is expected for an orchestrator -- it coordinates all subsystems. The concern is not the import count but whether the orchestrator does too much work inline rather than delegating.

### 8. Complexity Assessment

**Is the orchestrator too complex? Yes, partially.**

The orchestrator package was already split from a 3000+ line monolith into 6 modules. This was a good first step. The current state:

- **types.py** (202) -- Well-factored leaf module. No issues.
- **validation.py** (162) -- Clean, focused. No issues.
- **dag_navigator.py** (302) -- Clean extraction. Immutable, testable.
- **outcomes.py** (256) -- Good extraction, but has internal duplication.
- **aggregation.py** (441) -- Good extraction, but has significant internal duplication.
- **export.py** (472) -- Two unrelated responsibilities.
- **processor.py** (1,882) -- Too large. `_process_single_token` is the most complex method in the engine.
- **core.py** (2,364) -- Still too large. `_execute_run` and `_process_resumed_rows` have significant structural duplication.

The refactoring so far extracted "what happens after processing" (outcomes, aggregation flush, validation, export) but did not address "what happens during processing" (the 830-line `_execute_run` and the 375-line `_process_single_token`).

### 9. Concerns and Recommendations (Ranked by Severity)

#### CRITICAL

**C1. `_process_single_token()` in processor.py is 375 lines with 6+ nesting levels.**
This method is the heart of DAG traversal and handles transforms, gates, aggregations, coalesce, deaggregation, error routing, and telemetry -- all inline. The transform error handling path (QUARANTINED vs ROUTED) is duplicated, and the gate routing path (sink/fork/jump/continue) is deeply nested.

*Recommendation:* Extract `_handle_transform_result()` and `_handle_gate_result()` as separate methods. The transform error handling (quarantine/route) should be a single helper that takes the error_sink and returns a RowResult.

**C2. `_execute_run()` in core.py is 830 lines with deep nesting.**
The method handles graph registration (~200 lines), source loading with quarantine (~200 lines), the processing loop (~150 lines), end-of-source flush (~50 lines), sink writes (~50 lines), and various bookkeeping. The nesting depth (method > try > with > try > for > if) makes it hard to follow.

*Recommendation:* Extract `_register_graph_nodes_and_edges()`, `_handle_quarantined_source_row()`, and `_finalize_source_processing()` as separate methods. The processing loop itself should be tightened to: for each row -> process -> accumulate -> check timeouts -> check shutdown.

#### HIGH

**H1. `_execute_run()` and `_process_resumed_rows()` share ~60% structural duplication.**
Both methods: initialize counters and pending_tokens, build agg_transform_lookup, run the processing loop (with timeout/coalesce checks and shutdown handling), flush remaining aggregations, flush coalesce, write to sinks. The resume path omits source loading and uses `process_existing_row()` instead of `process_row()`, but the surrounding scaffolding is identical.

*Recommendation:* Extract the shared processing loop into a `_process_rows()` method that takes an iterable of (row_id, row_data_or_source_item, is_new) tuples and a source_operation_id (or None for resume). The source-specific logic (quarantine handling, field resolution, schema contract recording) can be handled via callbacks or a strategy pattern.

**H2. Duplicated work-item processing loops in aggregation.py.**
`check_aggregation_timeouts()` and `flush_remaining_aggregation_buffers()` have identical downstream result handling (~45 lines each). The `accumulate_row_outcomes()` helper already exists and handles the same outcome switch.

*Recommendation:* Refactor the work_items processing loop in both functions to use `accumulate_row_outcomes()` instead of inline outcome switching. The completed_results loop that handles terminal aggregation results can remain separate (it is simpler).

**H3. Duplicated transient error handling in `_execute_transform_with_retry()`.**
The no-retry path has two nearly identical exception handlers (LLMClientError and generic transient errors) that both validate on_error, call ctx.record_transform_error(), record DIVERT routing_event, and return TransformResult.error().

*Recommendation:* Extract `_handle_transient_error_no_retry(transform, token, ctx, exception)` that encapsulates the shared logic.

#### MEDIUM

**M1. Two unrelated responsibilities in export.py.**
`export_landscape()` (post-run audit export) and `reconstruct_schema_from_json()` (resume schema restoration) share no code, no state, and no conceptual connection.

*Recommendation:* Move `reconstruct_schema_from_json()` and its helpers to a `core.schema_reconstruction` module or into the checkpoint subsystem where it is consumed.

**M2. Quarantine handling in `_execute_run()` is 130 lines of inline code.**
The quarantine block creates tokens, records node states, records routing events, emits telemetry, tracks progress, and checks for shutdown -- all inline in the processing loop.

*Recommendation:* Extract `_handle_quarantined_row()` method that takes the source_item, row_index, and necessary context.

**M3. RowProcessor constructor has 18 parameters.**
This reflects the class managing too many concerns: token creation, transform execution, gate evaluation, aggregation handling, coalesce handling, retry, routing, and telemetry.

*Recommendation:* Consider grouping related parameters into context objects. For example, a `CoalesceContext` (coalesce_executor, branch_to_coalesce, coalesce_on_success_map) and a `RoutingContext` (edge_map, route_resolution_map, sink_names, branch_to_sink). This would reduce the parameter count and make dependencies explicit.

**M4. Coalesce timeout/flush handlers in outcomes.py share ~70% code.**
`handle_coalesce_timeouts()` and `flush_coalesce_pending()` both iterate outcomes, validate invariants, and route merged tokens.

*Recommendation:* Extract a shared `_process_coalesce_outcomes()` helper.

**M5. Repeated `graph.get_*()` calls in `_execute_run()`.**
Lines 1032-1036 and 1184-1190 call the same graph methods, with the second set overwriting the first.

*Recommendation:* Remove the first set (lines 1032-1036) or restructure so graph data is extracted once.

#### LOW

**L1. `_require_sink_name()` is duplicated between aggregation.py and outcomes.py.** Move to a shared location (types.py or a tiny utils module).

**L2. `DAGNavigator.from_traversal_context()` appears unused.** Verify and remove if confirmed dead code.

**L3. `validate_source_quarantine_destination()` accesses private `_on_validation_failure`.** Should use a public accessor.

**L4. CSV export bypasses sink abstraction.** Writes directly to filesystem instead of through sink.write(). This is a design mismatch.

### 10. Confidence

**Overall confidence: HIGH**

I read every line of all 8 files (6,081 lines total). The analysis is based on direct observation of the code, not inference. The architectural patterns, data flows, and concerns described above are supported by specific line references. The duplication findings are exact (identical outcome switches, identical error handling patterns). The complexity assessment is objective (line counts, nesting depth, parameter counts).

One area of lower confidence: the full interaction between the orchestrator and the `engine/executors/` package (TransformExecutor, GateExecutor, AggregationExecutor, SinkExecutor) was not analyzed in depth, as those files are outside scope. The executor interfaces are understood from their usage patterns in processor.py and core.py, but internal executor complexity could compound the concerns identified here.
