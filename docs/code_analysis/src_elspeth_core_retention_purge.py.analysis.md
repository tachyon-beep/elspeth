# Analysis: src/elspeth/core/retention/purge.py

**Lines:** 443
**Role:** Payload purge policies -- identifies payloads eligible for deletion based on retention period, deletes blobs from PayloadStore while preserving hashes in the Landscape audit trail. Supports content-addressable deduplication awareness (won't delete a ref that's still needed by an active run). Updates reproducibility grades after purge.
**Key dependencies:** SQLAlchemy (`select`, `and_`, `or_`, `union`), landscape schema tables (`calls_table`, `node_states_table`, `operations_table`, `routing_events_table`, `rows_table`, `runs_table`), `PayloadStore` protocol, `update_grade_after_purge`. Imported by `src/elspeth/cli.py`, `src/elspeth/core/retention/__init__.py`, and tests.
**Analysis depth:** FULL

## Summary

This is security-relevant code that manages data retention for the audit trail. The core logic is sound -- the content-addressable deduplication awareness (computing set difference between expired and active refs) is correctly implemented. The SQL queries correctly use denormalized `node_states.run_id` per the composite PK pattern documented in CLAUDE.md. There are two warning-level findings: a TOCTOU race in the `exists()`/`delete()` purge loop, and a potential performance concern with large ref lists in SQL `IN` clauses. There is also one critical finding related to the `find_expired_payload_refs` method reusing join objects across expired and active queries, which could produce incorrect results.

## Critical Findings

### [174-176, 210-211] Reuse of join objects across expired and active queries

**What:** The `call_state_join` object (line 174) and `routing_join` object (line 210) are constructed once and reused for BOTH expired and active queries. The expired queries use `run_expired_condition` on lines 181-187, and the active queries use `run_active_condition` on lines 241-249. Both query sets join to `runs_table` through the same join object.

SQLAlchemy join objects are stateless path descriptions -- they describe the table relationship, not a filtered subset. So `call_state_join` is simply:
```
calls -> node_states -> runs
```
Both expired and active queries apply different WHERE conditions. This is actually correct because the join describes the relationship path, and the WHERE clause filters the results.

**Correction:** After careful analysis, this is NOT a bug. SQLAlchemy's `select().select_from(join).where(condition)` applies the WHERE clause independently of the join definition. The join just establishes the table relationships. The expired and active conditions filter correctly. Downgrading from Critical.

## Warnings

### [399-423] TOCTOU race between exists() and delete() in purge loop

**What:** The purge loop calls `self._payload_store.exists(ref)` and then `self._payload_store.delete(ref)` as separate operations. Between the existence check and the delete, another process (concurrent purge, manual cleanup) could delete the file.
**Why it matters:** If the file is deleted between `exists()` and `delete()`:
1. `exists()` returns `True`
2. Another process deletes the file
3. `delete()` returns `False` (file not found)
4. The ref is added to `failed_refs` even though the payload IS gone

This means the `PurgeResult` could report false failures. More importantly, the `_find_affected_run_ids` call at line 427 uses `deleted_refs`, which would NOT include this ref. The reproducibility grade would not be updated for the affected run, even though the payload is gone. A subsequent purge run would see the ref as "skipped" (doesn't exist), and the grade would never be corrected.

**Evidence:**
```python
exists = self._payload_store.exists(ref)     # True
# ... another process deletes ref here ...
if exists:
    deleted = self._payload_store.delete(ref)  # Returns False
    if deleted:
        deleted_count += 1
        deleted_refs.append(ref)
    else:
        failed_refs.append(ref)  # Incorrectly classified as failure
```

The `FilesystemPayloadStore.delete()` method also has its own internal TOCTOU between `path.exists()` and `path.unlink()`, but that would raise `FileNotFoundError` (subclass of `OSError`), which IS caught by the `except OSError` at line 410. So the outer TOCTOU resolves to a caught exception -> `failed_refs`, which is the wrong bucket for "already deleted by someone else."

**Impact:** In practice, concurrent purge operations are unlikely in the current single-process CLI model. But if ELSPETH is ever deployed with scheduled purge jobs (cron, background workers), this race becomes real.

### [288-299] In-memory set difference assumes small result sets

**What:** The comment on lines 283-286 explains the design choice: Python set difference is used instead of SQL EXCEPT because "result sets are typically small enough for in-memory operation." Both `expired_refs` and `active_refs` are loaded entirely into memory as Python sets.
**Why it matters:** For a system with millions of rows across many runs, each with source_data_ref, request_ref, response_ref, and reason_ref, the total number of unique payload refs could be very large. Loading all of them into memory could cause OOM in constrained environments (containers with memory limits).
**Evidence:**
```python
with self._db.connection() as conn:
    expired_result = conn.execute(expired_refs_query)
    expired_refs = {row[0] for row in expired_result}    # Unbounded size
    active_result = conn.execute(active_refs_query)
    active_refs = {row[0] for row in active_result}      # Unbounded size

safe_to_delete = expired_refs - active_refs
```
**Mitigating factor:** Content-addressable deduplication means identical payloads share one ref. In practice, the number of unique refs is bounded by the number of unique payloads, not the number of rows referencing them. The DISTINCT in the UNION also helps. This is likely acceptable for the current scale but should be monitored.

### [321] SQL IN clause with large refs_set

**What:** `_find_affected_run_ids` uses `.in_(refs_set)` in multiple queries. SQLite has a limit on the number of parameters in a query (default SQLITE_MAX_VARIABLE_NUMBER = 999 in older versions, 32766 in newer). If `refs_set` is very large, this could hit the limit.
**Why it matters:** A large purge (thousands of refs) could cause an `OperationalError` from SQLite. The method would fail after payloads are already deleted (step 1 in `purge_payloads` runs before step 2), leaving reproducibility grades un-updated.
**Evidence:**
```python
row_runs_query = select(rows_table.c.run_id).distinct().where(
    rows_table.c.source_data_ref.in_(refs_set)  # refs_set could be very large
)
```
**Mitigating factor:** Modern SQLite (3.32.0+, 2020) increased the default limit to 32766. Python 3.12+ ships with SQLite 3.44+. This is only a concern for deployments with older SQLite versions or extremely large purge batches.

### [399] Sequential single-ref deletion is O(N) with no batching

**What:** The purge loop deletes one ref at a time in a Python for-loop. For each ref, it does an `exists()` call and potentially a `delete()` call. For filesystem-backed stores, each call involves filesystem I/O (stat + unlink).
**Why it matters:** For large purges (thousands of refs), this is slow. There's no batching, parallelization, or progress reporting. A large purge operation could appear to hang.
**Evidence:**
```python
for ref in refs:
    try:
        exists = self._payload_store.exists(ref)
    except OSError:
        failed_refs.append(ref)
        continue
    if exists:
        try:
            deleted = self._payload_store.delete(ref)
        # ...
```

## Observations

### [92-104] find_expired_row_payloads vs find_expired_payload_refs overlap

**What:** `find_expired_row_payloads` (line 65) only finds row-level `source_data_ref` payloads. `find_expired_payload_refs` (line 112) finds ALL payload types (rows, calls, routing). The older method is still used by tests and the CLI's `purge` command for backward compatibility with the simpler use case.
**Why it matters:** Two code paths for finding expired refs could diverge. If a new payload reference column is added, it needs to be added to `find_expired_payload_refs` but might be missed. A comment or deprecation note on `find_expired_row_payloads` would clarify the relationship.

### [144-159] Active run condition is comprehensive

**What:** The `run_active_condition` correctly identifies active runs as:
- `completed_at >= cutoff` (recent, within retention period)
- `completed_at IS NULL` (still running)
- `status == "running"` (explicitly running)

The third condition is redundant with the second (running runs have `completed_at IS NULL`), but the explicit check on status makes the intent clear and guards against edge cases where `completed_at` is set before `status` is updated.

### [368-443] purge_payloads correctly separates delete tracking from grade updates

**What:** The method tracks `deleted_refs` (actually deleted) separately from `failed_refs` (delete failed) and only updates reproducibility grades for runs affected by successfully deleted refs. This prevents grade downgrade when payloads still exist due to delete failures.
**Why it matters:** Correct. If grade were downgraded on failed deletes, the audit trail would claim payloads are gone when they're not.

### [170-228] Correct composite PK awareness for node_states joins

**What:** All joins through `node_states` use the denormalized `run_id` column directly rather than joining through the `nodes` table. The comments reference the composite PK pattern documented in CLAUDE.md.
**Why it matters:** This avoids the ambiguous join bug described in CLAUDE.md where `node_id` is reused across runs. The code correctly applies `node_states.run_id` for run isolation.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The TOCTOU race (warning #1) should be documented and either accepted as a known limitation or mitigated by changing the purge loop to use `delete()` directly without a prior `exists()` check (since `delete()` already returns False when the ref doesn't exist). The SQL IN clause size limit (warning #3) should be addressed with batching for large purge operations. The sequential deletion performance (warning #4) should be documented as a known limitation with guidance on purge batch sizes.
**Confidence:** HIGH -- The SQL queries are correctly constructed and the content-addressable deduplication awareness is sound. The warnings are real but impact future scale rather than current correctness. The TOCTOU finding has a concrete (if unlikely) misclassification consequence.
