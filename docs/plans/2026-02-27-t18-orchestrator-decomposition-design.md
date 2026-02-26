# T18: Extract Orchestrator Phase Methods

**Date:** 2026-02-27
**Status:** Reviewed
**Branch:** RC3.3-architectural-remediation
**Issue:** elspeth-rapid-cfcbcd
**Review:** 4-agent peer review (architecture critic, systems thinking, quality engineering, Python engineering) — all approve with required changes, incorporated below.

## Problem

Two methods dominate the engine's complexity budget:

| Method | File | Lines | Responsibility |
|--------|------|-------|----------------|
| `_execute_run()` | `orchestrator/core.py` | ~830 | Full pipeline execution lifecycle |
| `_process_single_token()` | `processor.py` | ~400 | Single token DAG traversal |

Additionally, `_execute_run()` and `_process_resumed_rows()` (~290 lines) share ~60% of their structure (processing loop, aggregation flushing, coalesce flushing, sink writes, shutdown handling), duplicating roughly 150 lines.

### Current file sizes

```
orchestrator/core.py      2,365 lines  (Orchestrator class)
processor.py              1,874 lines  (RowProcessor class)
orchestrator/aggregation.py 441 lines  (already extracted)
orchestrator/outcomes.py    258 lines  (already extracted)
orchestrator/validation.py  164 lines  (already extracted)
orchestrator/export.py      472 lines  (already extracted)
dag_navigator.py            302 lines  (already extracted)
```

## Approach: Extract Method

Pure method extraction on existing classes. No new files, no new classes, no behavioral changes. Each extraction is a separately testable commit where `git diff --stat` shows lines moved, not added.

This continues the trajectory already established by the orchestrator submodules (`aggregation.py`, `outcomes.py`, `validation.py`, `export.py`) and `DAGNavigator`, all of which were extracted from these same two classes.

New frozen dataclasses are introduced for return types and parameter bundling (in `engine/orchestrator/types.py`, which already contains `AggregationFlushResult` — a precedent created when it replaced a 9-element tuple). These are data carriers, not behavioral classes.

### Why not Phase Objects or module functions?

- **Phase Objects** require passing ~15 pieces of shared state between phases (recorder, run_id, config, pending_tokens, counters, processor, etc.), creating either a god-object context or verbose constructors. The abstraction cost exceeds the complexity reduction.
- **Module functions** (the pattern used by `aggregation.py` et al.) work well for stateless logic but poorly for the core orchestration loop, which needs access to `self._checkpoint_manager`, `self._events`, `self._telemetry`, etc. The parameter lists become unwieldy.

Method extraction keeps `self` access free while making each method independently readable and testable.

## Part 1: orchestrator/core.py

### New types (in `engine/orchestrator/types.py`)

```python
@dataclass(frozen=True, slots=True)
class GraphArtifacts:
    """Return type for _register_graph_nodes_and_edges().

    Named fields eliminate positional-swap hazards — several members share
    compatible dict[..., NodeID] types that mypy cannot distinguish in a tuple.
    """
    edge_map: dict[tuple[NodeID, str], str]
    source_id: NodeID
    sink_id_map: dict[SinkName, NodeID]
    transform_id_map: dict[int, NodeID]
    config_gate_id_map: dict[GateName, NodeID]
    coalesce_id_map: dict[CoalesceName, NodeID]


@dataclass(frozen=True, slots=True)
class RunContext:
    """Return type for _initialize_run_context().

    Bundles the five objects created during run initialization that are
    consumed by subsequent phases.
    """
    ctx: PluginContext
    processor: RowProcessor
    coalesce_executor: CoalesceExecutor | None
    coalesce_node_map: dict[CoalesceName, NodeID]
    agg_transform_lookup: dict[str, tuple[TransformProtocol, NodeID]]


@dataclass(frozen=True, slots=True)
class LoopContext:
    """Parameter bundle for _process_rows_loop() and _flush_and_write_sinks().

    Reduces 10+ parameter signatures to (self, loop_ctx, ...) and prevents
    parameter-list growth as the loop acquires new concerns.
    """
    processor: RowProcessor
    ctx: PluginContext
    config: PipelineConfig
    counters: ExecutionCounters
    pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]]
    agg_transform_lookup: dict[str, tuple[TransformProtocol, NodeID]]
    coalesce_executor: CoalesceExecutor | None
    coalesce_node_map: dict[CoalesceName, NodeID]
```

### Current `_execute_run()` structure

```
_execute_run() [830 lines]:
    Lines 1018-1060   Telemetry imports + graph metadata extraction
    Lines 1062-1182   GRAPH PHASE — register nodes/edges, validate routes
    Lines 1184-1213   SETUP — assign node IDs, create context, call on_start
    Lines 1234-1265   BUILD — construct processor, pre-compute lookup tables
    Lines 1280-1320   SOURCE PHASE — load source, track operation
    Lines 1346-1646   PROCESS PHASE — row iteration loop
        1346-1374       Field resolution (first iteration)
        1376-1525       Quarantine handling (source validation failures)
        1527-1546       Schema contract recording (first valid row)
        1548-1557       Clear operation_id after source fetch
        1560-1575       Aggregation timeout check (before processing)
        1577-1582       process_row() call
        1584-1591       Outcome accumulation
        1597-1606       Coalesce timeout check
        1608-1629       Progress emission
        1631-1646       Shutdown check + restore operation_id
    Lines 1648-1710   END-OF-SOURCE — flush aggregation, flush coalesce, empty source handling
    Lines 1743-1803   SINK WRITES — write pending, shutdown raise, final progress
    Lines 1808-1814   CLEANUP — finally block
```

### Extracted methods

#### 1. `_register_graph_nodes_and_edges()`

**Source lines:** 1062–1182
**Size:** ~120 lines
**Scope:** GRAPH phase — register nodes, register edges, validate routes

```python
def _register_graph_nodes_and_edges(
    self,
    recorder: LandscapeRecorder,
    run_id: str,
    config: PipelineConfig,
    graph: ExecutionGraph,
) -> GraphArtifacts:
```

Returns a `GraphArtifacts` dataclass with named fields. Emits GRAPH phase events and telemetry.

#### 2. `_initialize_run_context()`

**Source lines:** 1184–1265
**Size:** ~80 lines
**Scope:** Assign plugin node IDs, create PluginContext, call on_start, build processor, pre-compute aggregation lookup

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
```

Takes `GraphArtifacts` as a single parameter instead of 6 individual dicts/IDs (reduces parameter count from 14 to 9). The `include_source_on_start` flag distinguishes main (True) from resume (False — source is not called during resume).

Returns a `RunContext` dataclass with named fields.

#### 3. `_handle_quarantine_row()` (replaces `_iterate_source()` generator)

**Source lines:** 1376–1525
**Size:** ~125 lines
**Scope:** Full quarantine routing for a single source row that failed validation

```python
def _handle_quarantine_row(
    self,
    recorder: LandscapeRecorder,
    run_id: str,
    source_id: NodeID,
    source_item: SourceItem,
    row_index: int,
    edge_map: dict[tuple[NodeID, str], str],
    processor: RowProcessor,
    loop_ctx: LoopContext,
) -> None:
```

Handles:
- Token creation for quarantined row
- Node state recording (begin + complete)
- Routing event recording
- Error hash computation
- Telemetry emission
- Appending to `loop_ctx.pending_tokens` and incrementing `loop_ctx.counters`

**Design rationale (from review):** The original design proposed `_iterate_source()` as a generator that mutated `pending_tokens` and `counters` as side effects while yielding valid rows. Four reviewers rejected this:

1. **GeneratorExit hazard:** If the caller breaks (shutdown), Python sends `GeneratorExit` to the generator frame. If the generator is mid-quarantine-processing (token created, node_state begun, but not yet completed), Landscape records are left incomplete. The quarantine block spans ~125 lines of interleaved Landscape calls — `GeneratorExit` can interrupt any of them.
2. **Hidden mutation:** An iterator that mutates external state through two parameters while also interacting with `self._events`, `self._telemetry`, `recorder`, and `processor.token_manager` is a co-routine masquerading as an iterator. The caller has no indication that quarantined rows are being fully processed as a side effect of iteration.
3. **Untestable quarantine path:** The shared `_process_rows_loop()` could never exercise quarantine behavior — that path was entirely inside the generator.
4. **Operation_id lifecycle breakage:** The `ctx.operation_id` set/clear/restore cycle depends on both the quarantine `continue` path and the normal processing path. Moving this into a generator breaks the containment provided by `with track_operation(...)`.

Instead, `_handle_quarantine_row()` is a regular method called inline in the main loop. The quarantine path is explicit, testable, and cannot be interrupted mid-operation by `GeneratorExit`.

#### 4. `_process_rows_loop()` (shared between main + resume)

**Source lines:** The shared core of the `for` loop from both `_execute_run()` (1346–1646) and `_process_resumed_rows()` (2253–2307)
**Size:** ~80 lines

The main and resume paths have different row types (`int, SourceRow` vs `str, PipelineRow`) and different processor methods (`process_row` vs `process_existing_row`). Rather than erasing this type difference through an untyped `Callable`, we duplicate the ~20 lines of shared bookkeeping:

```python
def _run_main_processing_loop(
    self,
    loop_ctx: LoopContext,
    recorder: LandscapeRecorder,
    run_id: str,
    source_id: NodeID,
    edge_map: dict[tuple[NodeID, str], str],
    *,
    shutdown_event: threading.Event | None = None,
) -> bool:  # returns interrupted_by_shutdown
```

```python
def _run_resume_processing_loop(
    self,
    loop_ctx: LoopContext,
    *,
    shutdown_event: threading.Event | None = None,
) -> bool:  # returns interrupted_by_shutdown
```

**Design rationale (from review):** The original design proposed a single `_process_rows_loop()` with `process_fn: Callable` and `row_iterator: Iterator[...]`. Three reviewers flagged this:

1. **Type erasure:** `Callable` without parameters is `Callable[..., Any]` — mypy cannot verify argument types at either call site. The two lambdas have incompatible signatures.
2. **Incompatible iterator types:** Main yields `SourceRow`, resume yields `tuple[str, PipelineRow]`. The shared loop must accept `Iterator[Any]`.
3. **20 lines below duplication threshold:** The shared loop body (aggregation timeout, process, accumulate outcomes, coalesce timeout, progress, shutdown check) is ~20 lines. Duplicating 20 lines preserves full type safety on the critical path.

The main loop additionally handles quarantine (via `_handle_quarantine_row()`), field resolution, schema contract recording, and `operation_id` lifecycle — none of which exist in the resume path. These make the main loop ~60 lines longer than resume, which is acceptable.

The shared bookkeeping that both loops call:
- `check_aggregation_timeouts()` / `handle_coalesce_timeouts()` (already extracted functions)
- `accumulate_row_outcomes()` (already extracted)
- Progress emission (~5 lines)
- Shutdown check (~3 lines)

#### 5. `_flush_and_write_sinks()`

**Source lines:** 1648–1803 (end-of-source flush + sink writes)
**Size:** ~100 lines

```python
def _flush_and_write_sinks(
    self,
    recorder: LandscapeRecorder,
    run_id: str,
    loop_ctx: LoopContext,
    sink_id_map: dict[SinkName, NodeID],
    interrupted_by_shutdown: bool,
    *,
    on_token_written_factory: Callable[[str], Callable[..., None]] | None = None,
) -> None:
```

Handles:
1. Flush remaining aggregation buffers
2. Flush pending coalesce operations
3. Write pending tokens to sinks (with checkpoint callbacks if `on_token_written_factory` is provided)
4. Raise `GracefulShutdownError` if interrupted
5. Emit final progress

**Design rationale (from review):** The original design used `enable_checkpointing: bool = True` to distinguish main from resume. Reviewers recommended passing `on_token_written_factory: Callable | None` instead — matching the existing `_write_pending_to_sinks()` signature. The checkpoint factory is constructed at the `_execute_run()` level (10 lines, captures `processor` cleanly) and passed as `None` for resume. This documents intent without a boolean flag.

### After extraction: `_execute_run()` becomes ~90 lines

```python
def _execute_run(self, recorder, run_id, config, graph, settings, batch_checkpoints, *,
                 payload_store, shutdown_event):
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
        processor=run_ctx.processor,
        ctx=run_ctx.ctx,
        config=config,
        counters=counters,
        pending_tokens=pending_tokens,
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
        def checkpoint_after_sink(sink_node_id: str) -> Callable[..., None]:
            # ... 10 lines capturing processor for checkpoint ...
            ...

        self._flush_and_write_sinks(
            recorder, run_id, loop_ctx, artifacts.sink_id_map,
            interrupted, on_token_written_factory=checkpoint_after_sink,
        )
    finally:
        self._cleanup_plugins(config, run_ctx.ctx, include_source=True)

    self._current_graph = None
    return counters.to_run_result(run_id)
```

### `_process_resumed_rows()` becomes ~60 lines

```python
def _process_resumed_rows(self, recorder, run_id, config, graph, unprocessed_rows,
                          restored_aggregation_state, settings, *, payload_store,
                          schema_contract, shutdown_event):
    self._current_graph = graph

    # 1. Setup (reuses graph artifacts from original run, loads edges from DB)
    artifacts = self._setup_resume_context(...)

    # 2. Initialize context + processor (source on_start skipped)
    run_ctx = self._initialize_run_context(
        ..., artifacts, ..., include_source_on_start=False,
    )

    counters = ExecutionCounters()
    pending_tokens = {name: [] for name in config.sinks}

    loop_ctx = LoopContext(
        processor=run_ctx.processor,
        ctx=run_ctx.ctx,
        config=config,
        counters=counters,
        pending_tokens=pending_tokens,
        agg_transform_lookup=run_ctx.agg_transform_lookup,
        coalesce_executor=run_ctx.coalesce_executor,
        coalesce_node_map=run_ctx.coalesce_node_map,
    )

    try:
        # 3. Process loop (resume path)
        interrupted = self._run_resume_processing_loop(
            loop_ctx, shutdown_event=shutdown_event,
        )

        # 4. Flush + write sinks (no checkpointing)
        self._flush_and_write_sinks(
            recorder, run_id, loop_ctx, artifacts.sink_id_map,
            interrupted, on_token_written_factory=None,
        )
    finally:
        self._cleanup_plugins(config, run_ctx.ctx, include_source=False)

    self._current_graph = None
    return counters.to_run_result(run_id)
```

---

## Part 2: processor.py

### New types (in `engine/orchestrator/types.py` or `processor.py` private)

```python
@dataclass(frozen=True, slots=True)
class _TransformContinue:
    """Token should advance to the next node in the DAG."""
    updated_token: TokenInfo
    updated_sink: str

@dataclass(frozen=True, slots=True)
class _TransformTerminal:
    """Token has reached a terminal state (completed, failed, quarantined, etc.)."""
    result: RowResult | list[RowResult]

_TransformOutcome = _TransformContinue | _TransformTerminal
```

**Design rationale (from review):** The original design used `tuple[RowResult | list[RowResult] | None, TokenInfo, str]` where `None` meant "continue to next node." This conflates "no result yet" with absence of a value, and the caller must check `if result is not None` after every call while also unpacking two mutable out-parameters. Frozen dataclasses make the semantics explicit to mypy and readers. Precedent: `_FlushContext` in `processor.py` already uses this pattern.

### Current `_process_single_token()` structure

```
_process_single_token() [~400 lines]:
    Lines 1501-1542   Preamble — validation, on_success tracking, coalesce invariant check
    Lines 1543-1568   While loop start — coalesce check, structural node skip
    Lines 1571-1780   Transform handling (isinstance TransformProtocol)
        1575-1584       Batch aggregation dispatch (already extracted)
        1586-1674       Regular transform — retry, error routing, quarantine
        1676-1780       on_success tracking + multi-row/deaggregation
    Lines 1781-1855   Gate handling (isinstance GateSettings)
        1781-1800       Gate evaluation
        1800-1855       Fork/route/divert/continue dispatch
    Lines 1856-1874   Terminal token — end of chain routing
```

### Extracted methods

#### 1. `_handle_transform_node()`

**Size:** ~100 lines

```python
def _handle_transform_node(
    self,
    transform: TransformProtocol,
    current_token: TokenInfo,
    ctx: PluginContext,
    child_items: list[WorkItem],
    coalesce_node_id: NodeID | None,
    coalesce_name: CoalesceName | None,
    last_on_success_sink: str,
) -> _TransformOutcome:
```

Handles:
- Transform execution with retry
- Error routing (quarantine vs error sink)
- MaxRetriesExceeded
- Coalesce branch-loss notification
- Telemetry emission
- on_success tracking
- Multi-row/deaggregation output

Returns `_TransformContinue` when the token should advance to the next node. Returns `_TransformTerminal` when the token has reached a terminal state.

#### 2. `_handle_gate_node()`

**Size:** ~80 lines

```python
def _handle_gate_node(
    self,
    gate: GateSettings,
    current_token: TokenInfo,
    ctx: PluginContext,
    node_id: NodeID,
    child_items: list[WorkItem],
    coalesce_node_id: NodeID | None,
    coalesce_name: CoalesceName | None,
    last_on_success_sink: str,
) -> RowResult | list[RowResult] | None:
```

Handles:
- Gate evaluation via GateExecutor
- FORK_TO_PATHS (create child tokens, queue work items)
- ROUTE_TO_SINK (route to named sink)
- CONTINUE (advance to next node)
- Error handling and coalesce notification

Returns `None` for CONTINUE (token advances). Gate outcomes are simpler than transform outcomes (no mutable token/sink updates), so a `None` sentinel is acceptable here.

#### 3. `_handle_terminal_token()`

**Size:** ~50 lines

```python
def _handle_terminal_token(
    self,
    current_token: TokenInfo,
    last_on_success_sink: str,
    child_items: list[WorkItem],
) -> tuple[RowResult | list[RowResult], list[WorkItem]]:
```

Handles:
- Branch-to-sink routing (for fork branches that route directly to sinks)
- COMPLETED outcome with on_success sink resolution
- ROUTED outcome for named sink routing

### After extraction: `_process_single_token()` becomes ~60 lines

```python
def _process_single_token(self, token, ctx, current_node_id, ...):
    current_token = token
    child_items = []
    last_on_success_sink = on_success_sink or self._source_on_success

    # ... preamble validation (unchanged, ~20 lines) ...

    node_id = current_node_id
    while node_id is not None:
        # Coalesce check
        handled, result = self._maybe_coalesce_token(...)
        if handled:
            return result, child_items

        next_node_id = self._nav.resolve_next_node(node_id)
        plugin = self._nav.resolve_plugin_for_node(node_id)
        if plugin is None:
            node_id = next_node_id
            continue

        if isinstance(plugin, TransformProtocol):
            if plugin.is_batch_aware and ...:
                return self._process_batch_aggregation_node(...)
            outcome = self._handle_transform_node(
                plugin, current_token, ctx, child_items,
                coalesce_node_id, coalesce_name, last_on_success_sink,
            )
            if isinstance(outcome, _TransformTerminal):
                return outcome.result, child_items
            current_token = outcome.updated_token
            last_on_success_sink = outcome.updated_sink

        elif isinstance(plugin, GateSettings):
            result = self._handle_gate_node(
                plugin, current_token, ctx, node_id, child_items,
                coalesce_node_id, coalesce_name, last_on_success_sink,
            )
            if result is not None:
                return result, child_items

        node_id = next_node_id

    return self._handle_terminal_token(current_token, last_on_success_sink, child_items)
```

---

## Implementation Strategy

### Pre-implementation: Characterization tests (commit 0)

Before any extraction, add a characterization test that exercises the full `_execute_run()` path with a pipeline containing:
- At least one quarantined row (source validation failure)
- At least one successfully transformed row
- Aggregation with a count trigger
- A gate that forks to multiple paths

The test must assert:
- `run_result` counter fields (`rows_succeeded`, `rows_failed`, `rows_quarantined`, `rows_routed`)
- `sink.results` contents for each sink
- Audit record counts in `nodes`, `node_states`, `routing_events` tables
- `operation_id` attribution: `ctx.operation_id` is `None` during transform execution (not leaking source operation_id)

This test becomes the regression oracle for the entire extraction sequence.

Additionally, confirm existing coverage for:
- `test_quarantine_routing.py` — counter arithmetic for quarantine
- `test_orchestrator_checkpointing.py` — no checkpoint records during resume
- `test_graceful_shutdown.py` — shutdown branch in the processing loop
- `test_resume_guardrails.py` — flag inversion protection for resume path

### Commit sequence (each independently testable)

0. **Add characterization tests** — regression oracle for extraction sequence
1. **Define `GraphArtifacts`, `RunContext`, `LoopContext` dataclasses** in `engine/orchestrator/types.py`
2. **Define `_TransformContinue`, `_TransformTerminal`** in `processor.py` (private to module)
3. **Extract `_register_graph_nodes_and_edges()`** — pure move, returns `GraphArtifacts`
4. **Extract `_initialize_run_context()`** — pure move, takes `GraphArtifacts`, returns `RunContext`
5. **Extract `_handle_quarantine_row()`** — extract quarantine block from main loop
6. **Extract `_flush_and_write_sinks()`** — pure move, takes `LoopContext` + `on_token_written_factory`
7. **Extract `_run_main_processing_loop()`** — main path processing with quarantine + field resolution
8. **Extract `_run_resume_processing_loop()`** — resume path processing (simpler)
9. **Collapse `_execute_run()` and `_process_resumed_rows()`** — use extracted methods
10. **Extract `_handle_transform_node()`** — pure move, returns `_TransformOutcome`
11. **Extract `_handle_gate_node()`** — pure move from `_process_single_token()`
12. **Extract `_handle_terminal_token()`** — pure move from `_process_single_token()`
13. **Collapse `_process_single_token()`** — use extracted methods

### Risk ranking by commit

| Rank | Commit | Risk | Reason |
|------|--------|------|--------|
| 1 | **#7: `_run_main_processing_loop()`** | Highest | `operation_id` lifecycle lacks direct test coverage; quarantine interaction |
| 2 | **#9: Collapse main+resume** | High | Flag inversion risk (`include_source_on_start`, `on_token_written_factory`) |
| 3 | **#5: `_handle_quarantine_row()`** | Medium-high | Quarantine counter correctness, schema contract recording |
| 4 | **#11: `_handle_gate_node()`** | Medium | Multiple branches (fork/route/continue/error) |
| 5 | **#1-4, 6, 8, 10, 12-13** | Lower | Pure moves or type definitions, well-exercised by existing tests |

### Risk mitigation

- **One extraction per commit.** Run full test suite after each.
- **No behavior changes.** Only move code. If a test fails, it's a move error, not a logic bug.
- **Verify with `git diff --stat`.** Each commit should show lines moved between methods, not net new lines.
- **Integration tests exercise real code paths.** Per CLAUDE.md: "Never bypass production code paths in tests."
- **Focused test runs after each commit:** `pytest tests/unit/engine/test_processor.py tests/integration/pipeline/orchestrator/ tests/property/engine/ -x --tb=short` for fast feedback. Full suite run for the final commit and after high-risk commits (#5, #7, #9).
- **Side-by-side diff of resume path** required before committing #9 (collapse) — verify flag values match intent.

### Verification criteria

- All tests pass after each commit (8,000+ tests)
- mypy clean
- ruff clean
- No method exceeds 150 lines in the final state
- `_execute_run()` is ~90 lines of orchestration
- `_process_single_token()` is ~60 lines of flow control
- `_process_resumed_rows()` shares `LoopContext` and `_flush_and_write_sinks()` with main path
- Characterization test (commit 0) passes after every subsequent commit

### Expected line counts (post-refactor)

| File | Before | After | Delta |
|------|--------|-------|-------|
| `orchestrator/core.py` | 2,365 | ~2,320 | -45 (duplication removed, types moved out) |
| `orchestrator/types.py` | ~100 | ~160 | +60 (new dataclasses) |
| `processor.py` | 1,874 | ~1,890 | +16 (outcome dataclasses added) |

**Note:** This refactoring doesn't reduce total line count significantly. The value is in making each method independently readable and testable, eliminating the main/resume duplication, and introducing type-safe return values.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Extract Method vs Phase Objects vs Module Functions | Extract Method | Keeps `self` access free, minimal abstraction cost, lowest risk |
| Return types | Frozen dataclasses (`GraphArtifacts`, `RunContext`) | Named fields eliminate positional-swap hazards; precedent: `AggregationFlushResult` |
| Parameter bundling | `LoopContext` frozen dataclass | Reduces 10+ parameter signatures; prevents parameter-list growth |
| Main/resume loop unification | Two typed loop methods with shared helpers | Preserves full mypy coverage; 20 lines of shared bookkeeping is below duplication threshold |
| Source iteration | Regular method `_handle_quarantine_row()` (not generator) | Avoids `GeneratorExit` hazard, hidden mutation, untestable quarantine path |
| Transform node return type | `_TransformOutcome` discriminated union | Replaces `None` sentinel + 3-tuple; explicit semantics for continue vs terminal |
| Checkpointing control | `on_token_written_factory: Callable \| None` | Matches existing `_write_pending_to_sinks()` signature; eliminates boolean flag |
| Method vs standalone function for extractions | Private methods on same class | Extracted code needs `self._events`, `self._telemetry`, `self._checkpoint_*` etc. |
| New files? | No (types added to existing `types.py`) | Methods stay on their existing classes. No new modules. |

## Strategic Follow-Up

The main/resume duplication is a mild "Shifting the Burden" archetype (systems thinking review). T18 eliminates the duplicated code but preserves two separate entry points (`_execute_run` and `_process_resumed_rows`). The fundamental solution is a `RowSource` protocol that makes resume a mode rather than a separate code path.

**After T18 completes, create a follow-up task:**

> T24: Introduce `RowSource` protocol to unify main/resume execution
>
> Make `_execute_run()` the only execution path, parameterized by a `RowSource`
> that abstracts both live sources (CSV, API) and resume payloads (stored rows).
> This eliminates the architectural divergence between main and resume at the
> information-flow level, preventing future drift.

This is a Level 6 (Information Flows) intervention that T18's Level 10 (Structure) changes make feasible. Attempting both in one PR would violate T18's "no behavioral changes" principle.
