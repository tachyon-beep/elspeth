# Analysis: src/elspeth/core/landscape/reproducibility.py

**Lines:** 155
**Role:** Computes and manages the `reproducibility_grade` field on the runs table, indicating how reliably a run can be reproduced or replayed. Provides three operations: compute grade from node determinism, set grade on a run, and degrade grade after payload purge.
**Key dependencies:** Imports `Determinism` enum from `elspeth.contracts`, `nodes_table`/`runs_table` from landscape schema, and `LandscapeDB` for database access. Imported by `elspeth.core.retention.purge` (for post-purge grade degradation) and `elspeth.core.landscape.recorder` (for grade computation at run completion).
**Analysis depth:** FULL

## Summary

This module is well-structured with correct Tier 1 validation patterns. The primary concern is a race condition in `update_grade_after_purge()` where the read-modify-write pattern on the reproducibility grade is not protected against concurrent access. The grade computation logic is sound and correctly maps determinism values to reproducibility levels. Confidence is high that the module is correct for single-writer scenarios.

## Warnings

### [126-154] Read-modify-write race condition in update_grade_after_purge

**What:** The `update_grade_after_purge()` function performs a read-modify-write cycle: it reads the current grade (line 127-128), checks the value (line 149), and conditionally writes a new grade (line 150-153). While this happens within a single `db.connection()` context manager, `LandscapeDB.connection()` uses `engine.begin()` which provides transactional atomicity but does NOT acquire a row lock. If two purge operations run concurrently for the same run_id, both could read `REPLAY_REPRODUCIBLE`, both decide to update, and both write `ATTRIBUTABLE_ONLY`. In this specific case the end result is correct (both write the same value), but the pattern itself is fragile -- if grade degradation ever becomes more complex (e.g., multi-step degradation), this would become a real data integrity bug.

**Why it matters:** For SQLite this is unlikely to cause issues (WAL mode with file-level locking), but for PostgreSQL production deployments, concurrent purge operations on the same run could theoretically interleave. The current logic is safe because the degradation is idempotent (REPLAY -> ATTRIBUTABLE is the only transition), but the pattern is a landmine for future changes.

**Evidence:**
```python
with db.connection() as conn:
    result = conn.execute(query)  # READ
    row = result.fetchone()
    # ... validation ...
    if grade_enum == ReproducibilityGrade.REPLAY_REPRODUCIBLE:
        conn.execute(  # WRITE
            runs_table.update()...
        )
```
No `SELECT ... FOR UPDATE` or equivalent row lock is acquired between read and write.

### [130-131] Silent no-op when run doesn't exist in update_grade_after_purge

**What:** When `row is None` (run not found), the function silently returns without any logging or error. The caller (`PurgeManager`) iterates over `affected_run_ids` and calls this for each. If a run_id somehow ended up in the affected set but doesn't exist in the runs table, this discrepancy between the purge records (which reference run_id) and the runs table would be silently ignored.

**Why it matters:** Per the Data Manifesto, this is Tier 1 audit data. If we purged payloads for a run that doesn't exist in the runs table, that's a data integrity anomaly that should at minimum be logged. In an emergency dispatch system, silent discrepancies in the audit trail could be dangerous during forensic investigation.

**Evidence:**
```python
if row is None:
    return  # Run doesn't exist -- no log, no error
```

## Observations

### [62] Query uses nodes_table.c.run_id correctly

The query correctly filters by `run_id` on the `nodes_table` using the composite primary key pattern. This avoids the documented composite primary key pitfall where `node_id` alone could match across multiple runs.

### [82-87] Non-reproducible set is hardcoded but matches Determinism enum

The set of non-reproducible determinism values is explicitly listed rather than derived from the enum. If a new `Determinism` value were added (e.g., `HARDWARE_DEPENDENT`), this set would need manual updating. However, given that `Determinism` is a core audit enum that changes rarely and is tested extensively, this is acceptable. A comment noting the relationship would aid maintainability.

### [46-47] FULL_REPRODUCIBLE returned for empty pipeline (no nodes)

An empty pipeline (no nodes for a run) returns `FULL_REPRODUCIBLE`, which is documented and correct -- a pipeline with no transforms is trivially reproducible. However, this could mask a bug where nodes weren't registered properly. Since node registration is validated elsewhere, this is acceptable.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The read-modify-write race condition in `update_grade_after_purge` should use `SELECT ... FOR UPDATE` (or equivalent) for PostgreSQL deployments. The silent no-op when a run doesn't exist should at minimum log a warning. Neither is an emergency, but both should be addressed before production deployment with concurrent purge operations.
**Confidence:** HIGH -- The module is small, well-documented, and follows established patterns. The race condition assessment is based on clear analysis of the transactional semantics.
