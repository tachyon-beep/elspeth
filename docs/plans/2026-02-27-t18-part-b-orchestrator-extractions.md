# T18 Part B: Orchestrator Extractions

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract 7 methods from `_execute_run()` and `_process_resumed_rows()`, then collapse both into ~90/~60 line orchestration methods.

**Architecture:** Pure extract-method refactoring. Each commit moves code without changing behavior. Methods use the types defined in Part A (`GraphArtifacts`, `RunContext`, `LoopContext`, `AggNodeEntry`).

**Tech Stack:** No new dependencies. Pure code movement.

**Parent plan:** [T18 Implementation Plan Index](2026-02-27-t18-implementation-plan-index.md)

**Pre-requisite:** [Part A](2026-02-27-t18-part-a-types-and-tests.md) must be complete.

---

## Verification command (run after every commit)

```bash
.venv/bin/python -m pytest tests/integration/pipeline/orchestrator/test_t18_characterization.py tests/unit/engine/test_processor.py tests/integration/pipeline/orchestrator/ tests/property/engine/ -x --tb=short
```

---

## Commit #3: Extract `_register_graph_nodes_and_edges()`

**Risk:** Lower (pure move of self-contained block)

### Task 3.1: Extract the GRAPH phase from `_execute_run()`

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py`

**Step 1: Add the new method**

Add a new method `_register_graph_nodes_and_edges()` to the `Orchestrator` class. This method contains the code currently at lines 1018-1183 of `_execute_run()`.

The method signature (from design):

```python
def _register_graph_nodes_and_edges(
    self,
    recorder: LandscapeRecorder,
    run_id: str,
    config: PipelineConfig,
    graph: ExecutionGraph,
) -> GraphArtifacts:
    """Register all graph nodes and edges in Landscape. Returns artifacts for subsequent phases.

    Performs the GRAPH phase:
    1. Build node_to_plugin mapping from config
    2. Register each node with Landscape (metadata, determinism, schema)
    3. Register edges and build edge_map
    4. Validate route destinations, error sinks, quarantine destinations

    Args:
        recorder: LandscapeRecorder for audit trail
        run_id: Run identifier
        config: Pipeline configuration
        graph: Execution graph

    Returns:
        GraphArtifacts with edge_map, source_id, and all ID mappings
    """
```

The method body is the existing code from lines 1018-1183. It must:
1. Move the `execution_order` extraction, `node_to_plugin` building, ID map extraction (lines 1028-1060)
2. Move the GRAPH phase try/except block (lines 1062-1182)
3. After the GRAPH phase, extract the explicit node ID re-reads (lines 1184-1191)
4. Return `GraphArtifacts(edge_map=edge_map, source_id=source_id, sink_id_map=sink_id_map, transform_id_map=transform_id_map, config_gate_id_map=config_gate_id_map, coalesce_id_map=coalesce_id_map)`

Import `GraphArtifacts` in `core.py`:
```python
from elspeth.engine.orchestrator.types import (
    AggNodeEntry,
    ExecutionCounters,
    GraphArtifacts,
    PipelineConfig,
    RouteValidationError,
    RowPlugin,
    RunResult,
)
```

**Step 2: Replace the extracted code in `_execute_run()` with a call**

Replace lines 1018-1191 in `_execute_run()` with:

```python
# Store graph for checkpointing during execution
self._current_graph = graph

# Local imports for telemetry events
from elspeth.telemetry import FieldResolutionApplied, PhaseChanged, RowCreated

# 1. Register graph nodes and edges
artifacts = self._register_graph_nodes_and_edges(recorder, run_id, config, graph)

source_id = artifacts.source_id
sink_id_map = dict(artifacts.sink_id_map)  # Mutable copy for _write_pending_to_sinks
transform_id_map = artifacts.transform_id_map
config_gate_id_map = artifacts.config_gate_id_map
coalesce_id_map = artifacts.coalesce_id_map
edge_map = dict(artifacts.edge_map)  # Mutable copy for processor
```

Note: `_write_pending_to_sinks` and `RowProcessor` expect mutable dicts for `sink_id_map` and `edge_map`. We unwrap from `MappingProxyType` with `dict()`.

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/integration/pipeline/orchestrator/test_t18_characterization.py tests/integration/pipeline/orchestrator/ -x --tb=short`
Expected: All PASS

**Step 4: Verify with git diff**

Run: `git diff --stat`
Expected: Only `core.py` changed. Lines moved (method extracted), not added.

**Step 5: Commit**

```bash
git add src/elspeth/engine/orchestrator/core.py
git commit -m "refactor(t18): extract _register_graph_nodes_and_edges() from _execute_run()"
```

---

## Commit #4: Extract `_initialize_run_context()`

**Risk:** Lower (pure move)

### Task 4.1: Extract the SETUP+BUILD phase from `_execute_run()`

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py`

**Step 1: Add the new method**

The method contains the code currently at lines ~1193-1265 (after the artifacts call through processor build). Signature from design:

```python
def _initialize_run_context(
    self,
    recorder: LandscapeRecorder,
    run_id: str,
    config: PipelineConfig,
    graph: ExecutionGraph,
    settings: ElspethSettings | None,
    artifacts: GraphArtifacts,
    batch_checkpoints: dict[str, BatchCheckpointState] | None,
    payload_store: PayloadStore,
    *,
    include_source_on_start: bool = True,
) -> RunContext:
    """Initialize run context: assign node IDs, create PluginContext, call on_start, build processor.

    Args:
        include_source_on_start: If True, call source.on_start(). False for resume
            (source was fully consumed in original run).

    Returns:
        RunContext with ctx, processor, coalesce_executor, coalesce_node_map,
        and agg_transform_lookup.
    """
```

The body includes:
1. `_assign_plugin_node_ids()` call
2. `PluginContext` creation
3. `ctx.node_id` assignment
4. `on_start()` calls (conditional on `include_source_on_start`)
5. `_build_processor()` call (with cleanup on failure)
6. `agg_transform_lookup` construction (using `AggNodeEntry`)
7. Return `RunContext(...)`

Import `RunContext` in `core.py`.

**Step 2: Replace extracted code in `_execute_run()` with a call**

```python
# 2. Initialize context + processor
run_ctx = self._initialize_run_context(
    recorder, run_id, config, graph, settings,
    artifacts, batch_checkpoints, payload_store,
)
```

Then destructure what's needed:
```python
ctx = run_ctx.ctx
processor = run_ctx.processor
coalesce_executor = run_ctx.coalesce_executor
coalesce_node_map = run_ctx.coalesce_node_map
agg_transform_lookup = run_ctx.agg_transform_lookup
```

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/integration/pipeline/orchestrator/ -x --tb=short`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/elspeth/engine/orchestrator/core.py
git commit -m "refactor(t18): extract _initialize_run_context() from _execute_run()"
```

---

## Commit #5: Extract `_setup_resume_context()`

**Risk:** Lower (pure move from resume path)

### Task 5.1: Extract graph setup from `_process_resumed_rows()`

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py`

**Step 1: Add the new method**

Extracts lines ~2112-2167 from `_process_resumed_rows()`. Signature:

```python
def _setup_resume_context(
    self,
    recorder: LandscapeRecorder,
    run_id: str,
    config: PipelineConfig,
    graph: ExecutionGraph,
) -> GraphArtifacts:
    """Resume-path equivalent of _register_graph_nodes_and_edges().

    Loads node ID maps and edge_map from database records instead of
    registering new ones. The graph is the same as the original run,
    but nodes/edges already exist in Landscape.

    Returns:
        GraphArtifacts populated from existing Landscape records.
    """
```

The body includes:
1. Getting ID maps from graph
2. Building `edge_map` from `recorder.get_edge_map()`
3. Validating edges exist
4. Getting `route_resolution_map`
5. Calling all three validators
6. Return `GraphArtifacts(...)`

Note: `_setup_resume_context` does NOT need a `route_resolution_map` in GraphArtifacts — it only needs it locally for validation. The route_resolution_map is re-derived when `_build_processor()` is called via `_initialize_run_context()`. Verify this by checking that `route_resolution_map` is passed to `_build_processor()` in the resume path.

Actually — `route_resolution_map` IS passed to `_build_processor()` in both paths (via `_build_processor(route_resolution_map=route_resolution_map,...)`). So it must be available after `_setup_resume_context()`. Two options:
1. Add `route_resolution_map` as a field on `GraphArtifacts`
2. Get it separately after `_setup_resume_context()` returns

The design document says `GraphArtifacts` does NOT include `route_resolution_map`. So get it separately. In the resume path after `_setup_resume_context()`:

```python
artifacts = self._setup_resume_context(recorder, run_id, config, graph)
route_resolution_map = graph.get_route_resolution_map()
```

Wait — `_initialize_run_context()` calls `_build_processor()` which needs `route_resolution_map`. But `_initialize_run_context()` doesn't take it as a parameter (the design shows it takes `artifacts`). Let me re-check the design...

The design shows `_initialize_run_context()` takes `artifacts: GraphArtifacts`. It internally calls `_build_processor()` which needs `route_resolution_map` and `config_gate_id_map`. Both are available: `config_gate_id_map` from `artifacts.config_gate_id_map`, and `route_resolution_map` from `graph.get_route_resolution_map()` (graph is a parameter).

So `_initialize_run_context()` can derive `route_resolution_map` from `graph` internally. This works because `_build_processor` receives it as a parameter.

**Step 2: Replace extracted code in `_process_resumed_rows()` with a call**

```python
# Store graph for checkpointing during execution
self._current_graph = graph

# 1. Setup (loads graph artifacts from original run's DB records)
artifacts = self._setup_resume_context(recorder, run_id, config, graph)
```

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/integration/pipeline/orchestrator/test_t18_characterization.py tests/integration/pipeline/orchestrator/test_resume_guardrails.py -x --tb=short`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/elspeth/engine/orchestrator/core.py
git commit -m "refactor(t18): extract _setup_resume_context() from _process_resumed_rows()"
```

---

## Commit #6: Extract `_handle_quarantine_row()`

**Risk:** Medium-high (quarantine counter correctness, field resolution ordering)

### Task 6.1: Extract the quarantine block from the main loop

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py`

**Step 1: Add the new method**

Extracts lines ~1376-1525 from the `for` loop inside `_execute_run()`. Signature:

```python
def _handle_quarantine_row(
    self,
    recorder: LandscapeRecorder,
    run_id: str,
    source_id: NodeID,
    source_item: SourceItem,
    row_index: int,
    edge_map: Mapping[tuple[NodeID, str], str],
    loop_ctx: LoopContext,
) -> None:
    """Handle a quarantined source row: route directly to configured sink.

    Accesses loop_ctx.processor for token creation and loop_ctx.counters
    for incrementing quarantine count. Appends to loop_ctx.pending_tokens.

    This method performs the complete quarantine workflow:
    1. Validate quarantine destination exists
    2. Sanitize data for canonical JSON
    3. Create quarantine token
    4. Record source node_state (FAILED)
    5. Record DIVERT routing_event
    6. Emit telemetry
    7. Compute error_hash
    8. Append to pending_tokens with PendingOutcome
    """
```

The body is the existing quarantine block (everything inside `if source_item.is_quarantined:` through `continue`), EXCEPT:
- `counters.rows_quarantined += 1` — moved into this method (via `loop_ctx.counters`)
- Progress emission after quarantine — stays in caller (it uses `start_time`, `last_progress_time` etc.)
- `ctx.operation_id = source_operation_id` restore — stays in caller
- Shutdown check — stays in caller

**Step 1.5: Construct `LoopContext` early in `_execute_run()`**

Since `_handle_quarantine_row()` takes `LoopContext`, we need to construct it BEFORE the processing loop. Move `LoopContext` construction to just after the existing `counters` / `pending_tokens` / `agg_transform_lookup` initialization (around line ~1266):

```python
# Pre-compute aggregation transform lookup for O(1) access per timeout check
agg_transform_lookup: dict[str, AggNodeEntry] = {}
if config.aggregation_settings:
    for t in config.transforms:
        if isinstance(t, TransformProtocol) and t.is_batch_aware and t.node_id in config.aggregation_settings:
            agg_transform_lookup[t.node_id] = AggNodeEntry(transform=t, node_id=NodeID(t.node_id))

# Bundle loop state for extracted methods
loop_ctx = LoopContext(
    counters=counters,
    pending_tokens=pending_tokens,
    processor=processor,
    ctx=ctx,
    config=config,
    agg_transform_lookup=agg_transform_lookup,
    coalesce_executor=coalesce_executor,
    coalesce_node_map=coalesce_node_map,
)
```

Then update the remaining inline code in `_execute_run()` to use `loop_ctx.counters` instead of bare `counters`, `loop_ctx.pending_tokens` instead of bare `pending_tokens`, etc. Since `LoopContext` is NOT frozen and holds mutable references, `loop_ctx.counters` IS `counters` — mutations through either reference are visible to both. For this commit, add the construction but keep using the bare variable aliases that already exist (they're the same objects). This avoids a noisy diff of renaming every `counters.x` to `loop_ctx.counters.x`.

**Step 2: Replace the quarantine block in `_execute_run()` with a call**

The `if source_item.is_quarantined:` block becomes:

```python
if source_item.is_quarantined:
    self._handle_quarantine_row(
        recorder, run_id, source_id, source_item, row_index,
        edge_map, loop_ctx,
    )
    # Progress emission for quarantine path
    # (same hybrid timing: first row, every 100, every 5s)
    current_time = time.perf_counter()
    time_since_last_progress = current_time - last_progress_time
    should_emit = (
        counters.rows_processed == 1
        or counters.rows_processed % progress_interval == 0
        or time_since_last_progress >= progress_time_interval
    )
    if should_emit:
        elapsed = current_time - start_time
        self._events.emit(ProgressEvent(...))
        last_progress_time = current_time
    # Restore operation_id before next iteration
    ctx.operation_id = source_operation_id
    # Shutdown check for quarantine path
    if shutdown_event is not None and shutdown_event.is_set():
        interrupted_by_shutdown = True
        break
    continue
```

Note: The progress code still uses bare `counters` — this is fine because `loop_ctx.counters IS counters` (same mutable object). The `_handle_quarantine_row` method increments `loop_ctx.counters.rows_quarantined`, which is visible through the `counters` alias.

Import `LoopContext` at top of core.py and `Mapping` from `collections.abc`.

**Step 3: Run HIGH-RISK test suite**

Run: `.venv/bin/python -m pytest tests/integration/pipeline/orchestrator/ tests/integration/pipeline/ -x --tb=short`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/elspeth/engine/orchestrator/core.py
git commit -m "refactor(t18): extract _handle_quarantine_row() from _execute_run() main loop"
```

---

## Commit #7: Extract `_flush_and_write_sinks()`

**Risk:** Lower (sink write + shutdown + progress code is self-contained)

### Task 7.1: Extract sink writes, shutdown, and final progress

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py`

**Step 1: Add the new method**

Signature:

```python
def _flush_and_write_sinks(
    self,
    recorder: LandscapeRecorder,
    run_id: str,
    loop_ctx: LoopContext,
    sink_id_map: Mapping[SinkName, NodeID],
    interrupted_by_shutdown: bool,
    *,
    on_token_written_factory: _CheckpointFactory | None = None,
) -> None:
    """Write all pending tokens to sinks and handle post-loop bookkeeping.

    IMPORTANT: Aggregation flush and coalesce flush are NOT in this method.
    They stay inside _run_main_processing_loop() / _run_resume_processing_loop()
    because they must execute inside the track_operation(source_load) context
    to preserve audit attribution. At the time those flushes run, ctx.operation_id
    is source_operation_id (restored at end of last loop iteration). Moving them
    here would change it to None, altering the audit trail.

    Handles:
    1. Write pending tokens to sinks (each sink has its own track_operation)
    2. Raise GracefulShutdownError if interrupted
    3. Emit final progress and PROCESS phase completion
    """
```

The body combines only the code OUTSIDE the `track_operation(source_load)` context:
1. `_write_pending_to_sinks()` call (lines ~1743-1772) — internally calls `loop_ctx.processor.resolve_sink_step()` to get `sink_step`
2. Shutdown raise (lines ~1774-1785) — uses `loop_ctx.counters` for the `GracefulShutdownError` fields
3. Final progress emission (lines ~1787-1803) — uses `loop_ctx.counters`
4. PROCESS phase completion event (line ~1806)

**`sink_step` resolution:** The existing `_write_pending_to_sinks()` method takes a `sink_step: int` parameter (computed via `processor.resolve_sink_step()`). Inside `_flush_and_write_sinks()`, compute this from `loop_ctx.processor`:

```python
self._write_pending_to_sinks(
    recorder=recorder,
    run_id=run_id,
    config=loop_ctx.config,
    ctx=loop_ctx.ctx,
    pending_tokens=loop_ctx.pending_tokens,
    sink_id_map=sink_id_map,
    sink_step=loop_ctx.processor.resolve_sink_step(),
    on_token_written_factory=on_token_written_factory,
)
```

Note: The `_write_pending_to_sinks()` call in the resume path (lines ~2335-2344) uses `on_token_written_factory=None` (no checkpointing). This naturally passes through.

Import `_CheckpointFactory` in core.py (from types.py).

**Step 2: Replace extracted code in both `_execute_run()` and `_process_resumed_rows()`**

In `_execute_run()`, the checkpoint_after_sink factory construction stays at the call site:

```python
# 4. Write sinks + shutdown + final progress
def checkpoint_after_sink(sink_node_id: str) -> Callable[[TokenInfo], None]:
    def callback(token: TokenInfo) -> None:
        agg_state = processor.get_aggregation_checkpoint_state()
        self._maybe_checkpoint(run_id=run_id, token_id=token.token_id, node_id=sink_node_id, aggregation_state=agg_state)
    return callback

self._flush_and_write_sinks(
    recorder, run_id, loop_ctx, artifacts.sink_id_map,
    interrupted, on_token_written_factory=checkpoint_after_sink,
)
```

In `_process_resumed_rows()`:
```python
self._flush_and_write_sinks(
    recorder, run_id, loop_ctx, artifacts.sink_id_map,
    interrupted_by_shutdown, on_token_written_factory=None,
)
```

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/integration/pipeline/orchestrator/ -x --tb=short`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/elspeth/engine/orchestrator/core.py
git commit -m "refactor(t18): extract _flush_and_write_sinks() — shared by main and resume paths"
```

---

## Commit #8: Extract `_run_main_processing_loop()` ⚠️ HIGHEST RISK

**Risk:** Highest — `operation_id` lifecycle, quarantine interaction, `track_operation` boundary

### Task 8.1: Extract the main processing loop

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py`

**Step 1: Add the new method**

Signature:

```python
def _run_main_processing_loop(
    self,
    loop_ctx: LoopContext,
    recorder: LandscapeRecorder,
    run_id: str,
    source_id: NodeID,
    edge_map: Mapping[tuple[NodeID, str], str],
    *,
    shutdown_event: threading.Event | None = None,
) -> bool:
    """Run the main processing loop: source iteration, quarantine, transform, flush, progress.

    This method owns the track_operation(source_load) context. Everything inside
    it — source loading, row processing, aggregation flush, coalesce flush, empty
    source handling — executes within source_load operation attribution.

    Sink writes happen OUTSIDE this method in _flush_and_write_sinks(). Each sink
    has its own track_operation(sink_write). This boundary must be preserved — it
    determines audit attribution (source_load vs sink_write operations).

    Returns:
        True if interrupted by shutdown, False otherwise.
    """
```

The body is the remaining code inside the `with track_operation(...)` context, PLUS the aggregation/coalesce flush:
1. SOURCE phase event emission
2. `track_operation(source_load)` context open
3. Source load (`source.load()`)
4. Field resolution tracking flags
5. PROCESS phase event emission
6. The `for row_index, source_item in enumerate(source_iterator):` loop
7. End-of-source aggregation flush (lines ~1648-1666)
8. End-of-source coalesce flush (lines ~1668-1678)
9. Post-loop field resolution for empty sources
10. Post-loop schema contract for empty sources
11. Exception handling (`BatchPendingError`, general)
12. `track_operation` context close

**CRITICAL:** The `track_operation` context manager and its `source_operation_id` capture MUST stay inside this method (they're part of the source phase). The method opens the `track_operation` context and runs the entire processing loop inside it.

**CRITICAL:** Aggregation flush and coalesce flush MUST stay inside this method, inside the `track_operation` context. After the last loop iteration, `ctx.operation_id = source_operation_id` is restored (line ~1646). The flush runs with this attribution. Moving flushes outside `track_operation` would change `ctx.operation_id` from `source_operation_id` to `None`, altering audit attribution for any external calls made during flush (e.g., transforms triggered by aggregation dequeues).

**CRITICAL:** Empty source handling (field resolution + schema contract recording, lines 1682-1729) MUST stay inside this method, inside the `track_operation` context, because these operations are part of source loading (the source may compute field resolution during `load()` even for empty sources).

**Step 2: Replace in `_execute_run()`**

The entire SOURCE+PROCESS phase (lines ~1280-1806) becomes:

```python
# 3. Source + Process phase
interrupted = self._run_main_processing_loop(
    loop_ctx, recorder, run_id, artifacts.source_id, artifacts.edge_map,
    shutdown_event=shutdown_event,
)
```

**Step 3: Run HIGH-RISK test suite**

```bash
.venv/bin/python -m pytest tests/integration/pipeline/orchestrator/ tests/integration/pipeline/ -x --tb=short
```
Expected: All PASS

**Step 4: Verify `track_operation` boundary**

Manually inspect the extracted method to confirm:
- `track_operation(source_load)` context is opened and closed inside the method
- Aggregation flush and coalesce flush ARE inside the method (inside `track_operation`)
- Sink writes are NOT inside the method (they happen in `_flush_and_write_sinks()`)
- `ctx.operation_id` is correctly set/cleared/restored within the loop
- After the loop ends, `ctx.operation_id = source_operation_id` is the last assignment before flush

**Step 5: Commit**

```bash
git add src/elspeth/engine/orchestrator/core.py
git commit -m "refactor(t18): extract _run_main_processing_loop() — highest-risk extraction"
```

---

## Commit #9: Extract `_run_resume_processing_loop()`

**Risk:** Lower (simpler loop, no quarantine/field-resolution/operation_id)

### Task 9.1: Extract the resume processing loop

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py`

**Step 1: Add the new method**

Signature:

```python
def _run_resume_processing_loop(
    self,
    loop_ctx: LoopContext,
    *,
    shutdown_event: threading.Event | None = None,
) -> bool:
    """Run the resume processing loop: iterate unprocessed rows, transform, flush, accumulate.

    Includes end-of-loop aggregation flush and coalesce flush (same as the main
    loop — these must complete before _flush_and_write_sinks() writes to sinks).

    Simpler than the main loop:
    - No quarantine handling (rows already validated)
    - No field resolution (already recorded in original run)
    - No schema contract recording (passed via parameter)
    - No operation_id lifecycle (no source track_operation)
    - No progress emission (known gap — see design doc)

    Returns:
        True if interrupted by shutdown, False otherwise.
    """
```

Wait — the resume loop needs `unprocessed_rows` and `schema_contract` from the caller. These are parameters of `_process_resumed_rows()`, not of `LoopContext`. We need to pass them:

```python
def _run_resume_processing_loop(
    self,
    loop_ctx: LoopContext,
    unprocessed_rows: list[tuple[str, int, dict[str, Any]]],
    schema_contract: SchemaContract,
    *,
    shutdown_event: threading.Event | None = None,
) -> bool:
```

**Step 2: Replace in `_process_resumed_rows()`**

```python
interrupted = self._run_resume_processing_loop(
    loop_ctx, unprocessed_rows, schema_contract,
    shutdown_event=shutdown_event,
)
```

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/integration/pipeline/orchestrator/test_t18_characterization.py tests/integration/pipeline/orchestrator/test_resume_guardrails.py -x --tb=short`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/elspeth/engine/orchestrator/core.py
git commit -m "refactor(t18): extract _run_resume_processing_loop() from _process_resumed_rows()"
```

---

## Commit #10: Collapse `_execute_run()` and `_process_resumed_rows()` ⚠️ HIGH RISK

**Risk:** High — flag inversion risk, divergence accounting

### Task 10.1: Collapse both methods to use extracted methods

**Files:**
- Modify: `src/elspeth/engine/orchestrator/core.py`

**Step 1: Side-by-side review**

Before making changes, manually verify the divergences between the two methods match the design document's divergence table:

| Concern | `_execute_run()` | `_process_resumed_rows()` |
|---------|-------------------|---------------------------|
| Source `on_start()` | Called | Skipped (`include_source_on_start=False`) |
| Graph registration | Registers new nodes/edges | Loads from DB (`_setup_resume_context`) |
| Quarantine routing | Full handling | Not applicable |
| Field resolution | Recorded on first valid row | Skipped |
| Schema contract recording | Recorded on first valid row | Skipped (passed via parameter) |
| `operation_id` lifecycle | Set/clear/restore | Not applicable |
| Progress emission | Every N rows | None (known gap) |
| Checkpointing | `on_token_written_factory` | `None` |

**Step 2: Rewrite `_execute_run()` to use all extracted methods**

The final shape should be ~90 lines:

```python
def _execute_run(self, recorder, run_id, config, graph, settings=None,
                 batch_checkpoints=None, *, payload_store, shutdown_event=None):
    self._current_graph = graph
    from elspeth.telemetry import FieldResolutionApplied, PhaseChanged, RowCreated

    # 1. Register graph
    artifacts = self._register_graph_nodes_and_edges(recorder, run_id, config, graph)

    # 2. Initialize context + processor
    run_ctx = self._initialize_run_context(
        recorder, run_id, config, graph, settings,
        artifacts, batch_checkpoints, payload_store,
    )

    counters = ExecutionCounters()
    pending_tokens = {name: [] for name in config.sinks}

    loop_ctx = LoopContext(
        counters=counters,
        pending_tokens=pending_tokens,
        processor=run_ctx.processor,
        ctx=run_ctx.ctx,
        config=config,
        agg_transform_lookup=run_ctx.agg_transform_lookup,
        coalesce_executor=run_ctx.coalesce_executor,
        coalesce_node_map=run_ctx.coalesce_node_map,
    )

    try:
        # 3. Source + Process phase
        interrupted = self._run_main_processing_loop(
            loop_ctx, recorder, run_id, artifacts.source_id, artifacts.edge_map,
            shutdown_event=shutdown_event,
        )

        # 4. Flush + write sinks
        def checkpoint_after_sink(sink_node_id: str) -> Callable[[TokenInfo], None]:
            def callback(token: TokenInfo) -> None:
                agg_state = run_ctx.processor.get_aggregation_checkpoint_state()
                self._maybe_checkpoint(
                    run_id=run_id, token_id=token.token_id,
                    node_id=sink_node_id, aggregation_state=agg_state,
                )
            return callback

        self._flush_and_write_sinks(
            recorder, run_id, loop_ctx, artifacts.sink_id_map,
            interrupted, on_token_written_factory=checkpoint_after_sink,
        )
    finally:
        self._cleanup_plugins(config, run_ctx.ctx, include_source=True)

    self._current_graph = None
    return counters.to_run_result(run_id, status=RunStatus.RUNNING)
```

**IMPORTANT:** `_execute_run()` returns `RunStatus.RUNNING`, not `COMPLETED`. The public
`run()` wrapper transitions to `COMPLETED` after `finalize_run()`. The characterization
tests assert `RUNNING` — using `COMPLETED` here would break them.

**Step 3: Rewrite `_process_resumed_rows()` with divergence comment block**

The final shape should be ~60 lines with a divergence accounting comment:

```python
def _process_resumed_rows(self, recorder, run_id, config, graph, unprocessed_rows,
                          restored_aggregation_state, settings=None, *,
                          payload_store, schema_contract, shutdown_event=None):
    # ─────────────────────────────────────────────────────────────────
    # Divergence accounting: _process_resumed_rows vs _execute_run
    #
    # Source on_start():       Skipped (include_source_on_start=False)
    # Graph registration:     Loads from DB (_setup_resume_context)
    # Quarantine routing:     Not applicable (rows already validated)
    # Field resolution:       Skipped (loaded from DB in original run)
    # Schema contract:        Skipped (passed via parameter)
    # operation_id lifecycle: Not applicable (no source track_operation)
    # Progress emission:      None (known gap — T24 follow-up)
    # Checkpointing:          None (on_token_written_factory=None)
    # ─────────────────────────────────────────────────────────────────

    self._current_graph = graph

    # 1. Setup (loads graph artifacts from original run's DB records)
    artifacts = self._setup_resume_context(recorder, run_id, config, graph)

    # 2. Initialize context + processor (source on_start skipped)
    run_ctx = self._initialize_run_context(
        recorder, run_id, config, graph, settings,
        artifacts, None, payload_store,
        include_source_on_start=False,
    )

    # Restore contract from run (was recorded during original run)
    run_ctx.ctx.contract = schema_contract

    counters = ExecutionCounters()
    pending_tokens = {name: [] for name in config.sinks}

    loop_ctx = LoopContext(
        counters=counters,
        pending_tokens=pending_tokens,
        processor=run_ctx.processor,
        ctx=run_ctx.ctx,
        config=config,
        agg_transform_lookup=run_ctx.agg_transform_lookup,
        coalesce_executor=run_ctx.coalesce_executor,
        coalesce_node_map=run_ctx.coalesce_node_map,
    )

    try:
        # 3. Process loop (resume path)
        interrupted = self._run_resume_processing_loop(
            loop_ctx, unprocessed_rows, schema_contract,
            shutdown_event=shutdown_event,
        )

        # 4. Flush + write sinks (no checkpointing during resume)
        self._flush_and_write_sinks(
            recorder, run_id, loop_ctx, artifacts.sink_id_map,
            interrupted, on_token_written_factory=None,
        )
    finally:
        self._cleanup_plugins(config, run_ctx.ctx, include_source=False)

    self._current_graph = None
    return counters.to_run_result(run_id, status=RunStatus.RUNNING)
```

**IMPORTANT:** Same as `_execute_run()` — returns `RUNNING`, not `COMPLETED`. The
`resume()` public wrapper handles the status transition. The characterization test
for the resume path also asserts `RUNNING`.

Note: The `restored_aggregation_state` parameter needs to be passed to `_initialize_run_context()` which passes it to `_build_processor()`. This means `_initialize_run_context()` needs a `restored_aggregation_state` parameter. Check if the current implementation passes it through `_build_processor()` — yes it does (line 2219). So add `restored_aggregation_state: dict[str, AggregationCheckpointState] | None = None` to `_initialize_run_context()`.

**Step 4: Run FULL test suite for high-risk commit**

```bash
.venv/bin/python -m pytest tests/ -x --tb=short
```
Expected: All PASS

**Step 5: Run mypy**

```bash
.venv/bin/python -m mypy src/elspeth/engine/orchestrator/core.py
```
Expected: Clean

**Step 6: Commit**

```bash
git add src/elspeth/engine/orchestrator/core.py
git commit -m "refactor(t18): collapse _execute_run() and _process_resumed_rows() using extracted methods"
```

---

## Part B Complete

After these 8 commits (#3-#10):
- `_execute_run()` reduced from ~830 lines to ~90 lines
- `_process_resumed_rows()` reduced from ~290 lines to ~60 lines
- 7 new methods extracted: `_register_graph_nodes_and_edges`, `_initialize_run_context`, `_setup_resume_context`, `_handle_quarantine_row`, `_flush_and_write_sinks`, `_run_main_processing_loop`, `_run_resume_processing_loop`
- Main/resume paths share `LoopContext`, `_flush_and_write_sinks()`, `_initialize_run_context()`
- ~150 lines of duplication eliminated
- Divergence accounting comment block documents all behavioral differences

**Proceed to:** [Part C: Processor Extractions](2026-02-27-t18-part-c-processor-extractions.md)

---

## Post-Implementation Notes

The following deviations from the plan occurred during implementation:

1. **`LoopResult` return type:** The plan shows `_run_main_processing_loop() -> bool` (returning `interrupted`). The implementation returns `-> LoopResult`, a frozen dataclass carrying `(interrupted, start_time, phase_start, last_progress_time)`. This was needed because final progress emission and `PhaseCompleted` must happen AFTER sink writes in `_execute_run()`, not inside the processing loop.

2. **`_flush_and_write_sinks()` scope:** Plan says this method handles progress emission and `PhaseCompleted`. In the implementation, those events are emitted by the caller (`_execute_run()`) using timing data from `LoopResult`, keeping `_flush_and_write_sinks()` focused on sink writes only.

3. **Counter aliasing:** The plan created `counters = ExecutionCounters()` as a bare variable, then passed it into `LoopContext`. Post-review fix inlined the creation directly into `LoopContext(counters=ExecutionCounters(), ...)` and changed all post-construction references to `loop_ctx.counters` to eliminate the aliasing footgun.
