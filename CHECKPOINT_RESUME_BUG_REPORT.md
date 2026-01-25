# Checkpoint & Resume System Bug Report
**Date:** 2026-01-25
**Branch:** fix/rc1-bug-burndown-session-4
**Commit:** f70f38d
**Status:** CRITICAL - Multiple P0/P1 bugs found after refactoring

## Executive Summary

The checkpoint and resume system has **9 significant bugs** discovered through systematic deep-dive analysis with explore agents. Two are P0 (critical) causing silent data loss and audit trail corruption. Three are P1 (high) causing resume crashes or wrong results. The root cause is that the recent refactoring (commit 31cd066) added graph-based topology validation but violated transaction boundaries and sink durability guarantees.

**Impact:** The system cannot reliably resume from crashes without data loss or corruption.

---

## Critical Bugs (P0) - Fix Immediately

### BUG #1: Topology Hash Computed Outside Transaction
**File:** `src/elspeth/core/checkpoint/manager.py:71-74`
**Severity:** P0 - Audit Trail Corruption
**Reporter:** Explore agent (checkpoint manager analysis)

#### Current Code
```python
def create_checkpoint(
    self,
    run_id: str,
    token_id: str,
    node_id: str,
    sequence_number: int,
    graph: "ExecutionGraph",
    aggregation_state: dict[str, Any] | None = None,
) -> Checkpoint:
    """Create a checkpoint at current progress point."""

    # Compute topology hashes
    upstream_topology_hash = compute_upstream_topology_hash(graph, node_id)  # ← OUTSIDE transaction
    node_info = graph.get_node_info(node_id)
    checkpoint_node_config_hash = stable_hash(node_info.config)

    checkpoint_id = generate_checkpoint_id()
    created_at = datetime.now(UTC)

    with self._db.engine.connect() as conn:  # ← Transaction starts HERE
        conn.execute(
            insert(checkpoints_table).values(
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                token_id=token_id,
                node_id=node_id,
                sequence_number=sequence_number,
                upstream_topology_hash=upstream_topology_hash,  # ← Stale value
                checkpoint_node_config_hash=checkpoint_node_config_hash,
                aggregation_state_json=json.dumps(aggregation_state) if aggregation_state else None,
                created_at=created_at,
            )
        )
        conn.commit()
```

#### The Race Condition

**Timeline:**
1. T0: Thread A calls `create_checkpoint()`, computes `upstream_topology_hash = "abc123"`
2. T1: Thread B modifies graph (adds upstream node)
3. T2: Thread A enters transaction, inserts checkpoint with stale hash "abc123"
4. T3: On resume, `compute_upstream_topology_hash()` returns "xyz789" (new hash)
5. T4: Validation fails: "abc123" != "xyz789" → checkpoint rejected as incompatible

**Worse scenario:**
1. T0: Thread A computes topology hash
2. T1: Graph modified (node removed upstream)
3. T2: Thread A stores checkpoint with hash referencing non-existent node
4. T3: On resume, validation might crash or pass incorrectly

#### Why This Violates CLAUDE.md

From CLAUDE.md Tier 1 trust model:
> **Our Data (Audit Database / Landscape) - FULL TRUST**
> Must be 100% pristine at all times. We wrote it, we own it, we trust it completely.
> - Bad data in the audit trail = **crash immediately**
> - No coercion, no defaults, no silent recovery

The checkpoint table stores a topology hash that does not match the graph state at checkpoint time. This is "bad data in the audit trail."

#### Proposed Fix Options

**Option A: Move computation inside transaction**
```python
def create_checkpoint(...) -> Checkpoint:
    checkpoint_id = generate_checkpoint_id()
    created_at = datetime.now(UTC)

    with self._db.engine.begin() as conn:  # ← begin() for auto-rollback
        # Compute hashes inside transaction
        upstream_topology_hash = compute_upstream_topology_hash(graph, node_id)
        node_info = graph.get_node_info(node_id)
        checkpoint_node_config_hash = stable_hash(node_info.config)

        conn.execute(insert(checkpoints_table).values(...))
        # Auto-commit on context exit
```

**Pro:** Simple, keeps computation and storage atomic
**Con:** Graph operations inside DB transaction (cross-domain coupling)

**Option B: Add graph read lock**
```python
def create_checkpoint(...) -> Checkpoint:
    with graph._lock.read():  # ← Hypothetical graph lock
        upstream_topology_hash = compute_upstream_topology_hash(graph, node_id)
        node_info = graph.get_node_info(node_id)
        checkpoint_node_config_hash = stable_hash(node_info.config)

    with self._db.engine.begin() as conn:
        conn.execute(insert(checkpoints_table).values(...))
```

**Pro:** Separates concerns (graph vs DB), allows concurrent reads
**Con:** Requires adding locking to ExecutionGraph (new feature)

**Option C: Validate hash after storage**
```python
def create_checkpoint(...) -> Checkpoint:
    upstream_topology_hash = compute_upstream_topology_hash(graph, node_id)
    node_info = graph.get_node_info(node_id)
    checkpoint_node_config_hash = stable_hash(node_info.config)

    with self._db.engine.begin() as conn:
        conn.execute(insert(checkpoints_table).values(...))

    # Verify hash still matches
    recomputed_hash = compute_upstream_topology_hash(graph, node_id)
    if recomputed_hash != upstream_topology_hash:
        # Hash changed between compute and store
        self.delete_checkpoint(checkpoint_id)
        raise RuntimeError(f"Graph topology changed during checkpoint creation")
```

**Pro:** Detects race condition, fails safely
**Con:** Wasteful (creates then deletes), still has window where checkpoint exists with wrong hash

#### Recommended Fix
**Option A** - Move computation inside transaction. Rationale:
- Simplest implementation
- Graph is read-only during checkpoint creation (no modification expected)
- Transaction scope is brief (no long-running computation)
- Matches CLAUDE.md principle: "Make the fix right, not quick"

---

### BUG #2: Checkpoints Created Before Sink Writes Complete
**File:** `src/elspeth/engine/orchestrator.py:1068-1090`
**Severity:** P0 - Silent Data Loss
**Reporter:** Explore agent (orchestrator integration analysis)

#### Current Code
```python
# Line 1068-1090: Post-sink checkpoint callback
def checkpoint_after_sink(sink_node_id: str) -> Callable[[TokenInfo], None]:
    """Create checkpoint callback to run after each sink write."""
    def callback(token: TokenInfo) -> None:
        if self._checkpoint_manager and self._checkpoint_settings:
            self._maybe_checkpoint(
                run_id=token.token_id.split("-")[0],  # Extract run_id
                token_id=token.token_id,
                node_id=sink_node_id,
            )
    return callback

# Line 1085: Callback passed to sink executor
sink_executor.write(
    ...,
    checkpoint_callback=checkpoint_after_sink(sink_node_id),  # ← Checkpoint AFTER write returns
)
```

#### The Problem

**Sequence:**
1. Token processed through transform
2. `sink_executor.write()` called
3. Sink writes to file/DB (may buffer, may not flush)
4. Write returns (but may not be durable yet)
5. `checkpoint_callback` fires → checkpoint created
6. **CRASH** before sink flushes
7. On resume: checkpoint exists, so row is skipped
8. **Result:** Output artifact never written, but audit trail says it was

#### Example Scenario: CSV Sink

```python
# In CSVSink.write()
def write(self, rows: list[dict], checkpoint_callback: Callable | None = None):
    for row in rows:
        self._file.write(csv_line(row))  # ← Buffered write
        if checkpoint_callback:
            checkpoint_callback(row["token"])  # ← Checkpoint created
    # File not flushed yet!

# On crash, buffered writes lost but checkpoint exists
```

#### Why This Violates CLAUDE.md

From CLAUDE.md auditability standard:
> Every decision must be traceable to source data, configuration, and code version

The checkpoint claims row X was "completed" (reached sink), but the output artifact was never durably written. The audit trail is lying.

#### Proposed Fix Options

**Option A: Checkpoint only after flush**
```python
def write(self, rows: list[dict], checkpoint_callback: Callable | None = None):
    for row in rows:
        self._file.write(csv_line(row))

    self._file.flush()  # ← Ensure durability
    os.fsync(self._file.fileno())  # ← Force to disk

    # NOW checkpoint
    if checkpoint_callback:
        for row in rows:
            checkpoint_callback(row["token"])
```

**Pro:** Guarantees output durability before checkpoint
**Con:** Single flush per batch (not per row), changes callback semantics

**Option B: Two-phase checkpoint (pending → confirmed)**
```python
# Phase 1: Create "pending" checkpoint before write
pending_checkpoint = checkpoint_manager.create_pending_checkpoint(...)

# Phase 2: Write to sink
sink.write(rows)

# Phase 3: Confirm checkpoint (or rollback if write failed)
checkpoint_manager.confirm_checkpoint(pending_checkpoint.id)
```

**Pro:** Atomic semantics, can rollback on failure
**Con:** Requires new checkpoint state machine, more complex

**Option C: Move checkpoint to end of batch**
```python
# Don't checkpoint per-row, checkpoint once per batch after all writes
sink_executor.write_batch(rows)
sink_executor.flush()

# All rows durable, now checkpoint the last one
checkpoint_manager.create_checkpoint(..., token_id=rows[-1].token_id)
```

**Pro:** Simple, fewer checkpoints (better performance)
**Con:** Lose granularity, resume has to reprocess entire batch

#### Recommended Fix
**Option A with Option C** - Batch flush + checkpoint at batch boundary. Rationale:
- Checkpointing every row is wasteful
- Batch-level checkpoints are sufficient for resume
- Flush after batch guarantees all outputs are durable
- Aligns with CLAUDE.md: "This is more storage than minimal, but it means explain() queries are simple and complete"

---

## High Severity Bugs (P1) - Fix Before RC

### BUG #3: Resume Uses Synthetic Edge IDs (FK Violation)
**File:** `src/elspeth/engine/orchestrator.py:1413-1418`
**Severity:** P1 - Resume Crashes
**Reporter:** Explore agent (orchestrator integration analysis)

#### Current Code
```python
# Build edge_map from graph edges
edge_map: dict[tuple[str, str], str] = {}
for i, edge_info in enumerate(graph.get_edges()):
    # Generate synthetic edge_id for resume (edges were registered in original run)
    edge_id = f"resume_edge_{i}"  # ← SYNTHETIC - never registered in DB
    edge_map[(edge_info.from_node, edge_info.label)] = edge_id
```

#### The Problem

**Original run:**
```python
# Edges registered with real IDs
edge = recorder.register_edge(
    run_id=run_id,
    from_node_id="gate-fork",
    to_node_id="sink-a",
    label="route_a",
    ...
)
# edge.edge_id = "550e8400-e29b-41d4-a716-446655440000" (real UUID)
```

**Resume run:**
```python
# Synthetic edge ID
edge_map[("gate-fork", "route_a")] = "resume_edge_0"  # ← FAKE

# When gate routes, tries to record event
recorder.record_routing_event(
    token_id=token.token_id,
    edge_id="resume_edge_0",  # ← FK violation
    ...
)
# ERROR: FOREIGN KEY constraint failed: routing_events.edge_id -> edges.edge_id
```

#### Proposed Fix Options

**Option A: Load real edge IDs from database**
```python
# Query edges table for this run
edge_map: dict[tuple[str, str], str] = {}
with self._db.engine.connect() as conn:
    edges = conn.execute(
        select(edges_table).where(edges_table.c.run_id == run_id)
    ).fetchall()

    for edge in edges:
        edge_map[(edge.from_node_id, edge.label)] = edge.edge_id  # ← REAL ID
```

**Pro:** Uses real IDs, no FK violation
**Con:** Requires database query on resume

**Option B: Don't record routing events on resume**
```python
if self._is_resume:
    # Skip routing event recording (events already recorded in original run)
    pass
else:
    recorder.record_routing_event(...)
```

**Pro:** Avoids the problem entirely
**Con:** Incomplete audit trail (missing retry routing events)

**Option C: Re-register edges on resume**
```python
# Re-register edges (idempotent - same run_id)
for edge_info in graph.get_edges():
    edge = recorder.register_edge(...)  # Returns existing or creates new
    edge_map[(edge_info.from_node, edge_info.label)] = edge.edge_id
```

**Pro:** Reuses existing registration logic
**Con:** Might create duplicate edges if not properly idempotent

#### Recommended Fix
**Option A** - Load real edge IDs from database. Rationale:
- Preserves audit trail completeness
- Uses existing edge records (no duplication)
- Simple query with minimal overhead
- Matches CLAUDE.md: "The Landscape audit trail is the source of truth"

---

### BUG #4: Type Degradation on Resume (Schema Optional)
**File:** `src/elspeth/core/checkpoint/recovery.py:190-203`
**Severity:** P1 - Data Integrity
**Reporter:** Explore agent (recovery manager analysis)

#### Current Code
```python
def get_unprocessed_row_data(
    self,
    run_id: str,
    source_schema_class: type[PluginSchema] | None = None,  # ← OPTIONAL
) -> list[dict[str, Any]]:
    """Get unprocessed row data with payload resolution."""
    ...
    for row in unprocessed_rows:
        payload_bytes = self._payload_store.retrieve(row.source_data_ref)
        degraded_data = json.loads(payload_bytes.decode("utf-8"))  # ← All types become primitives

        if source_schema_class is not None:
            # Restore types via schema validation
            validated = source_schema_class.model_validate(degraded_data)
            row_data = validated.to_row()  # ← Types correct
        else:
            # No schema - return degraded types
            row_data = degraded_data  # ← datetime→str, Decimal→str, etc.

        result.append(row_data)
```

#### The Problem

**Type degradation example:**
```python
# Original source data (before checkpoint)
{
    "timestamp": datetime(2024, 1, 1, 12, 0, 0),  # datetime object
    "amount": Decimal("123.45"),                  # Decimal object
    "count": 42                                   # int
}

# Stored in payload via canonical_json
{
    "timestamp": "2024-01-01T12:00:00Z",  # ISO string
    "amount": "123.45",                   # string
    "count": 42                           # still int
}

# Resume WITHOUT schema
{
    "timestamp": "2024-01-01T12:00:00Z",  # str (was datetime)
    "amount": "123.45",                   # str (was Decimal)
    "count": 42                           # int (unchanged)
}

# Transform expects datetime, gets str → CRASH or wrong result
```

#### Test Evidence
From `tests/core/checkpoint/test_recovery_type_fidelity.py`:
```python
def test_get_unprocessed_row_data_loses_type_fidelity():
    """Demonstrate that without schema, types are degraded."""

    # Without schema
    rows = recovery_manager.get_unprocessed_row_data(run_id)  # No schema
    timestamp_degraded = rows[0]["timestamp"]
    amount_degraded = rows[0]["amount"]

    # BUG DEMONSTRATION: These should be datetime and Decimal, but they are str!
    assert isinstance(timestamp_degraded, str), "Without schema, timestamp should be str"
    assert isinstance(amount_degraded, str), "Without schema, amount should be str"
```

#### Why This Violates CLAUDE.md

From CLAUDE.md Tier 2 trust model:
> **Pipeline Data (Post-Source) - ELEVATED TRUST**
> Types are trustworthy (source validated and/or coerced them)
> Transforms/sinks **expect conformance** - if types are wrong, that's an upstream plugin bug

Resumed data violates the type contract. Transforms that worked in the original run will fail on resume because they receive different types.

#### Proposed Fix Options

**Option A: Make schema required**
```python
def get_unprocessed_row_data(
    self,
    run_id: str,
    source_schema_class: type[PluginSchema],  # ← REQUIRED, not optional
) -> list[dict[str, Any]]:
    """Get unprocessed row data with payload resolution."""
    ...
    validated = source_schema_class.model_validate(degraded_data)
    return validated.to_row()
```

**Pro:** Guarantees type fidelity
**Con:** Breaking change (callers must provide schema)

**Option B: Store type metadata in checkpoint**
```python
# In checkpoint, store schema class name
checkpoint = {
    ...,
    "source_schema_class": "MySourceSchema",  # ← Store class name
}

# On resume, dynamically load schema
schema_class = import_schema(checkpoint.source_schema_class)
validated = schema_class.model_validate(degraded_data)
```

**Pro:** No breaking change, automatic type restoration
**Con:** Dynamic import complexity, schema must be available

**Option C: Fail loudly without schema**
```python
if source_schema_class is None:
    raise ValueError(
        f"Schema required for resume to preserve type fidelity. "
        f"Run {run_id} cannot resume without source schema."
    )
```

**Pro:** Fails early with clear error
**Con:** Still requires caller to provide schema

#### Recommended Fix
**Option A** - Make schema required. Rationale:
- Enforces type contract
- Matches CLAUDE.md: "No coercion, no defaults, no silent recovery"
- Breaking change is acceptable (RC phase, not production)
- Alternative is to silently corrupt data, which is worse

---

### BUG #5: No Transaction Rollback on Hash Compute Failure
**File:** `src/elspeth/core/checkpoint/manager.py:72-90`
**Severity:** P1 - Transaction Safety
**Reporter:** Explore agent (checkpoint manager analysis)

#### Current Code
```python
def create_checkpoint(...) -> Checkpoint:
    upstream_topology_hash = compute_upstream_topology_hash(graph, node_id)  # ← Can throw

    with self._db.engine.connect() as conn:  # ← connect() doesn't auto-rollback
        conn.execute(insert(checkpoints_table).values(...))
        conn.commit()
```

#### The Problem

If `compute_upstream_topology_hash()` throws (e.g., invalid graph, networkx error), the connection is opened but never commits. SQLAlchemy's `connect()` context manager **closes the connection but does NOT rollback**.

**On PostgreSQL:** Unclosed transactions can leave locks.
**On SQLite:** Less critical (auto-rollback on close), but still violates best practices.

#### Proposed Fix
```python
def create_checkpoint(...) -> Checkpoint:
    checkpoint_id = generate_checkpoint_id()
    created_at = datetime.now(UTC)

    with self._db.engine.begin() as conn:  # ← begin() auto-rollbacks on exception
        # Compute inside transaction (per Bug #1 fix)
        upstream_topology_hash = compute_upstream_topology_hash(graph, node_id)
        node_info = graph.get_node_info(node_id)
        checkpoint_node_config_hash = stable_hash(node_info.config)

        conn.execute(insert(checkpoints_table).values(...))
        # Auto-commit on clean exit, auto-rollback on exception
```

**This fix combines with Bug #1 fix.**

---

## Medium Severity Bugs (P2)

### BUG #6: Aggregation Timeout Age Resets on Resume
**File:** `src/elspeth/engine/executors.py:1217-1222` + `src/elspeth/triggers.py:164`
**Severity:** P2 - Timeout Semantics Broken
**Reporter:** Explore agent (orchestrator integration analysis)

#### The Problem

Checkpoint stores aggregation buffer tokens but NOT timing metadata:
```python
# Checkpoint state (executors.py:1118-1129)
state[node_id] = {
    "tokens": [reconstructed tokens],
    "batch_id": batch.batch_id,
    # ← NO first_accept_time or elapsed_age_seconds
}
```

On restore, `record_accept()` is called to rebuild trigger state:
```python
# triggers.py:164
def record_accept(self) -> None:
    if self._first_accept_time is None:
        self._first_accept_time = time.monotonic()  # ← CURRENT TIME
```

**Result:** Timeout window resets on resume, violating SLA.

#### Proposed Fix
Store `first_accept_time` in checkpoint aggregation state:
```python
state[node_id] = {
    "tokens": [...],
    "batch_id": ...,
    "first_accept_time": time.monotonic(),  # ← Add this
}

# On restore
evaluator._first_accept_time = state["first_accept_time"]
```

---

### BUG #7: Schema Allows NULL on Audit Fields
**File:** `src/elspeth/core/landscape/schema.py:352-354`
**Severity:** P2 - Schema Enforcement
**Reporter:** Explore agent (checkpoint manager analysis)

#### Current Code
```python
checkpoints_table = Table(
    "checkpoints",
    metadata,
    Column("checkpoint_id", String, primary_key=True),
    ...,
    Column("upstream_topology_hash", String),  # ← nullable=True (default)
    Column("checkpoint_node_config_hash", String),  # ← nullable=True (default)
)
```

Per CLAUDE.md Tier 1 trust model, audit fields should be `nullable=False`.

#### Proposed Fix
```python
Column("upstream_topology_hash", String, nullable=False),
Column("checkpoint_node_config_hash", String, nullable=False),
```

**Requires migration** to set NOT NULL constraint.

---

### BUG #8: Resume Leaves Checkpoints on Early Exit
**File:** `src/elspeth/engine/orchestrator.py:1348-1358`
**Severity:** P2 - Cleanup Missing
**Reporter:** Explore agent (orchestrator integration analysis)

#### Current Code
```python
if not unprocessed_rows:
    # All rows were processed - complete the run
    recorder.complete_run(run_id, status="completed")
    return RunResult(...)  # ← Returns without _delete_checkpoints()
```

Normal completion path (lines 1370-1377) calls `_delete_checkpoints(run_id)`, but early-exit doesn't.

#### Proposed Fix
```python
if not unprocessed_rows:
    recorder.complete_run(run_id, status="completed")
    self._delete_checkpoints(run_id)  # ← Add this
    return RunResult(...)
```

---

## Low Severity Bugs (P3)

### BUG #9: No Validation of Graph Parameter
**File:** `src/elspeth/core/checkpoint/manager.py:50-74`
**Severity:** P3 - Missing Guard
**Reporter:** Explore agent (checkpoint manager analysis)

#### The Problem
`graph` parameter is documented as required but never validated. If `node_id` doesn't exist in graph, `graph.get_node_info(node_id)` raises KeyError late.

#### Proposed Fix
```python
def create_checkpoint(...) -> Checkpoint:
    # Validate graph parameter
    if not graph.has_node(node_id):
        raise ValueError(f"Node {node_id} not found in graph")

    # Continue with checkpoint creation
```

---

## Architecture Review Questions

### 1. Transaction Boundaries
**Question:** Should graph operations happen inside or outside database transactions?

**Current state:** Outside (Bug #1)
**Concern:** Cross-domain coupling (graph in-memory, DB persistent)
**Trade-off:** Atomicity vs separation of concerns

**Options:**
- A: Graph ops inside transaction (simple, atomic)
- B: Graph read locks (complex, better separation)
- C: Validate after storage (wasteful, eventually consistent)

### 2. Checkpoint Durability Semantics
**Question:** What does a checkpoint mean?

**Current state:** "Token reached this node" (Bug #2)
**Should be:** "Token completed processing AND output is durable"

**Options:**
- A: Checkpoint after sink flush (per-batch)
- B: Two-phase checkpoint (pending → confirmed)
- C: Checkpoint only after ALL sinks complete (simplest)

### 3. Resume Edge ID Management
**Question:** How should resume handle edge IDs?

**Current state:** Synthetic IDs (Bug #3)
**Concern:** FK integrity vs performance

**Options:**
- A: Load from database (simple, correct)
- B: Re-register edges (idempotent, but duplicates?)
- C: Skip routing events on resume (incomplete audit)

### 4. Type Fidelity on Resume
**Question:** Is schema required for resume?

**Current state:** Optional, types degrade (Bug #4)
**Concern:** Breaking change vs data integrity

**Options:**
- A: Make schema required (breaking but correct)
- B: Store schema in checkpoint (complex)
- C: Fail loudly without schema (forces fix)

---

## Recommended Fix Priority

1. **P0 - Week 1:**
   - Bug #1: Transaction boundaries
   - Bug #2: Checkpoint durability

2. **P1 - Week 2:**
   - Bug #3: Edge ID loading
   - Bug #4: Schema requirement
   - Bug #5: Transaction rollback

3. **P2 - Week 3:**
   - Bug #6: Timeout restoration
   - Bug #7: Schema constraints
   - Bug #8: Cleanup on early exit

4. **P3 - Week 4:**
   - Bug #9: Parameter validation

---

## Test Strategy

### New Tests Required

1. **Concurrency tests** for Bug #1 (race condition)
2. **Crash simulation** for Bug #2 (sink durability)
3. **Resume with gates** for Bug #3 (FK integrity)
4. **Type fidelity** for Bug #4 (already exists, make it fail loudly)
5. **Timeout SLA** for Bug #6 (aggregation timing)

### Integration Test Scenarios

- Resume after crash during sink write
- Resume with modified graph (should reject)
- Resume with gates (should not crash)
- Resume with aggregations near timeout
- Concurrent checkpoint creation

---

## Appendix: Explore Agent Findings

### Agent 1: Checkpoint Manager
- Found: Bugs #1, #5, #7, #9
- Analysis: Transaction boundaries, error handling
- Recommendation: Move to `begin()` instead of `connect()`

### Agent 2: Recovery Manager
- Found: Bug #4
- Analysis: Type degradation, schema handling
- Recommendation: Make schema required

### Agent 3: Compatibility Validator
- Found: **No bugs** - validation is sound
- Analysis: Topology hashing correct
- Note: Tests comprehensive, logic verified

### Agent 4: Orchestrator Integration
- Found: Bugs #2, #3, #6, #8
- Analysis: Lifecycle issues, resume paths
- Recommendation: Checkpoint after flush, load real edge IDs

---

## Sign-off

This report requires review and consensus from:
- [ ] Code Review Agent (implementation correctness)
- [ ] Architecture Critic (design patterns, trade-offs)
- [ ] Project Lead (priority, timeline)

**Next Steps:**
1. Review recommended fixes
2. Agree on architecture questions
3. Create implementation plan
4. Write comprehensive tests
5. Implement fixes by priority
