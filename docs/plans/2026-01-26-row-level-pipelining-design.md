# Row-Level Pipelining Design

**Date:** 2026-01-26
**Status:** Proposed
**Supersedes:** ADR-001 (Plugin-Level Concurrency)
**Author:** Architecture Team

---

## Executive Summary

This document describes the design for row-level pipelining in ELSPETH, a feature that allows multiple source rows to be processed simultaneously while maintaining strict FIFO ordering for sink writes. This supersedes ADR-001's sequential processing model to achieve significantly higher throughput for LLM-heavy pipelines.

### Key Decisions

| Aspect | Decision |
|--------|----------|
| **Architecture** | Three-stage pipeline: SourcePuller → WorkPool → ReleaseQueue |
| **FIFO Enforcement** | ReleaseQueue with sequence numbers, blocks until predecessors release |
| **DAG Support** | Full support from day one — fork groups synchronize, coalesce waits for branches |
| **Pool Strategy** | Shared `PooledExecutor` across all in-flight rows |
| **Audit Integrity** | Record outcome BEFORE sink write, thread-safe recorder |
| **Checkpointing** | Captures `released_through_seq` + in-flight state for crash recovery |
| **Defaults** | `enabled: false`, `max_rows_in_flight: 1` (safe defaults preserve sequential behavior) |

### Expected Outcomes

- **10x+ throughput** for LLM-heavy pipelines (30 pool slots utilized across rows vs. 10 per row)
- **Strict FIFO ordering** preserved — outputs identical to sequential execution
- **Complete audit trail** — every token reaches exactly one terminal state
- **Graceful degradation** — `max_rows_in_flight=1` equals current sequential behavior

---

## 1. Problem Statement

### 1.1 Current Architecture (ADR-001)

ADR-001 established that the orchestrator processes rows **sequentially**:

```
for row in source:
    results = processor.process_row(row)  # Full DAG execution
    for result in results:
        pending_tokens[sink].append(result)
# After ALL rows processed:
for sink, tokens in pending_tokens.items():
    sink.write(tokens)
```

**Rationale at the time:**
- Simple audit trail — no race conditions in `node_states` recording
- Deterministic ordering — output matches source order trivially
- Simpler checkpoint/recovery — "row N complete" is unambiguous

### 1.2 The Performance Problem

With LLM transforms, each row may issue 10+ API calls. The `PooledExecutor` has `pool_size=30` capacity, but only ~10 slots are used per row. Between rows, the pool is idle:

```
Row 1: [====== 10 queries ======]................
Row 2:                           [====== 10 queries ======]................
Row 3:                                                      [====== 10 queries ======]

Pool utilization: ~33% (10/30 slots used at any time)
```

With row-level pipelining:

```
Row 1: [====== 10 queries ======]
Row 2:    [====== 10 queries ======]
Row 3:       [====== 10 queries ======]

Pool utilization: ~100% (30/30 slots used)
```

### 1.3 Requirements

Based on the task specification (`docs/tasks/row-level-pipelining.md`) and stakeholder input:

| ID | Requirement | Priority |
|----|-------------|----------|
| R1 | Multiple rows in flight simultaneously | Must |
| R2 | Strict FIFO ordering to sinks (source order) | Must |
| R3 | Complete audit trail for every token | Must |
| R4 | Memory bounded (backpressure) | Must |
| R5 | Full DAG support (fork/join/aggregation) | Must |
| R6 | Shared query pool across rows | Must |
| R7 | Crash recovery with no duplicate sink writes | Must |
| R8 | Safe defaults (sequential behavior without config) | Should |

---

## 2. Architecture Overview

### 2.1 High-Level Architecture

The new orchestrator replaces the sequential loop with a three-stage pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PIPELINED ORCHESTRATOR                             │
│                                                                              │
│  ┌───────────────┐     ┌─────────────────────┐     ┌───────────────────┐   │
│  │ SOURCE PULLER │────▶│    WORK POOL        │────▶│  RELEASE QUEUE    │   │
│  │               │     │                     │     │                   │   │
│  │ • Pull rows   │     │ • Process tokens    │     │ • FIFO ordering   │   │
│  │ • Assign seq# │     │ • Execute DAG       │     │ • Fork/join sync  │   │
│  │ • Backpressure│     │ • Shared pool       │     │ • Sink dispatch   │   │
│  └───────────────┘     └─────────────────────┘     └───────────────────┘   │
│         ▲                                                    │              │
│         │                                                    │              │
│         └────────────── BACKPRESSURE SIGNAL ─────────────────┘              │
│                                                                              │
│  Configuration:                                                              │
│    max_rows_in_flight: 10        # Max source rows being processed          │
│    max_completed_waiting: 20     # Max completed rows waiting for release   │
│    pool_size: 30                 # Shared query pool capacity               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Responsibilities

| Component | Responsibility | Thread Model |
|-----------|----------------|--------------|
| **SourcePuller** | Pulls rows from source iterator, assigns sequence numbers, respects backpressure | Single thread (producer) |
| **WorkPool** | Processes tokens through DAG, executes transforms, handles fork/join creation | Thread pool (N workers) |
| **ReleaseQueue** | Enforces FIFO ordering, tracks fork/join completion, dispatches to sinks | Single thread (consumer) |

### 2.3 Key Data Structures

```python
@dataclass(frozen=True)
class InflightRow:
    """A row being processed through the pipeline."""
    sequence_number: int           # Monotonic, assigned by SourcePuller
    row_id: str                    # Stable identity from source
    root_token_id: str             # Initial token for this row


@dataclass
class CompletedToken:
    """A token that has finished processing, waiting for release."""
    sequence_number: int           # Inherited from InflightRow
    token_id: str
    row_id: str
    outcome: RowOutcome            # COMPLETED, ROUTED, FORKED, etc.
    sink_name: str | None          # Destination sink (if COMPLETED/ROUTED)
    row_data: dict[str, Any]       # Final row data for sink
    fork_group_id: str | None      # Links fork children
    coalesce_group_id: str | None  # Links coalesce inputs
```

### 2.4 Sequence Number Semantics

Source order is the contract for FIFO. We assign a monotonic `sequence_number` at source pull time. This number propagates through forks (children inherit parent's sequence) and is used by the release queue to enforce ordering.

```
Source Row 1 (seq=1) ──┬── Token T1 (seq=1) ──► COMPLETED (seq=1)
                       │
                       └── Fork ──┬── Token T2 (seq=1, branch=A)
                                  └── Token T3 (seq=1, branch=B)

Source Row 2 (seq=2) ──── Token T4 (seq=2) ──► COMPLETED (seq=2)
```

**Ordering rule:** A token with `seq=N` cannot be released to a sink until ALL tokens with `seq < N` have been released (or marked terminal with non-sink outcomes like FORKED, CONSUMED_IN_BATCH).

---

## 3. Source Puller & Backpressure

### 3.1 SourcePuller Component

```python
class SourcePuller:
    """Pulls rows from source with backpressure awareness.

    Runs in its own thread, feeding rows into the work pool.
    Stops pulling when max_rows_in_flight is reached.
    """

    def __init__(
        self,
        source: SourceProtocol,
        work_pool: WorkPool,
        release_queue: ReleaseQueue,
        config: PipeliningConfig,
    ):
        self._source = source
        self._work_pool = work_pool
        self._release_queue = release_queue
        self._config = config

        self._sequence_counter = 0
        self._rows_in_flight = 0
        self._backpressure_condition = threading.Condition()

    def run(self, ctx: PluginContext) -> None:
        """Main loop: pull rows until source exhausted or error."""
        for row_index, row_data in enumerate(self._source.load(ctx)):
            # Wait if at capacity
            with self._backpressure_condition:
                while self._rows_in_flight >= self._config.max_rows_in_flight:
                    self._backpressure_condition.wait()

            # Assign sequence number and dispatch
            self._sequence_counter += 1
            inflight = InflightRow(
                sequence_number=self._sequence_counter,
                row_id=self._generate_row_id(row_index, row_data),
                root_token_id=str(uuid.uuid4()),
            )

            self._rows_in_flight += 1
            self._work_pool.submit(inflight, row_data, ctx)

        # Signal end of source
        self._work_pool.signal_source_exhausted()

    def on_row_released(self) -> None:
        """Called by ReleaseQueue when a row is fully released."""
        with self._backpressure_condition:
            self._rows_in_flight -= 1
            self._backpressure_condition.notify()
```

### 3.2 Backpressure Mechanism

Backpressure flows from the ReleaseQueue back to the SourcePuller through two signals:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        BACKPRESSURE FLOW                                 │
│                                                                          │
│  SourcePuller                WorkPool              ReleaseQueue          │
│       │                         │                       │                │
│       │  submit(row)            │                       │                │
│       │────────────────────────▶│                       │                │
│       │                         │  completed(token)     │                │
│       │                         │──────────────────────▶│                │
│       │                         │                       │                │
│       │                         │                       │ (FIFO check)   │
│       │                         │                       │                │
│       │◀─────────────────────────────────────────────────│               │
│       │  on_row_released()      │                       │ release(token) │
│       │                         │                       │───────▶ SINK   │
│                                                                          │
│  Backpressure triggers when:                                             │
│    1. rows_in_flight >= max_rows_in_flight                              │
│    2. completed_waiting >= max_completed_waiting (optional)             │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Backpressure Scenarios

| Scenario | Trigger | Effect |
|----------|---------|--------|
| **Normal flow** | `rows_in_flight < max` | SourcePuller pulls next row immediately |
| **Processing backlog** | `rows_in_flight >= max` | SourcePuller blocks until a row is released |
| **Slow predecessor** | Row N takes 60s, rows N+1 to N+9 complete | Completed rows wait in ReleaseQueue; no new pulls until row N releases |
| **Sink bottleneck** | Sink write is slow | ReleaseQueue blocks on sink; backpressure propagates |

**Why two-level backpressure:** The `max_rows_in_flight` bounds total work in the system. The optional `max_completed_waiting` bounds memory for completed-but-waiting rows. If row 1 is slow and rows 2-100 complete, you don't want unbounded memory growth. The second limit provides defense-in-depth.

---

## 4. Work Pool & DAG Execution

### 4.1 WorkPool Component

```python
class WorkPool:
    """Processes tokens through the execution DAG.

    Uses a thread pool for row-level parallelism and shares
    the PooledExecutor for query-level parallelism within transforms.
    """

    def __init__(
        self,
        graph: ExecutionGraph,
        processor: RowProcessor,
        release_queue: ReleaseQueue,
        pooled_executor: PooledExecutor,  # Shared across all rows
        config: PipeliningConfig,
    ):
        self._graph = graph
        self._processor = processor
        self._release_queue = release_queue
        self._pooled_executor = pooled_executor

        # Thread pool for row-level parallelism
        self._executor = ThreadPoolExecutor(
            max_workers=config.max_rows_in_flight,
            thread_name_prefix="row-worker",
        )
        self._pending_futures: dict[int, Future] = {}  # seq -> future
        self._source_exhausted = threading.Event()

    def submit(self, inflight: InflightRow, row_data: dict, ctx: PluginContext) -> None:
        """Submit a row for processing."""
        future = self._executor.submit(
            self._process_row,
            inflight,
            row_data,
            ctx,
        )
        self._pending_futures[inflight.sequence_number] = future

    def _process_row(
        self,
        inflight: InflightRow,
        row_data: dict,
        ctx: PluginContext,
    ) -> None:
        """Process a single row through the DAG (runs in worker thread)."""
        try:
            # Reuse existing RowProcessor - it's already stateless
            results: list[RowResult] = self._processor.process_row(
                row_index=inflight.sequence_number - 1,  # 0-indexed
                row_data=row_data,
                row_id=inflight.row_id,
                root_token_id=inflight.root_token_id,
                ctx=ctx,
            )

            # Submit all terminal outcomes to release queue
            for result in results:
                completed = CompletedToken(
                    sequence_number=inflight.sequence_number,
                    token_id=result.token_id,
                    row_id=inflight.row_id,
                    outcome=result.outcome,
                    sink_name=result.sink_name,
                    row_data=result.row_data,
                    fork_group_id=result.fork_group_id,
                    coalesce_group_id=result.coalesce_group_id,
                )
                self._release_queue.submit_completed(completed)

        except Exception as e:
            # Unhandled exception - submit as FAILED
            self._release_queue.submit_failed(inflight, e)
```

### 4.2 Relationship to Existing RowProcessor

**Key design decision:** The existing `RowProcessor` is already stateless and processes one row through the entire DAG. We DON'T modify it. Instead, we wrap it with the WorkPool which handles parallelism. This minimizes changes to the auditing logic.

The RowProcessor continues to:
- Create tokens and record to Landscape
- Execute transforms with retry logic
- Handle fork/join/aggregation within a single row's context
- Return `list[RowResult]` with all terminal outcomes

**What changes:** The RowProcessor is now called from multiple threads concurrently, but each invocation is independent.

### 4.3 Shared PooledExecutor

The `PooledExecutor` (existing component) is shared across all in-flight rows:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SHARED POOLED EXECUTOR                               │
│                                                                          │
│  Row 1 (worker thread 1)                                                 │
│    └── Transform A ──┬── Query 1 ──────────┐                            │
│                      └── Query 2 ──────────┤                            │
│                                            │                            │
│  Row 2 (worker thread 2)                   │    ┌──────────────────┐   │
│    └── Transform A ──┬── Query 3 ──────────┼───▶│  SEMAPHORE       │   │
│                      └── Query 4 ──────────┤    │  (pool_size=30)  │   │
│                                            │    └──────────────────┘   │
│  Row 3 (worker thread 3)                   │             │              │
│    └── Transform A ──┬── Query 5 ──────────┤             ▼              │
│                      └── Query 6 ──────────┘    ┌──────────────────┐   │
│                                                 │  EXTERNAL CALLS  │   │
│                                                 │  (LLM, HTTP...)  │   │
│                                                 └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Thread safety:** The existing `PooledExecutor` uses a semaphore for capacity control and is thread-safe. No modifications needed.

### 4.4 DAG Execution with Forks

When a gate forks, the RowProcessor creates child tokens and returns multiple results:

```python
# RowProcessor.process_row() returns multiple results for forks:
results = [
    RowResult(token_id="parent", outcome=FORKED, fork_group_id="fg-1"),
    RowResult(token_id="child-A", outcome=COMPLETED, sink_name="output", ...),
    RowResult(token_id="child-B", outcome=ROUTED, sink_name="archive", ...),
]
```

All results inherit the same `sequence_number` from the parent row. The ReleaseQueue handles the ordering.

### 4.5 DAG Execution with Aggregations

Aggregations are **stateful** — they accumulate rows until a trigger fires. This creates a synchronization point:

```
Row 1 ──► Aggregation (buffered)
Row 2 ──► Aggregation (buffered)
Row 3 ──► Aggregation (TRIGGER!) ──► Batch result
```

**Challenge:** With row-level pipelining, rows 1, 2, 3 may arrive at the aggregation out-of-order.

**Solution:** Aggregation buffers remain per-aggregation (not per-row). The aggregation's internal lock serializes access:

```python
class AggregationExecutor:
    """Thread-safe aggregation with ordered batch membership."""

    def __init__(self):
        self._lock = threading.Lock()
        self._buffer: list[tuple[int, TokenInfo, dict]] = []  # (seq, token, row)

    def accept(self, sequence_number: int, token: TokenInfo, row: dict) -> AcceptResult:
        with self._lock:
            # Insert in sequence order (maintain FIFO within batch)
            bisect.insort(self._buffer, (sequence_number, token, row))

            if self._should_trigger():
                return self._flush()
            return AcceptResult(buffered=True)
```

**Aggregation ordering:** Even though rows arrive out-of-order at the aggregation, we maintain sequence order within the batch. When the batch flushes, `batch_members` records the correct ordinal based on source sequence, not arrival time. This preserves audit determinism.

### 4.6 End-of-Source Handling

When the source is exhausted:

1. **SourcePuller** signals `source_exhausted` to WorkPool
2. **WorkPool** waits for all pending futures to complete
3. **WorkPool** signals `processing_complete` to ReleaseQueue
4. **Aggregations** flush any remaining buffers (existing behavior)
5. **ReleaseQueue** releases all remaining tokens in FIFO order

```python
def signal_source_exhausted(self) -> None:
    """Called when source iterator is exhausted."""
    self._source_exhausted.set()

    # Wait for all in-flight work to complete
    for seq, future in sorted(self._pending_futures.items()):
        future.result()  # Block until complete

    # Flush remaining aggregations
    self._flush_aggregations()

    # Signal release queue
    self._release_queue.signal_processing_complete()
```

---

## 5. Release Queue & FIFO Enforcement

### 5.1 ReleaseQueue Component

The ReleaseQueue is the heart of the FIFO guarantee. It holds completed tokens until all predecessors have been released.

```python
class ReleaseQueue:
    """Enforces FIFO ordering for sink writes.

    Completed tokens wait here until all tokens with lower
    sequence numbers have been released. Handles fork/join
    synchronization and dispatches to sinks.
    """

    def __init__(
        self,
        sinks: dict[str, SinkProtocol],
        recorder: LandscapeRecorder,
        source_puller: SourcePuller,
        config: PipeliningConfig,
    ):
        self._sinks = sinks
        self._recorder = recorder
        self._source_puller = source_puller
        self._config = config

        # Core state (protected by lock)
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

        # Waiting tokens by sequence number
        self._waiting: dict[int, list[CompletedToken]] = defaultdict(list)

        # Next sequence number to release
        self._next_release_seq = 1

        # Track fork groups for synchronization
        self._fork_groups: dict[str, ForkGroupState] = {}

        # Track coalesce groups
        self._coalesce_groups: dict[str, CoalesceGroupState] = {}

        # Completion signal
        self._processing_complete = False
```

### 5.2 FIFO Release Algorithm

```python
def submit_completed(self, token: CompletedToken) -> None:
    """Submit a completed token for FIFO-ordered release."""
    with self._lock:
        self._waiting[token.sequence_number].append(token)

        # Track fork/coalesce groups
        if token.fork_group_id:
            self._track_fork_group(token)
        if token.coalesce_group_id:
            self._track_coalesce_group(token)

        # Try to release
        self._try_release()
        self._condition.notify_all()

def _try_release(self) -> None:
    """Release tokens in FIFO order. Called with lock held."""
    while self._can_release_next():
        tokens = self._waiting.pop(self._next_release_seq)

        for token in tokens:
            self._release_token(token)

        # Notify source puller that a row slot is free
        self._source_puller.on_row_released()

        self._next_release_seq += 1

def _can_release_next(self) -> bool:
    """Check if the next sequence can be released."""
    seq = self._next_release_seq

    if seq not in self._waiting:
        return False

    tokens = self._waiting[seq]

    # Check all tokens for this sequence are ready
    for token in tokens:
        if not self._token_ready_for_release(token):
            return False

    return True
```

### 5.3 Fork Group Synchronization

When a row forks, multiple child tokens share the same sequence number. The parent token (with outcome `FORKED`) and all children must be ready before any can release:

```python
@dataclass
class ForkGroupState:
    """Tracks completion state of a fork group."""
    fork_group_id: str
    sequence_number: int
    parent_token_id: str | None = None
    expected_children: set[str] = field(default_factory=set)
    arrived_children: set[str] = field(default_factory=set)
    parent_arrived: bool = False

def _track_fork_group(self, token: CompletedToken) -> None:
    """Track fork group membership."""
    fg_id = token.fork_group_id

    if fg_id not in self._fork_groups:
        self._fork_groups[fg_id] = ForkGroupState(
            fork_group_id=fg_id,
            sequence_number=token.sequence_number,
        )

    state = self._fork_groups[fg_id]

    if token.outcome == RowOutcome.FORKED:
        state.parent_arrived = True
        state.parent_token_id = token.token_id
    else:
        state.arrived_children.add(token.token_id)

def _fork_group_complete(self, fg_id: str) -> bool:
    """Check if all fork group members have arrived."""
    state = self._fork_groups.get(fg_id)
    if not state:
        return False

    # Parent must arrive with FORKED outcome
    if not state.parent_arrived:
        return False

    # All expected children must arrive
    # (expected_children is populated from parent's fork metadata)
    return state.arrived_children >= state.expected_children
```

**Fork release semantics:** A forked row is only "released" when the parent token (FORKED) AND all child tokens have completed. This ensures the audit trail is complete before any sink writes occur. The parent's FORKED outcome is recorded, then each child's outcome (COMPLETED/ROUTED) triggers its sink write.

### 5.4 Coalesce Group Synchronization

Coalesce (join) operations merge tokens from parallel branches. The coalesce must wait for all branches before releasing:

```python
@dataclass
class CoalesceGroupState:
    """Tracks completion state of a coalesce group."""
    coalesce_group_id: str
    sequence_number: int
    policy: CoalescePolicy  # require_all, quorum, best_effort, first
    expected_branches: set[str]
    arrived_branches: dict[str, CompletedToken] = field(default_factory=dict)
    timeout_at: float | None = None

def _coalesce_group_ready(self, cg_id: str) -> bool:
    """Check if coalesce group is ready based on policy."""
    state = self._coalesce_groups.get(cg_id)
    if not state:
        return False

    match state.policy:
        case CoalescePolicy.REQUIRE_ALL:
            return state.arrived_branches.keys() >= state.expected_branches

        case CoalescePolicy.QUORUM:
            return len(state.arrived_branches) >= state.quorum_count

        case CoalescePolicy.FIRST:
            return len(state.arrived_branches) >= 1

        case CoalescePolicy.BEST_EFFORT:
            if state.arrived_branches.keys() >= state.expected_branches:
                return True
            # Check timeout
            return time.time() >= state.timeout_at
```

### 5.5 Token Release and Sink Dispatch

```python
def _release_token(self, token: CompletedToken) -> None:
    """Release a token to its destination sink."""
    match token.outcome:
        case RowOutcome.COMPLETED | RowOutcome.ROUTED:
            # Write to sink
            sink = self._sinks[token.sink_name]
            artifact = sink.write(
                rows=[token.row_data],
                ctx=self._make_sink_context(token),
            )

            # Record artifact in Landscape
            self._recorder.record_artifact(
                token_id=token.token_id,
                sink_name=token.sink_name,
                artifact=artifact,
            )

            # Record terminal outcome
            self._recorder.record_token_outcome(
                token_id=token.token_id,
                outcome=token.outcome,
            )

        case RowOutcome.FORKED:
            # Parent token - just record outcome (children handle sink writes)
            self._recorder.record_token_outcome(
                token_id=token.token_id,
                outcome=RowOutcome.FORKED,
            )

        case RowOutcome.CONSUMED_IN_BATCH:
            # Aggregation consumed this token - record outcome only
            self._recorder.record_token_outcome(
                token_id=token.token_id,
                outcome=RowOutcome.CONSUMED_IN_BATCH,
            )

        case RowOutcome.COALESCED:
            # Token was merged - record outcome only
            self._recorder.record_token_outcome(
                token_id=token.token_id,
                outcome=RowOutcome.COALESCED,
            )

        case RowOutcome.QUARANTINED | RowOutcome.FAILED:
            # Error outcomes - record to Landscape
            self._recorder.record_token_outcome(
                token_id=token.token_id,
                outcome=token.outcome,
            )
```

### 5.6 Visualization of FIFO Release

```
TIME ──────────────────────────────────────────────────────────────────────▶

Source:     Row1(seq=1)    Row2(seq=2)    Row3(seq=3)    Row4(seq=4)
              │              │              │              │
              ▼              ▼              ▼              ▼
WorkPool:   [processing]  [processing]  [processing]  [processing]
              │              │              │              │
              │              ▼              ▼              │
              │           Complete      Complete          │
              │           (seq=2)       (seq=3)           │
              │              │              │              │
              │              ▼              ▼              │
ReleaseQ:   waiting      ┌─────────────────────┐       waiting
            for seq=1    │ WAITING (seq=2,3)   │       for seq=1
              │          │ Can't release yet!  │          │
              ▼          └─────────────────────┘          │
           Complete                                       │
           (seq=1)                                        │
              │                                           │
              ▼                                           │
           RELEASE seq=1 ──► SINK                        │
              │                                           │
              ▼                                           │
           RELEASE seq=2 ──► SINK                        │
              │                                           │
              ▼                                           │
           RELEASE seq=3 ──► SINK                        │
              │                                           ▼
              │                                        Complete
              │                                        (seq=4)
              ▼                                           │
           RELEASE seq=4 ──► SINK ◀───────────────────────┘
```

### 5.7 Memory Bounds

The `max_completed_waiting` configuration prevents unbounded memory growth:

```python
def submit_completed(self, token: CompletedToken) -> None:
    """Submit a completed token for FIFO-ordered release."""
    with self._lock:
        # Check memory bound
        total_waiting = sum(len(tokens) for tokens in self._waiting.values())

        while total_waiting >= self._config.max_completed_waiting:
            # Block until some tokens are released
            self._condition.wait()
            total_waiting = sum(len(tokens) for tokens in self._waiting.values())

        self._waiting[token.sequence_number].append(token)
        # ... rest of method
```

---

## 6. Audit Trail & Checkpointing

### 6.1 Audit Trail Integrity with Concurrent Processing

The Landscape audit trail must remain consistent even with concurrent row processing. Key invariants:

| Invariant | How It's Preserved |
|-----------|-------------------|
| Every token reaches exactly one terminal state | ReleaseQueue records outcome before sink write |
| `node_states` has unique (token_id, node_id, attempt) | RowProcessor uses token-scoped recording (unchanged) |
| Sink writes happen after audit recording | ReleaseQueue records outcome, THEN writes to sink |
| Source order is recoverable | `sequence_number` stored with row, FIFO release enforces order |

### 6.2 Landscape Schema Additions

```sql
-- Add sequence_number to rows table for FIFO recovery
ALTER TABLE rows ADD COLUMN sequence_number INTEGER;
CREATE UNIQUE INDEX idx_rows_run_seq ON rows(run_id, sequence_number);

-- Add pipelining metadata to runs table
ALTER TABLE runs ADD COLUMN pipelining_config_json TEXT;  -- Stores max_rows_in_flight, etc.
```

### 6.3 Recording Flow with Pipelining

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AUDIT RECORDING FLOW                                  │
│                                                                          │
│  SourcePuller                                                            │
│       │                                                                  │
│       │  1. Record row (with sequence_number)                           │
│       │     recorder.record_row(row_id, seq, data)                      │
│       ▼                                                                  │
│  WorkPool (concurrent)                                                   │
│       │                                                                  │
│       │  2. Record token creation                                        │
│       │     recorder.record_token(token_id, row_id)                     │
│       │                                                                  │
│       │  3. Record node_states (per transform)                          │
│       │     recorder.begin_transform(token_id, node_id)                 │
│       │     recorder.complete_transform(token_id, node_id, output)      │
│       │                                                                  │
│       │  4. Record routing events                                        │
│       │     recorder.record_routing_event(token_id, edge_id)            │
│       │                                                                  │
│       │  5. Record fork/coalesce                                         │
│       │     recorder.record_fork(parent_id, child_ids)                  │
│       │     recorder.record_coalesce(input_ids, output_id)              │
│       ▼                                                                  │
│  ReleaseQueue (FIFO ordered)                                             │
│       │                                                                  │
│       │  6. Record terminal outcome (BEFORE sink write)                 │
│       │     recorder.record_token_outcome(token_id, outcome)            │
│       │                                                                  │
│       │  7. Write to sink                                                │
│       │     sink.write(rows)                                            │
│       │                                                                  │
│       │  8. Record artifact (AFTER sink write)                          │
│       │     recorder.record_artifact(token_id, artifact)                │
│       ▼                                                                  │
│  Checkpoint (periodic)                                                   │
│       │                                                                  │
│       │  9. Record checkpoint with released_through_seq                 │
│       │     recorder.record_checkpoint(released_seq, pending_state)     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.4 Thread Safety in Recorder

The existing `LandscapeRecorder` uses database transactions for atomicity. With concurrent access, we need to ensure thread safety:

```python
class LandscapeRecorder:
    """Thread-safe audit trail recorder.

    Uses connection pooling and transaction isolation to handle
    concurrent recording from multiple worker threads.
    """

    def __init__(self, engine: Engine):
        self._engine = engine
        # Each thread gets its own connection from pool
        self._local = threading.local()

    def _get_connection(self) -> Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, 'connection'):
            self._local.connection = self._engine.connect()
        return self._local.connection

    def record_node_state(
        self,
        token_id: str,
        node_id: str,
        attempt: int,
        input_hash: str,
        output_hash: str | None,
        # ...
    ) -> str:
        """Record a node state. Thread-safe via connection pooling."""
        conn = self._get_connection()
        with conn.begin():  # Transaction isolation
            state_id = str(uuid.uuid4())
            conn.execute(
                node_states.insert().values(
                    state_id=state_id,
                    token_id=token_id,
                    node_id=node_id,
                    attempt=attempt,
                    # ...
                )
            )
            return state_id
```

**Why thread-local connections:** SQLite has limitations with concurrent writes (WAL mode helps but isn't perfect). PostgreSQL handles concurrent connections natively. By using thread-local connections with proper transaction isolation, we avoid contention while maintaining ACID guarantees. For SQLite in production, we recommend PostgreSQL for pipelined workloads.

### 6.5 Checkpoint Semantics with Pipelining

Checkpoints enable crash recovery. With pipelining, checkpoint semantics change:

**Old (Sequential):**
```
Checkpoint after row N = "rows 1..N fully processed and written to sink"
```

**New (Pipelined):**
```
Checkpoint with released_seq=N = "rows 1..N released to sinks"
                                + "rows N+1..M in flight (state preserved)"
```

```python
@dataclass
class PipelineCheckpoint:
    """Checkpoint state for crash recovery."""
    checkpoint_id: str
    run_id: str
    created_at: datetime

    # FIFO state
    released_through_seq: int      # All rows <= this seq have been released

    # In-flight state (for recovery)
    inflight_rows: list[InflightRowState]  # Rows being processed
    waiting_tokens: list[WaitingTokenState]  # Completed but not released

    # Aggregation state
    draft_batches: list[str]       # Batch IDs in draft state

    # Fork/coalesce state
    pending_fork_groups: list[str]
    pending_coalesce_groups: list[str]
```

### 6.6 Checkpoint Recording Strategy

```python
class CheckpointManager:
    """Manages checkpoints for pipelined execution."""

    def __init__(
        self,
        recorder: LandscapeRecorder,
        release_queue: ReleaseQueue,
        config: CheckpointSettings,
    ):
        self._recorder = recorder
        self._release_queue = release_queue
        self._config = config
        self._last_checkpoint_seq = 0

    def maybe_checkpoint(self) -> None:
        """Create checkpoint if conditions met."""
        current_released = self._release_queue.released_through_seq

        # Checkpoint every N released rows
        if current_released - self._last_checkpoint_seq >= self._config.frequency:
            self._create_checkpoint(current_released)
            self._last_checkpoint_seq = current_released

    def _create_checkpoint(self, released_seq: int) -> None:
        """Create a checkpoint capturing current pipeline state."""
        with self._release_queue.snapshot_lock():
            checkpoint = PipelineCheckpoint(
                checkpoint_id=str(uuid.uuid4()),
                run_id=self._recorder.run_id,
                created_at=datetime.utcnow(),
                released_through_seq=released_seq,
                inflight_rows=self._capture_inflight_state(),
                waiting_tokens=self._capture_waiting_state(),
                draft_batches=self._capture_aggregation_state(),
                pending_fork_groups=self._capture_fork_state(),
                pending_coalesce_groups=self._capture_coalesce_state(),
            )

        self._recorder.record_checkpoint(checkpoint)
```

### 6.7 Crash Recovery

On resume, we reconstruct the pipeline state from the last checkpoint:

```python
def resume_from_checkpoint(
    checkpoint: PipelineCheckpoint,
    source: SourceProtocol,
    ctx: PluginContext,
) -> PipelinedOrchestrator:
    """Resume execution from a checkpoint."""

    # 1. Skip already-released rows from source
    source_iter = source.load(ctx)
    for _ in range(checkpoint.released_through_seq):
        next(source_iter, None)  # Skip released rows

    # 2. Create orchestrator with remaining source
    orchestrator = PipelinedOrchestrator(
        source_iterator=source_iter,
        starting_sequence=checkpoint.released_through_seq + 1,
        # ...
    )

    # 3. Restore in-flight rows (re-process from source data)
    for inflight_state in checkpoint.inflight_rows:
        row_data = payload_store.get(inflight_state.source_data_ref)
        orchestrator.restore_inflight(inflight_state, row_data)

    # 4. Restore waiting tokens (already processed, just need release)
    for waiting_state in checkpoint.waiting_tokens:
        orchestrator.restore_waiting(waiting_state)

    # 5. Restore aggregation buffers
    for batch_id in checkpoint.draft_batches:
        orchestrator.restore_aggregation_batch(batch_id)

    return orchestrator
```

**Recovery trade-off:** In-flight rows at crash time are re-processed from source data (idempotent). Waiting tokens (already processed) skip directly to the release queue. This means some work is repeated on crash, but no work is lost and no duplicates appear in sinks (FIFO ordering + artifact idempotency keys).

---

## 7. Observability & Configuration

### 7.1 Metrics for Pipelined Execution

```python
@dataclass
class PipelineMetrics:
    """Real-time metrics for pipelined execution."""

    # Throughput
    rows_pulled: int = 0              # Total rows pulled from source
    rows_released: int = 0            # Total rows released to sinks
    tokens_completed: int = 0         # Total tokens completed (includes forks)

    # Pipeline depth
    rows_in_flight: int = 0           # Currently being processed
    tokens_waiting: int = 0           # Completed, waiting for FIFO release

    # Timing (rolling averages)
    avg_row_latency_ms: float = 0.0   # Source pull → sink release
    avg_processing_time_ms: float = 0.0  # WorkPool processing time
    avg_wait_time_ms: float = 0.0     # Time waiting in release queue

    # Pool utilization
    pool_slots_used: int = 0          # Current query pool usage
    pool_slots_total: int = 0         # Pool capacity
    pool_utilization_pct: float = 0.0

    # Backpressure indicators
    source_blocked_ms: int = 0        # Time source puller was blocked
    release_queue_blocked_ms: int = 0 # Time workers blocked on queue

    # Fork/join tracking
    active_fork_groups: int = 0
    active_coalesce_groups: int = 0

    # Error counts
    rows_failed: int = 0
    rows_quarantined: int = 0
```

### 7.2 OpenTelemetry Integration

```python
class PipelineSpanFactory:
    """Creates OpenTelemetry spans for pipelined execution."""

    def create_row_span(self, inflight: InflightRow) -> Span:
        """Create span for a row's complete lifecycle."""
        return self._tracer.start_span(
            name="pipeline.row",
            attributes={
                "elspeth.row_id": inflight.row_id,
                "elspeth.sequence_number": inflight.sequence_number,
                "elspeth.pipeline.rows_in_flight": self._metrics.rows_in_flight,
            },
        )

    def create_release_span(self, token: CompletedToken, wait_time_ms: float) -> Span:
        """Create span for token release (FIFO wait + sink write)."""
        return self._tracer.start_span(
            name="pipeline.release",
            attributes={
                "elspeth.token_id": token.token_id,
                "elspeth.sequence_number": token.sequence_number,
                "elspeth.outcome": token.outcome.value,
                "elspeth.sink_name": token.sink_name,
                "elspeth.fifo_wait_ms": wait_time_ms,
            },
        )
```

### 7.3 Structured Logging

```python
import structlog

logger = structlog.get_logger()

# SourcePuller logging
logger.info(
    "row_pulled",
    sequence_number=seq,
    row_id=row_id,
    rows_in_flight=self._rows_in_flight,
    backpressure_active=self._rows_in_flight >= self._config.max_rows_in_flight,
)

# ReleaseQueue logging
logger.info(
    "token_released",
    sequence_number=token.sequence_number,
    token_id=token.token_id,
    outcome=token.outcome.value,
    sink_name=token.sink_name,
    wait_time_ms=wait_time,
    tokens_waiting=len(self._waiting),
)

# Backpressure events
logger.warning(
    "backpressure_triggered",
    trigger="max_rows_in_flight",
    current=self._rows_in_flight,
    limit=self._config.max_rows_in_flight,
    oldest_pending_seq=min(self._waiting.keys()) if self._waiting else None,
)
```

### 7.4 Configuration Schema

```yaml
# settings.yaml
concurrency:
  # Row-level pipelining (NEW - supersedes ADR-001)
  pipelining:
    enabled: true                    # Enable pipelined execution
    max_rows_in_flight: 10           # Max source rows being processed
    max_completed_waiting: 20        # Max completed rows waiting for release

  # Query-level pooling (existing, now shared across rows)
  pool_size: 30                      # Shared pool capacity

  # Backpressure tuning
  backpressure:
    source_block_timeout_ms: 30000   # Max time to block source puller
    release_block_timeout_ms: 30000  # Max time to block on release queue

# Checkpoint settings (updated for pipelining)
checkpoint:
  enabled: true
  frequency: 100                     # Checkpoint every N released rows
  include_inflight_state: true       # Capture in-flight rows for recovery

# Metrics export
metrics:
  enabled: true
  export_interval_seconds: 10
  include_pipeline_metrics: true
```

### 7.5 Pydantic Configuration Models

```python
class PipeliningSettings(BaseModel):
    """Configuration for row-level pipelining."""

    enabled: bool = Field(
        default=False,  # Opt-in initially for safety
        description="Enable pipelined execution (supersedes ADR-001 sequential model)",
    )

    max_rows_in_flight: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Maximum source rows being processed simultaneously",
    )

    max_completed_waiting: int = Field(
        default=None,  # Computed as 2x max_rows_in_flight if not set
        ge=1,
        le=1000,
        description="Maximum completed rows waiting for FIFO release",
    )

    @model_validator(mode='after')
    def set_defaults(self) -> 'PipeliningSettings':
        if self.max_completed_waiting is None:
            self.max_completed_waiting = self.max_rows_in_flight * 2
        return self


class BackpressureSettings(BaseModel):
    """Backpressure tuning parameters."""

    source_block_timeout_ms: int = Field(
        default=30000,
        ge=1000,
        le=300000,
        description="Max time source puller blocks waiting for capacity",
    )

    release_block_timeout_ms: int = Field(
        default=30000,
        ge=1000,
        le=300000,
        description="Max time workers block waiting for release queue",
    )


class ConcurrencySettings(BaseModel):
    """Complete concurrency configuration."""

    pipelining: PipeliningSettings = Field(default_factory=PipeliningSettings)
    pool_size: int = Field(default=30, ge=1, le=1000)
    backpressure: BackpressureSettings = Field(default_factory=BackpressureSettings)
```

### 7.6 CLI Integration

```python
@app.command()
def run(
    settings: Path = typer.Option(..., "-s", "--settings"),
    execute: bool = typer.Option(False, "--execute"),
    # New pipelining overrides
    max_rows_in_flight: int | None = typer.Option(
        None,
        "--max-rows-in-flight",
        help="Override max_rows_in_flight (enables pipelining)",
    ),
):
    """Run a pipeline."""
    config = load_settings(settings)

    # CLI override enables pipelining
    if max_rows_in_flight is not None:
        config.concurrency.pipelining.enabled = True
        config.concurrency.pipelining.max_rows_in_flight = max_rows_in_flight

    # ...
```

### 7.7 Validation Rules

```python
def validate_pipelining_config(config: PipelineConfig) -> list[str]:
    """Validate pipelining configuration."""
    errors = []

    pipelining = config.concurrency.pipelining

    # max_completed_waiting should be >= max_rows_in_flight
    if pipelining.max_completed_waiting < pipelining.max_rows_in_flight:
        errors.append(
            f"max_completed_waiting ({pipelining.max_completed_waiting}) "
            f"should be >= max_rows_in_flight ({pipelining.max_rows_in_flight})"
        )

    # Warn if pipelining with SQLite (not recommended for production)
    if pipelining.enabled and pipelining.max_rows_in_flight > 1:
        if "sqlite" in config.landscape.url:
            errors.append(
                "Pipelining with max_rows_in_flight > 1 is not recommended "
                "with SQLite. Consider PostgreSQL for production workloads."
            )

    # Aggregations require careful tuning
    if pipelining.enabled and config.has_aggregations:
        if pipelining.max_rows_in_flight > 5:
            errors.append(
                "Pipelines with aggregations should use max_rows_in_flight <= 5 "
                "to avoid excessive memory in aggregation buffers."
            )

    return errors
```

---

## 8. Testing Strategy

### 8.1 Testing Overview

| Testing Type | Purpose | Tools |
|--------------|---------|-------|
| **Unit Tests** | Individual component correctness | pytest |
| **Property-Based Tests** | FIFO invariant never violated | Hypothesis |
| **Concurrency Tests** | Race conditions, deadlocks | pytest + threading |
| **Integration Tests** | End-to-end pipeline behavior | pytest + fixtures |
| **Stress Tests** | Performance under load | locust / custom |
| **Chaos Tests** | Crash recovery correctness | pytest + fault injection |

### 8.2 Critical Invariant Tests

```python
class TestFIFOInvariant:
    """FIFO ordering must NEVER be violated."""

    def test_fifo_ordering_linear_pipeline(self, pipelined_orchestrator):
        """Rows release in source order for linear pipelines."""
        results = pipelined_orchestrator.run(source_rows=100)

        release_order = [r.sequence_number for r in results.released_tokens]
        assert release_order == sorted(release_order), "FIFO violated!"

    def test_fifo_ordering_with_slow_row(self, pipelined_orchestrator):
        """Slow row blocks faster successors."""
        # Row 5 takes 10x longer than others
        source = SlowRowSource(slow_row_index=5, slow_factor=10)
        results = pipelined_orchestrator.run(source=source)

        release_order = [r.sequence_number for r in results.released_tokens]
        assert release_order == sorted(release_order), "FIFO violated with slow row!"

    def test_fifo_ordering_with_forks(self, pipelined_orchestrator):
        """Fork children release after all predecessors."""
        # Pipeline: source → fork(A,B) → sinks
        results = pipelined_orchestrator.run(source_rows=50)

        # Group by original row's sequence number
        for seq in range(1, 51):
            tokens_for_seq = [t for t in results.released_tokens if t.sequence_number == seq]
            predecessors = [t for t in results.released_tokens if t.sequence_number < seq]

            # All predecessors must have released before any token with this seq
            for token in tokens_for_seq:
                for pred in predecessors:
                    assert pred.released_at <= token.released_at, \
                        f"Token {token.token_id} (seq={seq}) released before predecessor {pred.token_id}"


class TestAuditCompleteness:
    """Every token must have complete audit trail."""

    def test_all_tokens_have_terminal_outcome(self, pipelined_orchestrator, landscape):
        """No orphan tokens - all reach terminal state."""
        results = pipelined_orchestrator.run(source_rows=100)

        all_tokens = landscape.get_all_tokens(results.run_id)
        outcomes = landscape.get_all_outcomes(results.run_id)

        tokens_with_outcomes = {o.token_id for o in outcomes}

        for token in all_tokens:
            assert token.token_id in tokens_with_outcomes, \
                f"Token {token.token_id} has no terminal outcome!"

    def test_node_states_recorded_before_release(self, pipelined_orchestrator, landscape):
        """Audit trail complete before sink write."""
        results = pipelined_orchestrator.run(source_rows=50)

        for token in results.released_tokens:
            if token.outcome in (RowOutcome.COMPLETED, RowOutcome.ROUTED):
                # Get artifact (sink write)
                artifact = landscape.get_artifact_for_token(token.token_id)

                # Get all node_states for this token
                states = landscape.get_node_states(token.token_id)

                # All states must be recorded before artifact
                for state in states:
                    assert state.completed_at <= artifact.created_at, \
                        f"node_state recorded after sink write!"
```

### 8.3 Property-Based Testing with Hypothesis

```python
from hypothesis import given, strategies as st, settings

class TestPipeliningProperties:
    """Property-based tests for pipelining invariants."""

    @given(
        num_rows=st.integers(min_value=1, max_value=200),
        max_rows_in_flight=st.integers(min_value=1, max_value=20),
        slow_row_indices=st.lists(st.integers(min_value=0, max_value=199), max_size=10),
        processing_times=st.lists(st.floats(min_value=0.001, max_value=0.5), min_size=1),
    )
    @settings(max_examples=100, deadline=60000)
    def test_fifo_never_violated(
        self,
        num_rows: int,
        max_rows_in_flight: int,
        slow_row_indices: list[int],
        processing_times: list[float],
    ):
        """FIFO ordering holds for any combination of row counts and timings."""
        # Create source with variable processing times
        source = VariableTimingSource(
            num_rows=num_rows,
            slow_indices=set(slow_row_indices),
            processing_times=processing_times,
        )

        orchestrator = PipelinedOrchestrator(
            config=PipeliningSettings(max_rows_in_flight=max_rows_in_flight),
        )

        results = orchestrator.run(source=source)

        # INVARIANT: release order == source order
        release_order = [r.sequence_number for r in results.released_tokens]
        assert release_order == list(range(1, len(release_order) + 1))

    @given(
        num_rows=st.integers(min_value=10, max_value=100),
        fork_probability=st.floats(min_value=0.0, max_value=0.5),
        num_branches=st.integers(min_value=2, max_value=4),
    )
    @settings(max_examples=50, deadline=120000)
    def test_fork_children_complete_before_release(
        self,
        num_rows: int,
        fork_probability: float,
        num_branches: int,
    ):
        """All fork children must complete before any are released."""
        source = RandomForkSource(
            num_rows=num_rows,
            fork_probability=fork_probability,
            num_branches=num_branches,
        )

        orchestrator = PipelinedOrchestrator()
        results = orchestrator.run(source=source)

        # Group tokens by fork_group_id
        fork_groups = defaultdict(list)
        for token in results.all_tokens:
            if token.fork_group_id:
                fork_groups[token.fork_group_id].append(token)

        # INVARIANT: all children in a fork group complete before any release
        for fg_id, tokens in fork_groups.items():
            completion_times = [t.completed_at for t in tokens]
            release_times = [t.released_at for t in tokens if t.released_at]

            if release_times:
                earliest_release = min(release_times)
                latest_completion = max(completion_times)
                assert latest_completion <= earliest_release, \
                    f"Fork group {fg_id}: child released before sibling completed"
```

### 8.4 Concurrency Stress Tests

```python
class TestConcurrencyStress:
    """Stress tests for race conditions and deadlocks."""

    def test_no_deadlock_under_backpressure(self):
        """Pipeline doesn't deadlock when backpressure triggers."""
        # Create slow sink that triggers backpressure
        slow_sink = SlowSink(write_delay_ms=100)

        orchestrator = PipelinedOrchestrator(
            config=PipeliningSettings(
                max_rows_in_flight=5,
                max_completed_waiting=10,
            ),
            sinks={"output": slow_sink},
        )

        # Should complete without hanging
        with timeout(seconds=60):
            results = orchestrator.run(source_rows=100)

        assert results.rows_released == 100

    def test_no_race_in_release_queue(self):
        """Multiple workers completing simultaneously don't corrupt state."""
        # All rows complete at roughly the same time
        instant_source = InstantProcessingSource(num_rows=1000)

        orchestrator = PipelinedOrchestrator(
            config=PipeliningSettings(max_rows_in_flight=50),
        )

        results = orchestrator.run(source=instant_source)

        # Verify no corruption
        assert len(results.released_tokens) == 1000
        assert len(set(t.token_id for t in results.released_tokens)) == 1000  # No duplicates

        # Verify FIFO
        release_order = [r.sequence_number for r in results.released_tokens]
        assert release_order == list(range(1, 1001))

    @pytest.mark.parametrize("num_workers", [2, 4, 8, 16, 32])
    def test_scaling_workers(self, num_workers: int):
        """Pipeline scales correctly with worker count."""
        orchestrator = PipelinedOrchestrator(
            config=PipeliningSettings(max_rows_in_flight=num_workers),
        )

        start = time.time()
        results = orchestrator.run(source_rows=100)
        elapsed = time.time() - start

        # Should complete and maintain FIFO
        assert results.rows_released == 100
        release_order = [r.sequence_number for r in results.released_tokens]
        assert release_order == list(range(1, 101))
```

### 8.5 Crash Recovery Tests

```python
class TestCrashRecovery:
    """Tests for checkpoint and recovery correctness."""

    def test_recovery_after_crash_mid_processing(self, tmp_path):
        """Crash during processing recovers correctly."""
        # Run until row 50, then simulate crash
        orchestrator = PipelinedOrchestrator(
            config=PipeliningSettings(max_rows_in_flight=10),
            checkpoint_frequency=10,
        )

        with pytest.raises(SimulatedCrash):
            orchestrator.run(
                source_rows=100,
                crash_at_row=50,
            )

        # Verify checkpoint exists
        checkpoint = orchestrator.get_latest_checkpoint()
        assert checkpoint is not None
        assert checkpoint.released_through_seq >= 40  # At least 4 checkpoints

        # Resume from checkpoint
        resumed = PipelinedOrchestrator.resume(checkpoint)
        results = resumed.run()

        # All 100 rows should be released exactly once
        all_released = list(range(1, checkpoint.released_through_seq + 1)) + \
                       [r.sequence_number for r in results.released_tokens]
        assert sorted(all_released) == list(range(1, 101))

    def test_recovery_no_duplicate_sink_writes(self, tmp_path):
        """Crash recovery doesn't duplicate sink writes."""
        tracking_sink = TrackingCSVSink(tmp_path / "output.csv")

        orchestrator = PipelinedOrchestrator(
            sinks={"output": tracking_sink},
        )

        # Crash and resume multiple times
        for crash_point in [25, 50, 75]:
            try:
                orchestrator.run(source_rows=100, crash_at_row=crash_point)
            except SimulatedCrash:
                checkpoint = orchestrator.get_latest_checkpoint()
                orchestrator = PipelinedOrchestrator.resume(checkpoint)

        # Final run
        orchestrator.run()

        # Verify no duplicates in sink
        written_rows = tracking_sink.get_all_written_rows()
        row_ids = [r["row_id"] for r in written_rows]
        assert len(row_ids) == len(set(row_ids)), "Duplicate sink writes detected!"
```

---

## 9. Migration Plan

### Phase 1: Foundation (Week 1-2)

| Task | Description | Risk |
|------|-------------|------|
| Add `sequence_number` to schema | Alembic migration for rows table | Low |
| Create `PipeliningSettings` | Configuration models with defaults | Low |
| Implement `InflightRow`, `CompletedToken` | Core data structures | Low |
| Add pipelining metrics | Metrics collection infrastructure | Low |

### Phase 2: Core Components (Week 3-4)

| Task | Description | Risk |
|------|-------------|------|
| Implement `SourcePuller` | Backpressure-aware row pulling | Medium |
| Implement `ReleaseQueue` | FIFO ordering and fork/join sync | High |
| Implement `WorkPool` | Thread pool integration | Medium |
| Thread-safe `LandscapeRecorder` | Connection pooling, transaction isolation | Medium |

### Phase 3: Integration (Week 5-6)

| Task | Description | Risk |
|------|-------------|------|
| Create `PipelinedOrchestrator` | Wire components together | High |
| Update `CheckpointManager` | Pipeline state serialization | Medium |
| CLI integration | `--max-rows-in-flight` flag | Low |
| Validation rules | Config validation for pipelining | Low |

### Phase 4: Testing & Hardening (Week 7-8)

| Task | Description | Risk |
|------|-------------|------|
| Property-based tests | Hypothesis test suite | Medium |
| Concurrency stress tests | Race condition hunting | High |
| Crash recovery tests | Checkpoint/resume validation | Medium |
| Performance benchmarks | Throughput and latency measurement | Low |

### Phase 5: Documentation & Rollout (Week 9)

| Task | Description | Risk |
|------|-------------|------|
| ADR-004: Row-Level Pipelining | Document architectural decision | Low |
| Update CLAUDE.md | New concurrency model documentation | Low |
| Migration guide | How to enable pipelining safely | Low |
| Gradual rollout | `enabled: false` default, opt-in | Low |

---

## 10. Rollback Plan

If issues are discovered post-deployment:

```yaml
# Instant rollback - disable pipelining
concurrency:
  pipelining:
    enabled: false  # Falls back to sequential model
```

**Rollback guarantees:**
- `enabled: false` + `max_rows_in_flight: 1` = identical behavior to ADR-001
- No schema changes required for rollback
- Existing runs and checkpoints remain valid
- `explain()` works for both pipelined and sequential runs

---

## 11. Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| FIFO invariant | 100% | Property tests, integration tests |
| Audit completeness | 100% | All tokens have terminal outcomes |
| Throughput improvement | ≥5x | Benchmark with LLM transforms |
| No deadlocks | 0 occurrences | Stress tests, production monitoring |
| Crash recovery | 100% correct | Recovery tests, no duplicate writes |
| Memory bounded | ≤ configured limits | Stress tests with backpressure |

---

## 12. References

- **Task Specification:** `docs/tasks/row-level-pipelining.md`
- **ADR-001:** `docs/design/adr/001-plugin-level-concurrency.md` (superseded)
- **Architecture:** `docs/design/architecture.md`
- **Plugin Protocol:** `docs/contracts/plugin-protocol.md`
- **Subsystems Overview:** `docs/design/subsystems/00-overview.md`

---

## Appendix A: Alternatives Considered

### A.1 Actor-Based Token Flow (Rejected)

**Approach:** Model each row as an actor with ordered communication channels between stages.

**Pros:**
- More natural fit for DAG branching (each branch is a channel)
- Better locality for fork/join
- Easier reasoning about ordering invariants

**Cons:**
- More complex infrastructure (channels, buffers per stage)
- Higher memory overhead
- Less familiar pattern

**Decision:** Rejected in favor of work-stealing pipeline for simplicity and alignment with existing code patterns.

### A.2 Extend ADR-001 (Rejected)

**Approach:** Keep sequential processing as default, add pipelining as opt-in feature.

**Pros:**
- Lower risk
- Preserves existing behavior

**Cons:**
- Two code paths to maintain
- Pipelining never becomes the default
- Technical debt

**Decision:** Rejected. Pipelining should supersede the sequential model as the new default for RC-1 performance requirements.

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Sequence Number** | Monotonic integer assigned at source pull time, used for FIFO ordering |
| **Inflight Row** | A row that has been pulled from source but not yet released to a sink |
| **Completed Token** | A token that has finished DAG processing, waiting in the release queue |
| **Release Queue** | Component that enforces FIFO ordering and dispatches tokens to sinks |
| **Fork Group** | Set of tokens (parent + children) created by a fork gate |
| **Coalesce Group** | Set of tokens being merged by a coalesce operation |
| **Backpressure** | Flow control mechanism that slows source pulling when pipeline is saturated |
