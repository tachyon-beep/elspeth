# T18: Extract Orchestrator Phase Methods

**Date:** 2026-02-27
**Status:** Reviewed
**Branch:** RC3.3-architectural-remediation
**Issue:** elspeth-rapid-cfcbcd
**Review:** Three review passes — 4-agent peer review (architecture critic, systems thinking, quality engineering, Python engineering). All approve with required changes, incorporated below.

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

New dataclasses are introduced for return types and parameter bundling (in `engine/orchestrator/types.py`, which already contains `AggregationFlushResult` — a precedent created when it replaced a 9-element tuple). Immutable return types use `frozen=True` with `MappingProxyType`-wrapped dict fields; the mutable processing loop state bundle uses `slots=True` only.

### Why not Phase Objects or module functions?

- **Phase Objects** require passing ~15 pieces of shared state between phases (recorder, run_id, config, pending_tokens, counters, processor, etc.), creating either a god-object context or verbose constructors. The abstraction cost exceeds the complexity reduction.
- **Module functions** (the pattern used by `aggregation.py` et al.) work well for stateless logic but poorly for the core orchestration loop, which needs access to `self._checkpoint_manager`, `self._events`, `self._telemetry`, etc. The parameter lists become unwieldy.

Method extraction keeps `self` access free while making each method independently readable and testable.

## Part 1: orchestrator/core.py

### New types (in `engine/orchestrator/types.py`)

```python
from collections.abc import Mapping
from types import MappingProxyType
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class GraphArtifacts:
    """Return type for _register_graph_nodes_and_edges().

    Named fields eliminate positional-swap hazards — several members share
    compatible Mapping[..., NodeID] types that mypy cannot distinguish in a tuple.

    All mapping fields are wrapped in MappingProxyType via __post_init__
    to enforce deep immutability, matching the DAGTraversalContext precedent.
    """
    edge_map: Mapping[tuple[NodeID, str], str]
    source_id: NodeID
    sink_id_map: Mapping[SinkName, NodeID]
    transform_id_map: Mapping[int, NodeID]
    config_gate_id_map: Mapping[GateName, NodeID]
    coalesce_id_map: Mapping[CoalesceName, NodeID]

    def __post_init__(self) -> None:
        object.__setattr__(self, "edge_map", MappingProxyType(dict(self.edge_map)))
        object.__setattr__(self, "sink_id_map", MappingProxyType(dict(self.sink_id_map)))
        object.__setattr__(self, "transform_id_map", MappingProxyType(dict(self.transform_id_map)))
        object.__setattr__(self, "config_gate_id_map", MappingProxyType(dict(self.config_gate_id_map)))
        object.__setattr__(self, "coalesce_id_map", MappingProxyType(dict(self.coalesce_id_map)))


@dataclass(frozen=True, slots=True)
class AggNodeEntry:
    """Named pair for aggregation lookup values.

    Replaces tuple[TransformProtocol, NodeID] to prevent positional-swap bugs,
    applying the same rationale as GraphArtifacts.
    """
    transform: TransformProtocol
    node_id: NodeID


@dataclass(frozen=True, slots=True)
class RunContext:
    """Return type for _initialize_run_context().

    Bundles the five objects created during run initialization that are
    consumed by subsequent phases. Short-lived: consumed immediately to
    build LoopContext. Mapping fields are wrapped in MappingProxyType
    for consistency with GraphArtifacts.
    """
    ctx: PluginContext
    processor: RowProcessor
    coalesce_executor: CoalesceExecutor | None
    coalesce_node_map: Mapping[CoalesceName, NodeID]
    agg_transform_lookup: Mapping[str, AggNodeEntry]

    def __post_init__(self) -> None:
        object.__setattr__(self, "coalesce_node_map", MappingProxyType(dict(self.coalesce_node_map)))
        object.__setattr__(self, "agg_transform_lookup", MappingProxyType(dict(self.agg_transform_lookup)))


@dataclass(slots=True)
class LoopContext:
    """Parameter bundle for _run_main_processing_loop() and _flush_and_write_sinks().

    Reduces 10+ parameter signatures to (self, loop_ctx, ...) and prevents
    parameter-list growth as the loop acquires new concerns.

    NOT frozen: ``counters`` and ``pending_tokens`` are mutated in place
    throughout the processing loop by ``_handle_quarantine_row()``,
    ``_run_main_processing_loop()``, ``_run_resume_processing_loop()``,
    and ``accumulate_row_outcomes()``. All other fields are effectively
    read-only after construction. Field reassignment is prevented by
    convention, not by the dataclass.

    Mutation contracts:
    - ``counters``: incremented by _handle_quarantine_row(),
      _run_main_processing_loop(), _run_resume_processing_loop(),
      accumulate_row_outcomes(), accumulate_flush_result()
    - ``pending_tokens``: appended by _handle_quarantine_row(),
      accumulate_row_outcomes(); consumed (cleared per-sink) by
      _write_pending_to_sinks() inside _flush_and_write_sinks()
    """
    # --- Mutable state (updated row-by-row) ---
    counters: ExecutionCounters
    pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]]

    # --- Read-only after construction (not reassigned) ---
    processor: RowProcessor
    ctx: PluginContext
    config: PipelineConfig
    agg_transform_lookup: Mapping[str, AggNodeEntry]
    coalesce_executor: CoalesceExecutor | None
    coalesce_node_map: Mapping[CoalesceName, NodeID]


_CheckpointFactory: TypeAlias = Callable[[str], Callable[[TokenInfo], None]]
"""Factory that creates a per-sink checkpoint callback.

Takes a sink_node_id (str) and returns a callback invoked after each
token is written to that sink. The inner callable signature matches
_write_pending_to_sinks()'s on_token_written parameter exactly
(verified: core.py line 275).
"""
```

Additionally, `ExecutionCounters.to_run_result()` currently has a dangerous default `status=RunStatus.RUNNING` — every call site that forgets to pass `status` produces a `RunResult` that silently shows RUNNING on completion, an audit integrity risk. This is changed to a required parameter as part of the types commit:

```python
# Before (dangerous default)
def to_run_result(self, run_id: str, status: RunStatus = RunStatus.RUNNING) -> RunResult:

# After (required parameter)
def to_run_result(self, run_id: str, status: RunStatus) -> RunResult:
```

**Preflight required before commit #1:** Run `grep -rn 'to_run_result' src/ tests/` and update every call site that omits `status`. Known call sites requiring update:
- `orchestrator/core.py:1814` — `counters.to_run_result(run_id)` → add `status=RunStatus.COMPLETED`
- `orchestrator/core.py:2365` — `counters.to_run_result(run_id)` → add `status=RunStatus.COMPLETED` (the post-hoc `result.status = RunStatus.COMPLETED` in `resume()` becomes redundant and should be removed)
- `tests/property/engine/test_orchestrator_lifecycle_properties.py` — 5 call sites at lines 419, 441, 457, 478, 691 that pass no `status` argument → add `status=RunStatus.RUNNING` (these tests verify counter field mapping, not status semantics)

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

Takes `GraphArtifacts` as a single parameter instead of 6 individual dicts/IDs (reduces parameter count from 14 to 9). The `include_source_on_start` flag distinguishes main (True) from resume (False — source `on_start()` is not called during resume because the source was fully consumed in the original run; transform/sink `on_start()` calls still fire).

Returns a `RunContext` dataclass with named fields.

#### 3. `_setup_resume_context()`

**Source lines:** 2116–2167
**Size:** ~50 lines
**Scope:** Resume-path equivalent of graph registration — loads node ID maps and edge_map from database records instead of registering new ones

```python
def _setup_resume_context(
    self,
    recorder: LandscapeRecorder,
    run_id: str,
    config: PipelineConfig,
    graph: ExecutionGraph,
) -> GraphArtifacts:
```

Returns a `GraphArtifacts` with the same structure as `_register_graph_nodes_and_edges()`, but populated from existing Landscape records. Includes: getting ID maps, building `edge_map` from database, validating edges, getting route resolution map, and validating route/error/quarantine destinations.

#### 4. `_handle_quarantine_row()` (replaces `_iterate_source()` generator)

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
    edge_map: Mapping[tuple[NodeID, str], str],
    loop_ctx: LoopContext,
) -> None:
```

Accesses `loop_ctx.processor` for token creation (not passed separately — avoids split-brain where `processor` is available both as a parameter and via the bundle).

Handles:
- Token creation for quarantined row (via `loop_ctx.processor.token_manager`)
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

#### 5. `_process_rows_loop()` (shared between main + resume)

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
    edge_map: Mapping[tuple[NodeID, str], str],
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

**`track_operation` boundary constraint:** `_run_main_processing_loop()` is called inside the `track_operation(source_load)` context. `_flush_and_write_sinks()` is called outside it (sinks have their own `track_operation` calls). This boundary must be preserved during extraction — aggregation flushing and sink writes must not be pulled into the processing loop method, as that would change audit attribution.

**Known gap (resume progress):** The resume path currently emits no progress events. This is inherited from the existing implementation — adding progress emission would be a behavioral change outside T18's scope. Noted as a follow-up for T24 or a dedicated task.

**Design rationale (from review):** The original design proposed a single `_process_rows_loop()` with `process_fn: Callable` and `row_iterator: Iterator[...]`. Three reviewers flagged this:

1. **Type erasure:** `Callable` without parameters is `Callable[..., Any]` — mypy cannot verify argument types at either call site. The two lambdas have incompatible signatures.
2. **Incompatible iterator types:** Main yields `SourceRow`, resume yields `tuple[str, PipelineRow]`. The shared loop must accept `Iterator[Any]`.
3. **20 lines below duplication threshold:** The shared loop body (aggregation timeout, process, accumulate outcomes, coalesce timeout, progress, shutdown check) is ~20 lines. Duplicating 20 lines preserves full type safety on the critical path.

The main loop additionally handles quarantine (via `_handle_quarantine_row()`), field resolution, schema contract recording, and `operation_id` lifecycle — none of which exist in the resume path. These make the main loop ~60 lines longer than resume, which is acceptable.

The shared bookkeeping that both loops call:
- `check_aggregation_timeouts()` / `handle_coalesce_timeouts()` (already extracted functions)
- `accumulate_row_outcomes()` (already extracted)
- Progress emission (~5 lines, main only — see known gap above)
- Shutdown check (~3 lines)

#### 6. `_flush_and_write_sinks()`

**Source lines:** 1648–1803 (end-of-source flush + sink writes)
**Size:** ~100 lines

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
```

Handles:
1. Flush remaining aggregation buffers
2. Flush pending coalesce operations
3. Write pending tokens to sinks (with checkpoint callbacks if `on_token_written_factory` is provided)
4. Raise `GracefulShutdownError` if interrupted
5. Emit final progress

**Design rationale (from review):** The original design used `enable_checkpointing: bool = True` to distinguish main from resume. Reviewers recommended passing `on_token_written_factory: _CheckpointFactory | None` instead — matching the existing `_write_pending_to_sinks()` signature. The checkpoint factory is constructed at the `_execute_run()` level (10 lines, captures `processor` cleanly) and passed as `None` for resume. This documents intent without a boolean flag.

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
        # 3. Source + Process phase (inside track_operation for source)
        interrupted = self._run_main_processing_loop(
            loop_ctx, recorder, run_id, artifacts.source_id, artifacts.edge_map,
            shutdown_event=shutdown_event,
        )

        # 4. Flush + write sinks (outside source track_operation)
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
    return counters.to_run_result(run_id, status=RunStatus.COMPLETED)
```

### `_process_resumed_rows()` becomes ~60 lines

```python
def _process_resumed_rows(self, recorder, run_id, config, graph, unprocessed_rows,
                          restored_aggregation_state, settings, *, payload_store,
                          schema_contract, shutdown_event):
    self._current_graph = graph

    # 1. Setup (loads graph artifacts from original run's DB records)
    artifacts = self._setup_resume_context(recorder, run_id, config, graph)

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
        # 3. Process loop (resume path — no progress emission, see known gap)
        interrupted = self._run_resume_processing_loop(
            loop_ctx, shutdown_event=shutdown_event,
        )

        # 4. Flush + write sinks (no checkpointing during resume)
        self._flush_and_write_sinks(
            recorder, run_id, loop_ctx, artifacts.sink_id_map,
            interrupted, on_token_written_factory=None,
        )
    finally:
        self._cleanup_plugins(config, run_ctx.ctx, include_source=False)

    self._current_graph = None
    return counters.to_run_result(run_id, status=RunStatus.COMPLETED)
```

**Divergence accounting:** Before committing the collapse (commit #10), add a block comment to `_process_resumed_rows()` enumerating every behavioral divergence from `_execute_run()`. The known divergences are:

| Concern | `_execute_run()` | `_process_resumed_rows()` |
|---------|-------------------|---------------------------|
| Source `on_start()` | Called | Skipped (`include_source_on_start=False`) |
| Graph registration | Registers new nodes/edges | Loads from DB (`_setup_resume_context`) |
| Quarantine routing | Full handling via `_handle_quarantine_row()` | Not applicable (rows already validated) |
| Field resolution | Recorded on first valid row | Skipped (loaded from DB) |
| Schema contract recording | Recorded on first valid row | Skipped (passed via parameter) |
| `operation_id` lifecycle | Set/clear/restore per iteration | Not applicable |
| Progress emission | Every N rows | None (known gap) |
| Checkpointing | `on_token_written_factory` creates callbacks | `None` (no checkpointing during resume) |

This converts the implicit divergence into explicit, visible state — preventing future drift between the paths (R2 reinforcing loop from systems analysis).

---

## Part 2: processor.py

### New types (private to `processor.py`)

```python
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class _TransformContinue:
    """Token should advance to the next node in the DAG."""
    updated_token: TokenInfo
    updated_sink: str

@dataclass(frozen=True, slots=True)
class _TransformTerminal:
    """Token has reached a terminal state (completed, failed, quarantined, etc.)."""
    result: RowResult | list[RowResult]

_TransformOutcome: TypeAlias = _TransformContinue | _TransformTerminal


@dataclass(frozen=True, slots=True)
class _GateContinue:
    """Gate says advance to next node (or jump to a specific node).

    Matches GateOutcome.next_node_id vocabulary from executors/types.py.
    """
    updated_sink: str
    next_node_id: NodeID | None = None  # None = next structural node

@dataclass(frozen=True, slots=True)
class _GateTerminal:
    """Gate has routed, forked, or diverted the token to a terminal state."""
    result: RowResult | list[RowResult]

_GateOutcome: TypeAlias = _GateContinue | _GateTerminal
```

**Design rationale (from review):** The original design used `tuple[RowResult | list[RowResult] | None, TokenInfo, str]` where `None` meant "continue to next node." This conflates "no result yet" with absence of a value, and the caller must check `if result is not None` after every call while also unpacking two mutable out-parameters. Frozen dataclasses make the semantics explicit to mypy and readers. Precedent: `_FlushContext` in `processor.py` already uses this pattern.

The gate outcome type mirrors the transform pattern for consistency. The original design used `RowResult | list[RowResult] | None` with a `None` sentinel for gates, but this created two problems: (1) asymmetry with the transform discriminated union in the same 60-line method, and (2) the gate "jump to specific node" case (where `outcome.next_node_id` overrides the structural next node) cannot be represented by returning `None` — the caller needs the jump target. `_GateContinue.next_node_id` captures this cleanly.

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
    current_on_success_sink: str,
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
    current_on_success_sink: str,
) -> _GateOutcome:
```

Handles:
- Gate evaluation via GateExecutor
- FORK_TO_PATHS (create child tokens, queue work items) → `_GateTerminal`
- ROUTE_TO_SINK (route to named sink) → `_GateTerminal`
- DIVERT_TO_ERROR → `_GateTerminal`
- CONTINUE (advance to next node) → `_GateContinue(next_node_id=None)`
- Explicit next_node_id jump → `_GateContinue(next_node_id=node_id)`
- Error handling and coalesce notification

Returns `_GateTerminal` for fork/route/divert outcomes. Returns `_GateContinue` for continue/jump outcomes, with `next_node_id` set when the gate specifies an explicit next node (overriding structural DAG order).

#### 3. `_handle_terminal_token()`

**Size:** ~50 lines

```python
def _handle_terminal_token(
    self,
    current_token: TokenInfo,
    current_on_success_sink: str,
) -> RowResult | list[RowResult]:
```

Handles:
- Branch-to-sink routing (for fork branches that route directly to sinks)
- COMPLETED outcome with on_success sink resolution
- ROUTED outcome for named sink routing

Returns only the result — the caller wraps it with the already-constructed `child_items`: `return result, child_items`. This keeps the method's contract honest: it computes a result, it does not manage work items. (All fork children are created earlier in the loop by `_handle_gate_node()`.)

### After extraction: `_process_single_token()` becomes ~65 lines

```python
def _process_single_token(self, token, ctx, current_node_id, ...):
    current_token = token
    child_items = []
    current_on_success_sink = on_success_sink or self._source_on_success

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
                coalesce_node_id, coalesce_name, current_on_success_sink,
            )
            if isinstance(outcome, _TransformTerminal):
                return outcome.result, child_items
            current_token = outcome.updated_token
            current_on_success_sink = outcome.updated_sink

        elif isinstance(plugin, GateSettings):
            gate_outcome = self._handle_gate_node(
                plugin, current_token, ctx, node_id, child_items,
                coalesce_node_id, coalesce_name, current_on_success_sink,
            )
            if isinstance(gate_outcome, _GateTerminal):
                return gate_outcome.result, child_items
            current_on_success_sink = gate_outcome.updated_sink
            if gate_outcome.next_node_id is not None:
                node_id = gate_outcome.next_node_id
                continue

        node_id = next_node_id

    result = self._handle_terminal_token(current_token, current_on_success_sink)
    return result, child_items
```

---

## Implementation Strategy

### Pre-implementation: Characterization tests (commit 0)

Before any extraction, add a characterization test that exercises the full `_execute_run()` path with a pipeline containing:
- At least one quarantined row (source validation failure) **as the first row** (exercises field resolution ordering — field resolution must be recorded from the first *valid* row, not skipped entirely)
- At least one successfully transformed row
- Aggregation with a count trigger
- A gate that forks to multiple paths

The test must assert:
- **Per-scenario counter assertions:** Assert specific counter values for the characterization pipeline rather than a single conservation equation. The naive identity `rows_processed == rows_quarantined + rows_succeeded + rows_failed + rows_routed` is **wrong for fork paths** — a source row that forks to 2 paths produces `rows_forked=1` and 2 child tokens that each increment `rows_succeeded`, breaking the identity. Instead, assert the exact expected counters for the specific pipeline configuration (e.g., "2 quarantined, 3 succeeded, 1 forked, 0 failed").
- `sink.results` contents for each sink
- Audit record counts in `nodes`, `node_states`, `routing_events` tables
- **`operation_id` attribution via spy:** Use `unittest.mock.patch.object` (not bare attribute assignment) to wrap the transform's `process()` method and capture `ctx.operation_id` at call time, then assert all captured values are `None`. `patch.object` is robust against the caller storing a reference before the spy is installed.

```python
# operation_id spy pattern for characterization test
from unittest.mock import patch

captured_operation_ids = []
original_process = transform.process

def spy_process(row, ctx):
    captured_operation_ids.append(ctx.operation_id)
    return original_process(row, ctx)

with patch.object(transform, "process", side_effect=spy_process):
    # ... run pipeline ...
    pass

assert all(op_id is None for op_id in captured_operation_ids), (
    f"operation_id leaked into transform execution: {captured_operation_ids}"
)
```

- **Audit attribution in Landscape:** After the run completes, query the Landscape `calls` table and assert: (1) the `source_load` operation has no calls from sink nodes; (2) sink write calls have `operation_id = None` (they execute outside the source `track_operation` context). This catches extraction errors that break the `track_operation` boundary — the highest-risk boundary in commit #8.
- **Field resolution after quarantine:** Assert that `field_resolution_recorded` is `True` even when the first source row is quarantined (field resolution must come from the first *valid* row)
- **Aggregation timeout ordering:** Verify the row that triggers a timeout flush does NOT appear in the flushed batch (regression oracle for BUG FIX P1-2026-01-22). Confirm the test uses the `Clock` abstraction for deterministic timeout triggering — do NOT use `time.sleep()`.

This test becomes the regression oracle for the entire extraction sequence.

Additionally, add targeted tests for review-identified gaps:
- **`on_start()` not called for source during resume:** Create a source with a call tracker on `on_start()`. Run resume. Assert call count is 0 for the source and 1 for each transform/sink.
- **No checkpoint created during resume:** Run resume path, assert `checkpoint_manager.get_latest_checkpoint(run_id)` returns the pre-resume checkpoint (not a new one from `on_token_written_factory=None`)
- **No field resolution recorded during resume:** After resume completes, query the Landscape and assert no `field_resolution_recorded` event was emitted during the resume portion of the run (field resolution was already recorded in the original run).
- **No schema contract recorded during resume:** After resume completes, assert no duplicate schema contract records exist (the schema contract is passed via parameter, not re-recorded).
- **`_current_graph` lifecycle under error:** Force an error inside an extracted method, verify `self._current_graph is None` after the exception propagates through the `finally` block. This prevents stale graph references from affecting subsequent checkpointing calls.

Confirm existing coverage for:
- `test_quarantine_routing.py` — counter arithmetic for quarantine
- `test_orchestrator_checkpointing.py` — checkpoint records during resume
- `test_graceful_shutdown.py` — shutdown branch in the processing loop
- `test_resume_guardrails.py` — flag inversion protection for resume path

### Commit sequence (each independently testable)

0. **Add characterization tests** — regression oracle for extraction sequence
1. **Define types in `engine/orchestrator/types.py`** — `GraphArtifacts` (with `MappingProxyType`), `AggNodeEntry`, `RunContext` (with `MappingProxyType`), `LoopContext` (not frozen, mutable/immutable field groups), `_CheckpointFactory` TypeAlias (concrete inner type `Callable[[TokenInfo], None]`). Also fix `ExecutionCounters.to_run_result()` to require `status` parameter (preflight: update all call sites in `src/` and `tests/` — see preflight section above). Also update `aggregation.py` to use `AggNodeEntry` attribute access instead of tuple destructuring (line 224: `agg_transform, _agg_node_id = ...` → `entry = ...; agg_transform = entry.transform`).
2. **Define outcome types in `processor.py`** — `_TransformContinue`, `_TransformTerminal`, `_TransformOutcome` TypeAlias, `_GateContinue`, `_GateTerminal`, `_GateOutcome` TypeAlias (all private to module)
3. **Extract `_register_graph_nodes_and_edges()`** — pure move, returns `GraphArtifacts`
4. **Extract `_initialize_run_context()`** — pure move, takes `GraphArtifacts`, returns `RunContext`
5. **Extract `_setup_resume_context()`** — pure move from resume path (~50 lines), returns `GraphArtifacts`
6. **Extract `_handle_quarantine_row()`** — extract quarantine block from main loop
7. **Extract `_flush_and_write_sinks()`** — pure move, takes `LoopContext` + `_CheckpointFactory | None`
8. **Extract `_run_main_processing_loop()`** — main path processing with quarantine + field resolution
9. **Extract `_run_resume_processing_loop()`** — resume path processing (simpler)
10. **Collapse `_execute_run()` and `_process_resumed_rows()`** — use extracted methods, add divergence accounting comment block to resume path
11. **Extract `_handle_transform_node()`** — pure move, returns `_TransformOutcome`
12. **Extract `_handle_gate_node()`** — pure move, returns `_GateOutcome`
13. **Extract `_handle_terminal_token()`** — pure move from `_process_single_token()`
14. **Collapse `_process_single_token()`** — use extracted methods

### Risk ranking by commit

| Rank | Commit | Risk | Reason |
|------|--------|------|--------|
| 1 | **#8: `_run_main_processing_loop()`** | Highest | `operation_id` lifecycle lacks direct test coverage; quarantine interaction; `track_operation` boundary |
| 2 | **#10: Collapse main+resume** | High | Flag inversion risk (`include_source_on_start`, `on_token_written_factory`); divergence accounting must be correct |
| 3 | **#6: `_handle_quarantine_row()`** | Medium-high | Quarantine counter correctness, schema contract recording, field resolution ordering |
| 4 | **#12: `_handle_gate_node()`** | Medium-high | Multiple branches (fork/route/continue/jump/error); `next_node_id` semantics; fork path token multiplication |
| 5 | **#1-5, 7, 9, 11, 13-14** | Lower | Pure moves or type definitions, well-exercised by existing tests |

### Risk mitigation

- **One extraction per commit.** Run full test suite after each.
- **No behavior changes.** Only move code. If a test fails, it's a move error, not a logic bug.
- **Verify with `git diff --stat`.** Each commit should show lines moved between methods, not net new lines.
- **Integration tests exercise real code paths.** Per CLAUDE.md: "Never bypass production code paths in tests."
- **Focused test runs after each commit:** `pytest tests/unit/engine/test_processor.py tests/integration/pipeline/orchestrator/ tests/property/engine/ -x --tb=short` for fast feedback. For high-risk commits (#6, #8, #10), also include `tests/integration/pipeline/` (the parent directory covers fork/join tests that depend on both orchestrator and processor). Full suite run for the final commit and after high-risk commits.
- **Side-by-side diff of resume path** required before committing #10 (collapse) — verify flag values match intent and divergence accounting is complete.
- **`track_operation` boundary verification** for commit #8: confirm that the extraction boundary between `_run_main_processing_loop()` and `_flush_and_write_sinks()` coincides with the `track_operation(source_load)` context boundary. Aggregation flushing and sink writes must remain outside the source operation context.

### Verification criteria

- All tests pass after each commit (8,000+ tests)
- mypy clean
- ruff clean
- No method exceeds 150 lines in the final state
- `_execute_run()` is ~90 lines of orchestration
- `_process_single_token()` is ~65 lines of flow control
- `_process_resumed_rows()` shares `LoopContext` and `_flush_and_write_sinks()` with main path
- Characterization test (commit 0) passes after every subsequent commit
- `operation_id` spy captures only `None` values throughout the extraction sequence

### Expected line counts (post-refactor)

| File | Before | After | Delta |
|------|--------|-------|-------|
| `orchestrator/core.py` | 2,365 | ~2,270 | -95 (duplication removed, types/resume-setup moved out) |
| `orchestrator/types.py` | ~100 | ~200 | +100 (new dataclasses, TypeAlias, AggNodeEntry) |
| `processor.py` | 1,874 | ~1,910 | +36 (outcome dataclasses + gate outcome types) |

**Note:** This refactoring doesn't reduce total line count significantly. The value is in making each method independently readable and testable, eliminating the main/resume duplication, and introducing type-safe return values.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Extract Method vs Phase Objects vs Module Functions | Extract Method | Keeps `self` access free, minimal abstraction cost, lowest risk |
| Immutable return types | Frozen dataclasses with `MappingProxyType` (`GraphArtifacts`, `RunContext`) | Deep immutability matching `DAGTraversalContext` precedent; named fields eliminate positional-swap hazards |
| Aggregation lookup values | `AggNodeEntry` frozen dataclass | Replaces `tuple[TransformProtocol, NodeID]`; same anti-pattern `GraphArtifacts` was designed to fix |
| Parameter bundling | `LoopContext` mutable dataclass (`slots=True`, NOT `frozen=True`) | Contains `counters` and `pending_tokens` which are mutated in place; `frozen=True` would create a semantic lie |
| Main/resume loop unification | Two typed loop methods with shared helpers | Preserves full mypy coverage; 20 lines of shared bookkeeping is below duplication threshold |
| Source iteration | Regular method `_handle_quarantine_row()` (not generator) | Avoids `GeneratorExit` hazard, hidden mutation, untestable quarantine path |
| Transform node return type | `_TransformOutcome` discriminated union | Replaces `None` sentinel + 3-tuple; explicit semantics for continue vs terminal |
| Gate node return type | `_GateOutcome` discriminated union | Symmetric with transform pattern; `_GateContinue.next_node_id` captures explicit next-node override that `None` sentinel cannot represent |
| Checkpointing control | `on_token_written_factory: _CheckpointFactory \| None` | Named TypeAlias documents intent; matches existing `_write_pending_to_sinks()` signature; eliminates boolean flag |
| `to_run_result()` status parameter | Required (no default) | Previous `RunStatus.RUNNING` default silently produces incorrect audit records if any call site omits the argument |
| Method vs standalone function for extractions | Private methods on same class | Extracted code needs `self._events`, `self._telemetry`, `self._checkpoint_*` etc. |
| Parameter naming | `current_on_success_sink` (not `last_on_success_sink`) | `current_` describes the parameter's role at the method boundary; `last_` implies loop iteration context |
| Resume graph setup | Separate `_setup_resume_context()` method | Loads `GraphArtifacts` from DB instead of registering new ones; parallel to `_register_graph_nodes_and_edges()` |
| New files? | No (types added to existing `types.py`) | Methods stay on their existing classes. No new modules. |

## Strategic Follow-Up

The main/resume duplication is a "Shifting the Burden" archetype (systems thinking review) with an active Reinforcing loop (R2: Duplication Drift) underneath. T18 eliminates the duplicated code and adds a divergence accounting table, but preserves two separate entry points (`_execute_run` and `_process_resumed_rows`). The fundamental solution is a `RowSource` protocol that makes resume a mode rather than a separate code path.

**After T18 completes, create a follow-up task:**

> T24: Introduce `RowSource` protocol to unify main/resume execution
>
> Make `_execute_run()` the only execution path, parameterized by a `RowSource`
> that abstracts both live sources (CSV, API) and resume payloads (stored rows).
> This eliminates the architectural divergence between main and resume at the
> information-flow level, preventing future drift.

**Scope warning (from systems analysis):** T24 is a **Level 10 (Structure) intervention**, not just Level 6 (Information Flows). The `RowSource` protocol must carry at least 5 behavioral variants between main and resume:

1. Row-level iteration (live source iterator vs stored row payloads)
2. Quarantine routing (source-side validation vs no-op for resume)
3. Field resolution recording (first-row vs skip for resume)
4. Schema contract recording (first-row vs loaded-from-DB for resume)
5. `operation_id` lifecycle (set/clear/restore vs N/A for resume)

Underspecifying this protocol will reproduce the divergence pattern at the protocol level. Scope T24 with the same rigor as a structural refactor — do not combine it with other RC3.3 work.
