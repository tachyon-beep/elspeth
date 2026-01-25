# Checkpoint & Resume Bugs - Expert Review Consensus
**Date:** 2026-01-25
**Reviewers:** Python Code Reviewer (axiom-python-engineering), Architecture Critic (axiom-system-architect)
**Status:** APPROVED WITH AMENDMENTS

## Executive Summary

Both expert reviewers **confirm all 9 bugs are real and correctly diagnosed**. However, they identified **3 critical gaps** in the original analysis and **3 additional bugs** that must be fixed. The consensus is that the proposed fixes are mostly correct, but Bug #2 requires a **protocol-level architectural change**, not just implementation fixes.

---

## Consensus: Critical Gaps in Original Report

### GAP #1: Missing `os.fsync()` in CSVSink (CRITICAL)
**Identified by:** Code Reviewer
**Severity:** P0 - Makes Bug #2 unfixable without this

The original Bug #2 analysis correctly identifies checkpoints before sink writes, but **misses the root cause**: CSVSink doesn't call `os.fsync()`.

**Current Code (csv_sink.py:137):**
```python
file.flush()  # Flushes to OS buffer, NOT to disk
```

**What's missing:**
```python
file.flush()           # Write to OS buffer
os.fsync(file.fileno())  # ← MISSING: Force to disk
```

**Impact:** Even if checkpoint callback is delayed until after `flush()`, data is only in OS buffer. Crash before OS flushes → silent data loss.

**Required Fix:**
```python
# In CSVSink.write(), after line 137
self._file.flush()
os.fsync(self._file.fileno())  # ← ADD THIS
```

**Consensus:** This is mandatory for Bug #2 fix. Must be added to ALL sinks.

---

### GAP #2: Missing Sink Durability Contract (ARCHITECTURAL)
**Identified by:** Architecture Critic
**Severity:** P0 - Bug #2 cannot be fully fixed without this

The `SinkProtocol` has no durability contract. The protocol interface has:
- `write(rows, ctx) -> ArtifactInfo` - But no guarantee when data persists
- No `flush()` method
- No documentation of durability semantics

**Impact:** Different sinks have different durability guarantees:
- CSVSink: Buffered, needs `fsync()`
- DatabaseSink: Connection pooled, needs `commit()`
- Future Kafka/S3 sinks: Async, needs `await flush()`

**Required Architecture Change:**

Add to `SinkProtocol` (contracts.py):
```python
@abstractmethod
def flush(self) -> None:
    """Ensure all buffered writes are durable.

    MUST guarantee that when this method returns:
    - All data passed to write() is persisted
    - Data survives process crash
    - Data survives power loss (for file/block storage)

    This method MUST block until durability is guaranteed.
    """
    pass
```

**Required Implementation Changes:**

```python
# In orchestrator.py, after sink.write()
sink_executor.write(rows, ctx)
sink_executor.flush()  # ← ADD: Guarantee durability

# THEN create checkpoint
if checkpoint_callback:
    for token in tokens:
        checkpoint_callback(token)
```

**Consensus:** This is a **protocol change** that fixes Bug #2 architecturally, not just symptomatically.

---

### GAP #3: Checkpoint Callback Error Handling Missing
**Identified by:** Code Reviewer (Additional Bug #10)
**Severity:** P0 - Can cause audit trail inconsistency

**Current Code (executors.py:1457-1460):**
```python
if on_token_written is not None:
    for token in tokens:
        on_token_written(token)  # ← No try/except
```

**Problem:** If checkpoint creation fails AFTER sink write:
1. Sink write is durable (can't roll back)
2. Checkpoint fails (exception thrown)
3. Node states marked complete
4. But no checkpoint record exists
5. Resume cannot find checkpoint → processes rows again → **duplicate data**

**Required Fix:**
```python
if on_token_written is not None:
    for token in tokens:
        try:
            on_token_written(token)
        except Exception as e:
            # Critical: Sink write is durable, can't roll back
            # Log error and continue - manual cleanup required
            logger.error(
                f"Checkpoint failed after durable sink write for token {token.token_id}. "
                f"Manual cleanup required. Error: {e}",
                exc_info=True
            )
            # Don't raise - we can't undo the sink write
```

**Consensus:** This must be part of Bug #2 fix.

---

## Consensus: Additional Bugs Found

### ADDITIONAL BUG #10: Partial Batch Failure Creates Duplicates
**Identified by:** Code Reviewer
**Severity:** P1 - Data integrity

**Scenario:**
```python
# Sink writing batch of 100 rows
for i, row in enumerate(rows):
    file.write(row)
    if i == 50:
        raise IOError("Disk full")  # Crash mid-batch
```

**Result:**
- 50 rows written to sink
- Batch marked failed
- On resume: All 100 rows reprocessed
- **First 50 rows written twice** (duplicates)

**Root Cause:** Sinks are not atomic at batch boundaries.

**Fix Options:**

**Option A: Temp file + rename (atomic)**
```python
def write(self, rows, ctx):
    temp_file = f"{self._output_path}.tmp"
    with open(temp_file, 'w') as f:
        for row in rows:
            writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())

    # Atomic rename
    os.rename(temp_file, self._output_path)
```

**Option B: Document non-atomic behavior**
```
KNOWN LIMITATION (RC-1):
Sinks are not atomic at batch boundaries. If crash occurs mid-batch,
resume may write duplicate rows. This is acceptable for RC-1.
Post-RC: Add transaction support to sink protocol.
```

**Consensus:** Option B for RC-1 (document limitation), Option A for post-RC.

---

### ADDITIONAL BUG #11: Type Annotations Too Broad
**Identified by:** Code Reviewer
**Severity:** P3 - Type safety

**Current:**
```python
source_schema_class: type[Any] | None = None  # Too broad
```

**Should be:**
```python
from elspeth.contracts import PluginSchema
source_schema_class: type[PluginSchema] | None = None
```

**Consensus:** Fix with Bug #4 (make schema required).

---

### ADDITIONAL BUG #12: No Checkpoint State Version Validation
**Identified by:** Code Reviewer
**Severity:** P2 - Migration support

**Problem:** If checkpoint format changes, old checkpoints fail with cryptic errors.

**Fix:**
```python
# In checkpoint state
state = {
    "_version": "1.0",  # Add version field
    "node_states": {...},
}

# On restore
if state.get("_version") != "1.0":
    raise ValueError(
        f"Incompatible checkpoint version: {state.get('_version')}. "
        f"Expected: 1.0. Cannot resume from incompatible checkpoint."
    )
```

**Consensus:** Add to P2 priority for future-proofing.

---

## Consensus: Revised Fix Recommendations

### Bug #1: Topology Hash Race Condition

**AGREED FIX: Option A (Move inside transaction)**

Both reviewers agree this is the correct fix. Architecture Critic notes the race condition is more about crash consistency than multi-threading, but the fix is the same.

**Implementation:**
```python
def create_checkpoint(...) -> Checkpoint:
    checkpoint_id = generate_checkpoint_id()
    created_at = datetime.now(UTC)  # Move inside too (temporal consistency)

    with self._db.engine.begin() as conn:  # begin() not connect()
        # Compute topology hashes INSIDE transaction
        upstream_topology_hash = compute_upstream_topology_hash(graph, node_id)
        node_info = graph.get_node_info(node_id)
        checkpoint_node_config_hash = stable_hash(node_info.config)

        conn.execute(
            insert(checkpoints_table).values(
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                token_id=token_id,
                node_id=node_id,
                sequence_number=sequence_number,
                upstream_topology_hash=upstream_topology_hash,
                checkpoint_node_config_hash=checkpoint_node_config_hash,
                aggregation_state_json=json.dumps(aggregation_state) if aggregation_state else None,
                created_at=created_at,
            )
        )
        # Auto-commit on clean exit, auto-rollback on exception
```

**Additional fixes from reviews:**
1. Also move `created_at` inside transaction (Code Reviewer)
2. Validate graph parameter at function start (Code Reviewer - Bug #9)

---

### Bug #2: Checkpoint Before Sink Durability

**AGREED FIX: Three-part architectural fix**

Both reviewers agree the report's "Option A + C" is incomplete. The consensus fix requires:

**Part 1: Add SinkProtocol.flush() (ARCHITECTURAL)**
```python
# In contracts.py SinkProtocol
@abstractmethod
def flush(self) -> None:
    """Ensure all buffered writes are durable."""
    pass
```

**Part 2: Implement flush() in all sinks**
```python
# CSVSink
def flush(self) -> None:
    self._file.flush()
    os.fsync(self._file.fileno())

# DatabaseSink
def flush(self) -> None:
    self._connection.commit()
```

**Part 3: Call flush before checkpoint**
```python
# In orchestrator, after sink writes
sink_executor.write(batch_tokens, ctx)
sink_executor.flush()  # ← Guarantee durability

# NOW safe to checkpoint
if checkpoint_callback:
    for token in batch_tokens:
        try:
            checkpoint_callback(token)
        except Exception as e:
            logger.error(f"Checkpoint failed after flush: {e}")
            # Don't raise - can't undo flush
```

**Checkpoint Granularity:** Both reviewers agree batch-level checkpointing is acceptable, but Architecture Critic notes this may affect `explain()` queries. **Action item:** Verify explain() doesn't require row-level granularity.

---

### Bug #3: Synthetic Edge IDs

**AGREED FIX: Option A (Load from database)**

Both reviewers agree this is correct. Architecture Critic notes this reveals a larger problem: resume duplicates orchestration logic instead of reusing it.

**Implementation:**
```python
# In orchestrator.py resume()
edge_map: dict[tuple[str, str], str] = {}
with self._db.engine.connect() as conn:
    edges = conn.execute(
        select(edges_table).where(edges_table.c.run_id == run_id)
    ).fetchall()

    for edge in edges:
        edge_map[(edge.from_node_id, edge.label)] = edge.edge_id
```

**Long-term architecture fix:** Unify run and resume paths to share edge registration logic.

---

### Bug #4: Type Degradation on Resume

**AGREED FIX: Option A (Make schema required)**

Both reviewers **strongly agree** schema must be required. Code Reviewer: "This is mandatory." Architecture Critic: "The optional parameter was a design mistake."

**Implementation:**
```python
def get_unprocessed_row_data(
    self,
    run_id: str,
    payload_store: PayloadStore,
    *,
    source_schema_class: type[PluginSchema],  # REQUIRED, not Optional
) -> list[dict[str, Any]]:
    """Get unprocessed row data with type restoration.

    Args:
        source_schema_class: Schema for type restoration. REQUIRED.
            Resume cannot guarantee type fidelity without schema validation.

    Raises:
        ValueError: If schema validation fails
    """
    # Remove if/else - always validate
    validated = source_schema_class.model_validate(degraded_data)
    return validated.to_row()
```

**Breaking change handling:**
```python
# In orchestrator.py resume()
source_schema_class = getattr(config.source, "_schema_class", None)
if source_schema_class is None:
    raise ValueError(
        f"Source '{config.source.name}' does not provide schema class. "
        f"Resume requires type restoration. "
        f"Source plugin must set _schema_class attribute."
    )
```

**Consensus:** Breaking change is acceptable per CLAUDE.md RC policy.

---

### Bug #5: Transaction Rollback

**AGREED FIX: Merged with Bug #1**

Both reviewers agree this is automatically fixed by switching to `begin()` in Bug #1 fix.

**Additional:** Code Reviewer notes `delete_checkpoints()` also uses `connect()` - should use `begin()` for consistency.

---

### Bug #6: Aggregation Timeout Reset

**AGREED FIX: Store elapsed time, not monotonic timestamp**

Code Reviewer identified critical issue: `time.monotonic()` is relative to process start, so restored value is meaningless across processes.

**Correct Implementation:**
```python
# In get_checkpoint_state()
state[node_id] = {
    "tokens": [...],
    "batch_id": batch.batch_id,
    "elapsed_age_seconds": evaluator.get_age_seconds(),  # Store elapsed time
}

# In restore_from_checkpoint()
elapsed_seconds = state.get("elapsed_age_seconds", 0.0)
evaluator._first_accept_time = time.monotonic() - elapsed_seconds
```

**Alternative (Architecture Critic suggestion):** Store deadline timestamp instead of elapsed time.

---

### Bug #7: Schema Allows NULL

**AGREED FIX: Add nullable=False**

Both reviewers agree. Requires Alembic migration.

---

### Bug #8: Resume Early Exit Cleanup

**AGREED FIX: Add _delete_checkpoints() call**

Both reviewers agree this is straightforward.

---

### Bug #9: Missing Graph Validation

**AGREED FIX: Add parameter validation**

Code Reviewer recommends validating both graph and node_id at function start.

---

## Consensus: Revised Priority

| Priority | Bugs | Week | Rationale |
|----------|------|------|-----------|
| **P0** | #1, #2 (with gaps), #5, #10 (callback error) | Week 1 | Data loss + audit corruption |
| **P1** | #3, #4, #11 | Week 2 | Resume crashes + type safety |
| **P2** | #6, #7, #8, #12 | Week 3 | SLA + schema + cleanup + versioning |
| **P3** | #9 | Week 4 | Parameter validation |

**Key changes from original:**
- Added Bug #10 (checkpoint callback errors) to P0
- Added Bug #12 (version validation) to P2
- Moved Bug #5 to P0 (merged with #1)
- Added Bug #11 to P1

---

## Consensus: Testing Requirements

### Critical Tests (P0)

1. **Crash simulation for Bug #2**
   ```python
   def test_checkpoint_after_sink_crash():
       """Verify checkpoint not created if sink flush fails."""
       # Mock os.fsync() to raise IOError
       # Verify no checkpoint exists
       # Verify resume processes row again
   ```

2. **Concurrent checkpoint creation for Bug #1**
   ```python
   def test_concurrent_checkpoint_race():
       """Verify topology hash matches graph at checkpoint time."""
       # Create checkpoint
       # Modify graph
       # Verify checkpoint has original hash (not modified graph)
   ```

3. **Checkpoint callback error for Bug #10**
   ```python
   def test_checkpoint_callback_failure_after_flush():
       """Verify sink write is not lost if checkpoint fails."""
       # Write to sink successfully
       # Mock checkpoint to fail
       # Verify sink artifact exists
       # Verify error logged, not raised
   ```

### Property-Based Tests (Recommended by Code Reviewer)

```python
from hypothesis import given, strategies as st

@given(
    num_rows=st.integers(min_value=1, max_value=1000),
    checkpoint_at=st.integers(min_value=0, max_value=999),
)
def test_resume_processes_exact_remaining_rows(num_rows, checkpoint_at):
    """Verify resume processes exactly (num_rows - checkpoint_at) rows."""
    # Run with num_rows, checkpoint at checkpoint_at
    # Crash and resume
    # Assert: resumed rows == num_rows - checkpoint_at
```

### Integration Test Scenarios

1. Resume after crash during sink write
2. Resume with modified graph (should reject)
3. Resume with gates (verify real edge IDs)
4. Resume with aggregations near timeout
5. Partial batch failure (verify duplicate handling)

---

## Consensus: Implementation Order

### Week 1: P0 Fixes (Data Loss Prevention)

**Day 1-2: Bug #1 + #5 (Transaction atomicity)**
- Move hash computation inside `begin()` transaction
- Add graph/node validation
- Fix `delete_checkpoints()` to use `begin()`

**Day 3-4: Bug #2 (Sink durability)**
- Add `SinkProtocol.flush()` method
- Implement `flush()` in CSVSink (with `fsync`)
- Implement `flush()` in DatabaseSink (with `commit`)
- Call `flush()` before checkpoint callback

**Day 5: Bug #10 (Checkpoint callback errors)**
- Add try/except around checkpoint callback
- Log errors without raising
- Write integration test

### Week 2: P1 Fixes (Resume Correctness)

**Day 1: Bug #3 (Edge IDs)**
- Load real edge IDs from database in resume path
- Remove synthetic ID generation

**Day 2-3: Bug #4 + #11 (Type fidelity)**
- Make `source_schema_class` required (breaking change)
- Update type annotations to `type[PluginSchema]`
- Update all resume callers to provide schema
- Add early validation in orchestrator

### Week 3: P2 Fixes (Robustness)

**Day 1: Bug #6 (Timeout restoration)**
- Store `elapsed_age_seconds` in checkpoint
- Restore with adjusted `first_accept_time`

**Day 2: Bug #7 (Schema constraints)**
- Alembic migration for `nullable=False`
- Test migration on existing DBs

**Day 3: Bug #8 (Cleanup)**
- Add `_delete_checkpoints()` to early-exit path

**Day 4: Bug #12 (Version validation)**
- Add `_version` field to checkpoint state
- Validate version on restore

### Week 4: P3 Fixes (Polish)

**Day 1: Bug #9 (Validation)**
- Add parameter validation to `create_checkpoint()`

---

## Consensus: Known Limitations (Document for RC-1)

Both reviewers agree these are acceptable to defer post-RC:

1. **Partial batch failure creates duplicates** (Bug #10 scenario)
   - Sinks are not atomic at batch boundaries
   - Crash mid-batch → some rows written, resume replays all → duplicates
   - **Mitigation:** Document limitation, plan atomic sinks for post-RC

2. **Checkpoint granularity trade-off**
   - Batch-level checkpointing may affect `explain()` row-level queries
   - **Action:** Verify explain() doesn't require row-level precision
   - If required: consider checkpointing last row in batch (still batch-flush)

3. **Resume path code duplication**
   - Resume duplicates orchestration logic instead of reusing it
   - Creates maintenance burden (Bug #3 is symptom)
   - **Refactor:** Post-RC, unify run and resume paths

---

## Consensus: Sign-off

✅ **Code Reviewer (axiom-python-engineering):**
- "The report is excellent work. Fix the durability gap (`fsync`) and error handling, and this will be production-ready."
- **Grade:** A- (Excellent with minor gaps)
- **Confidence:** HIGH (90%)

✅ **Architecture Critic (axiom-system-architect):**
- "The bug report is technically accurate and the recommended fixes are mostly correct. The significant gap is that Bug #2 requires a protocol-level change (sink durability contract)."
- **Assessment:** APPROVED WITH AMENDMENTS
- **Confidence:** HIGH (80%)

---

## Next Steps

1. ✅ Review consensus approved by both experts
2. ⏭️ Implement P0 fixes (Week 1)
3. ⏭️ Write comprehensive tests (parallel with implementation)
4. ⏭️ Create Alembic migration for schema changes
5. ⏭️ Update documentation with known limitations
6. ⏭️ Plan post-RC refactoring (resume path unification)

---

## Appendix: Expert Review Summaries

### Code Reviewer Key Findings
- Found 3 additional bugs (#10, #11, #12)
- Identified critical `os.fsync()` gap
- Recommended property-based testing with Hypothesis
- Noted partial batch failure scenario
- Confirmed all fix options are technically sound

### Architecture Critic Key Findings
- Identified missing sink durability contract (architectural)
- Noted resume path code duplication (systemic)
- Clarified Bug #1 is about crash consistency, not concurrency
- Recommended protocol-level fixes over implementation patches
- Confirmed alignment with CLAUDE.md principles

### Areas of Agreement
- All 9 bugs are real and correctly diagnosed
- Priority ordering is accurate
- Option A fixes are generally correct
- Testing strategy needs enhancement
- Breaking changes acceptable for RC-1

### Areas of Refinement
- Bug #2 needs protocol change, not just implementation fix
- Bug #6 needs elapsed time storage, not monotonic timestamp
- Batch-level checkpointing trade-off needs verification
- Additional bugs found require priority adjustment
