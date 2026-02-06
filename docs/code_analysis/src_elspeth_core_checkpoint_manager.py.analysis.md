# Analysis: src/elspeth/core/checkpoint/manager.py

**Lines:** 252
**Role:** Manages checkpoint creation, retrieval, deletion, and compatibility validation. Checkpoints capture pipeline progress at row/transform boundaries for crash recovery. Each checkpoint records the current token, node, sequence number, topology hash, and optional aggregation state.
**Key dependencies:** Imports `Checkpoint` contract from `elspeth.contracts`, `compute_full_topology_hash`/`stable_hash` from `elspeth.core.canonical`, `checkpoint_dumps` from checkpoint serialization, `LandscapeDB` and `checkpoints_table` from landscape. Imported by `elspeth.core.checkpoint.recovery`, `elspeth.cli`, and `elspeth.engine.orchestrator`.
**Analysis depth:** FULL

## Summary

The CheckpointManager is well-structured with good atomicity practices (transaction-scoped checkpoint creation) and proper compatibility validation. The primary concern is a subtle atomicity gap where the returned `Checkpoint` object is constructed OUTSIDE the transaction, meaning if the process crashes between the database write and the return statement, the caller has no checkpoint object but the database has the record. There is also a minor concern about `get_checkpoints()` not validating compatibility, unlike `get_latest_checkpoint()`. Overall, the module is solid.

## Warnings

### [86-135] Checkpoint object constructed outside transaction boundary

**What:** The `create_checkpoint` method writes to the database inside a `with self._db.engine.begin() as conn:` transaction block (lines 86-121), then constructs and returns the `Checkpoint` dataclass OUTSIDE the transaction (lines 124-135). If the process crashes after the database commit but before the `Checkpoint` object is returned to the caller, the checkpoint exists in the database but the caller doesn't know about it. On resume, the checkpoint will be found and used, so this is not a data loss issue. However, the caller may have stale state about what was checkpointed.

**Why it matters:** In practice, this is very unlikely to cause issues because:
1. Resume always reads from the database, not from the in-memory object
2. The crash window is microseconds

However, the pattern is noteworthy because the variables (`checkpoint_id`, `created_at`, etc.) are defined inside the transaction scope and used outside it. If Python's variable scoping were different, this would be a bug. As-is, Python's function-scoped variables make this safe.

**Evidence:**
```python
with self._db.engine.begin() as conn:
    checkpoint_id = f"cp-{uuid.uuid4().hex}"
    created_at = datetime.now(UTC)
    # ... database insert ...

# Outside transaction scope, but variables still accessible
return Checkpoint(
    checkpoint_id=checkpoint_id,
    # ...
)
```

### [178-206] get_checkpoints() does not validate compatibility

**What:** The `get_checkpoints()` method returns ALL checkpoints for a run without calling `_validate_checkpoint_compatibility()`. In contrast, `get_latest_checkpoint()` (line 174) validates compatibility before returning. This means callers of `get_checkpoints()` could receive incompatible checkpoints that would fail if used for resume.

**Why it matters:** If any code path uses `get_checkpoints()` to select a checkpoint for resume (e.g., selecting a specific checkpoint rather than the latest), it would bypass the version compatibility check. Currently, the only caller pattern appears to be diagnostic/display use, but this is a latent risk. The inconsistency between the two retrieval methods is a maintenance hazard.

**Evidence:**
```python
def get_latest_checkpoint(self, run_id: str) -> Checkpoint | None:
    # ... fetch ...
    self._validate_checkpoint_compatibility(checkpoint)  # Validates!
    return checkpoint

def get_checkpoints(self, run_id: str) -> list[Checkpoint]:
    # ... fetch ...
    return [Checkpoint(...) for r in results]  # No validation!
```

### [149] get_latest_checkpoint uses engine.connect() (read-only) while create uses engine.begin()

**What:** `get_latest_checkpoint()` uses `self._db.engine.connect()` (line 149) which provides a read-only connection without auto-commit transaction semantics, while `create_checkpoint()` uses `self._db.engine.begin()` (line 86) for write transactions. This is technically correct -- reads don't need transaction commits -- but it creates an inconsistency where `get_latest_checkpoint()` doesn't participate in the same transactional semantics as writes. For SQLite WAL mode this is fine; for PostgreSQL with concurrent writers, a read outside a transaction could see an intermediate state.

**Why it matters:** If a checkpoint is being written concurrently (rare but possible in recovery scenarios), the read could see a partially-committed row on PostgreSQL. Given that checkpoint operations are typically serialized by the orchestrator, this is low risk.

**Evidence:**
```python
def get_latest_checkpoint(self, run_id: str) -> Checkpoint | None:
    with self._db.engine.connect() as conn:  # read-only
        result = conn.execute(...)

def create_checkpoint(self, ...):
    with self._db.engine.begin() as conn:  # transactional
        conn.execute(...)
```

## Observations

### [79-83] Early parameter validation is correct

The method validates both `graph is not None` and `graph.has_node(node_id)` before entering the transaction. This prevents wasted database connections for invalid inputs.

### [99-106] Full topology hash (BUG-COMPAT-01 fix) is well-documented

The comment explains why full topology hashing replaced upstream-only hashing, with a clear reference to the bug that motivated the change. The `compute_full_topology_hash` function correctly hashes all nodes and edges.

### [237-251] Compatibility validation rejects both older AND newer versions

The version check on line 245 uses `!=` rather than `<`, meaning checkpoints from NEWER format versions are also rejected. This is correct -- cross-version resume is unsafe in both directions. The error messages are actionable ("Please restart pipeline from beginning").

### [88] Checkpoint ID format uses UUID hex without dashes

`f"cp-{uuid.uuid4().hex}"` produces IDs like `cp-a1b2c3d4...` (34 chars total: 2 prefix + 32 hex). This fits within the 64-char `checkpoint_id` column limit in the schema.

### [219-222] delete_checkpoints returns rowcount

The method correctly returns the number of deleted rows, allowing callers to verify cleanup happened. The transaction semantics are correct for bulk deletion.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The `get_checkpoints()` method should either validate compatibility for each checkpoint (consistent with `get_latest_checkpoint()`) or be clearly documented as returning raw/unvalidated checkpoints. The transaction boundary concern is informational and does not require immediate action.
**Confidence:** HIGH -- The module is well-documented, follows established patterns, and the identified issues are clear and verifiable.
