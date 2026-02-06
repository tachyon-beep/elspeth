# Analysis: src/elspeth/core/checkpoint/recovery.py

**Lines:** 472
**Role:** Recovery protocol for resuming failed runs from checkpoint state. Provides the API for determining if a run can be resumed (`can_resume`), getting the resume point (`get_resume_point`), identifying unprocessed rows (`get_unprocessed_rows`), and retrieving their data with type fidelity restoration (`get_unprocessed_row_data`).
**Key dependencies:** Imports `CheckpointCompatibilityValidator`, `CheckpointManager`, `LandscapeRecorder`, `checkpoint_loads`, and multiple landscape schema tables. Uses `PluginSchema` for type restoration and `PayloadStore` for row data retrieval. Imported by `elspeth.core.checkpoint.__init__` and used by `elspeth.engine.orchestrator.core`.
**Analysis depth:** FULL

## Summary

This is the most complex file in the analysis set and the most critical for data integrity during crash recovery. The SQL query for identifying unprocessed rows is sophisticated and addresses real-world edge cases (fork recovery, delegation markers, aggregation buffers). The primary concerns are: (1) a potential for duplicate rows in the unprocessed result due to the outer join producing multiple rows per row_id when a row has multiple tokens, (2) the N+1 database query pattern in `get_unprocessed_row_data`, and (3) defensive `.get()` calls on aggregation state that may hide structural corruption. The BUFFERED outcome is notably absent from the terminal outcomes list, which is correct behavior but creates a subtle interaction with the buffered_row_ids exclusion logic that warrants attention.

## Critical Findings

### [383-405] SQL query can return duplicate row_ids despite DISTINCT

**What:** The main query in `get_unprocessed_rows` joins `rows_table` to `tokens_table` via outer join, then applies a WHERE clause with three OR conditions. The `DISTINCT` on line 402 is applied to `(row_id, row_index)` pairs (line 384). While `row_index` is unique per `(run_id, row_id)`, the issue is more subtle: a row with multiple tokens (e.g., after a fork creates tokens A and B) could match Case 2 multiple times -- once for each non-terminal, non-delegation token. `DISTINCT` prevents duplicate `(row_id, row_index)` tuples, which is correct. However, if somehow the same `row_id` appeared with different `row_index` values (which the schema's unique constraint on `(run_id, row_index)` prevents for the same run), duplicates could appear. The `DISTINCT` protection is sufficient given the schema constraints, but the correctness relies on an implicit assumption that `row_id` is 1:1 with `row_index` within a run.

**Why it matters:** If duplicates were returned, `get_unprocessed_row_data` would process the same row twice, leading to duplicate outputs in the resumed run. For an emergency dispatch system, a duplicate dispatch could waste resources or cause confusion. The current code is correct due to schema constraints, but the correctness chain is fragile -- it depends on schema invariants that are not validated in this module.

**Evidence:**
```python
query = (
    select(rows_table.c.row_id, rows_table.c.row_index)
    .select_from(rows_table)
    .outerjoin(tokens_table, rows_table.c.row_id == tokens_table.c.row_id)
    # Multiple tokens per row means multiple joined rows
    .where(...)
    .order_by(rows_table.c.row_index)
    .distinct()  # Deduplicates (row_id, row_index) pairs
)
```

### [286-296] Defensive .get() on aggregation state structure may mask corruption

**What:** The code extracts buffered row IDs from checkpoint aggregation state using `node_state.get("tokens", [])` (line 292) and `token.get("row_id")` (line 294). Per CLAUDE.md, checkpoint data is Tier 1 (our data). The aggregation state structure is written by our own checkpoint serialization. Using `.get()` with defaults silently handles cases where the structure doesn't match the expected format, which could mask corruption.

**Why it matters:** If the aggregation state is corrupted (missing "tokens" key, or tokens without "row_id"), the `.get()` calls would silently return defaults, causing the buffered rows to be treated as unprocessed. This would lead to duplicate processing of rows that were already buffered -- the exact duplication that the P1-2026-02-05 fix was designed to prevent. A corrupted aggregation state should crash, not silently fall through.

**Evidence:**
```python
tokens = node_state.get("tokens", [])  # Should be direct access: node_state["tokens"]
for token in tokens:
    row_id = token.get("row_id")  # Should be direct access: token["row_id"]
    if row_id:  # Falsy check also hides empty string row_id
        buffered_row_ids.add(row_id)
```

Per the Data Manifesto: "Bad data in the audit trail = crash immediately." Checkpoint aggregation state is Tier 1 data that we wrote. If `node_state["tokens"]` is missing, that's a bug in our serialization code, not an expected condition to handle gracefully.

## Warnings

### [207-252] N+1 query pattern in get_unprocessed_row_data

**What:** The `get_unprocessed_row_data` method opens a single database connection (line 207) but executes a separate query for each unprocessed row_id (line 210-211), then a separate payload store retrieval (line 225), and schema validation (line 235). For N unprocessed rows, this is N database queries + N payload retrievals + N schema validations.

**Why it matters:** For small resumptions (a few unprocessed rows), this is fine. But if a pipeline crashed early and has thousands of unprocessed rows, this becomes a significant performance bottleneck. Each query round-trip adds latency, especially for PostgreSQL over network. The database queries could be batched with a single `WHERE row_id IN (...)` clause.

**Evidence:**
```python
for row_id in row_ids:
    row_result = conn.execute(
        select(rows_table.c.row_index, rows_table.c.source_data_ref)
        .where(rows_table.c.row_id == row_id)  # One query per row
    ).fetchone()
```

### [121-157] get_resume_point calls can_resume then re-fetches checkpoint

**What:** `get_resume_point` calls `self.can_resume(run_id, graph)` which internally calls `self._checkpoint_manager.get_latest_checkpoint(run_id)`. If `can_resume` returns True, `get_resume_point` then calls `self._checkpoint_manager.get_latest_checkpoint(run_id)` AGAIN on line 142. This is a double fetch of the same data.

**Why it matters:** This is a wasted database query. More importantly, there's a TOCTOU (time-of-check-time-of-use) window: between the `can_resume` check and the second `get_latest_checkpoint` call, a new checkpoint could theoretically be written (if the run was somehow still creating checkpoints), causing the resume to use a different checkpoint than the one that was validated. In practice, this is unlikely because the run must be in "failed" status to be resumable, and failed runs don't create new checkpoints. But the pattern is wasteful and introduces a theoretical inconsistency.

**Evidence:**
```python
def get_resume_point(self, run_id: str, graph: "ExecutionGraph") -> ResumePoint | None:
    check = self.can_resume(run_id, graph)  # Fetches checkpoint internally
    if not check.can_resume:
        return None
    checkpoint = self._checkpoint_manager.get_latest_checkpoint(run_id)  # Fetches again!
```

### [343-350] BUFFERED outcome is correctly excluded from terminal_outcome_values but interaction with buffered_row_ids is subtle

**What:** The `BUFFERED` outcome is not in `terminal_outcome_values` (lines 343-350), which means tokens with BUFFERED outcome will not be treated as "complete." This means rows with only BUFFERED tokens will appear in the unprocessed list (Case 2 or Case 3 would match). However, these rows are then filtered OUT by the `buffered_row_ids` exclusion on lines 409-410. The correctness depends on the aggregation state checkpoint containing ALL buffered row IDs.

**Why it matters:** If the aggregation state checkpoint is stale or incomplete (e.g., rows were buffered AFTER the last checkpoint but BEFORE the crash), those rows would appear as "unprocessed" (no terminal outcome) AND would NOT be in `buffered_row_ids` (not in checkpoint). They would be reprocessed from scratch, which is actually the correct behavior for rows buffered after the last checkpoint. The logic is correct but the reasoning chain is complex and not documented.

**Evidence:** The BUFFERED outcome has `is_terminal = False` per the enum, so `is_terminal == 1` filter in terminal_tokens/rows_with_terminal subqueries correctly excludes it.

### [428-471] verify_contract_integrity creates new LandscapeRecorder per call

**What:** `verify_contract_integrity` creates a new `LandscapeRecorder(self._db)` on line 446 every time it's called. `LandscapeRecorder` initialization may involve creating internal state (database operations helper, etc.). This is called from `can_resume`, which is called from `get_resume_point`, so it could be called multiple times per resume attempt.

**Why it matters:** This is a minor resource concern. More importantly, it suggests the `RecoveryManager` should either hold a reference to a `LandscapeRecorder` or receive one via dependency injection, rather than creating throwaway instances.

## Observations

### [99-103] IncompatibleCheckpointError correctly converted to ResumeCheck

The `can_resume` method catches `IncompatibleCheckpointError` from `get_latest_checkpoint` and converts it to a `ResumeCheck(can_resume=False, reason=...)`. This maintains the API contract (returns ResumeCheck, doesn't throw for expected conditions) while the underlying manager throws for format incompatibility.

### [238-248] Defense-in-depth for empty schema is valuable

The check on line 241 (`if degraded_data and not row_data`) catches a real failure mode where a wrong schema class (e.g., NullSourceSchema with no fields) would silently discard all row data. This is appropriate defensive programming at a trust boundary (schema validation could be misconfigured).

### [383-402] PostgreSQL DISTINCT/ORDER BY compatibility note

The comment on line 381-382 about PostgreSQL requiring ORDER BY columns in SELECT when using DISTINCT is correct and shows awareness of cross-database compatibility. The workaround (selecting both columns, extracting just row_id from results on line 405) is clean.

### [32-36] Re-exporting contracts from recovery module

The `__all__` re-exports `ResumeCheck` and `ResumePoint` from contracts for caller convenience. This is a reasonable pattern for the public API of the recovery subsystem.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The `.get()` calls on aggregation state (lines 292-295) should be replaced with direct key access per the Data Manifesto's Tier 1 trust model. The N+1 query pattern in `get_unprocessed_row_data` should be batched for performance. The double checkpoint fetch in `get_resume_point` should be refactored to pass the validated checkpoint through rather than re-fetching. These are not emergency fixes but should be addressed before production deployment where crash recovery reliability is paramount.
**Confidence:** HIGH -- The SQL query logic was analyzed in detail against the schema definitions, and the identified issues are concrete and verifiable. The BUFFERED outcome interaction was traced through the full code path.
