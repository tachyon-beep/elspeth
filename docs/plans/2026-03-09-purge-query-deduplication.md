# Purge Query Deduplication Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate 8 near-identical query pairs in `find_expired_payload_refs` by extracting a shared helper method.

**Architecture:** Extract a `_build_ref_union_query(run_condition, ...)` method that builds the 8 sub-queries (row, operation input/output, call-state request/response, call-op request/response, routing) for a given run condition. The existing method calls it twice — once with `run_expired_condition`, once with `run_active_condition`. Pure refactoring; no behavioral change.

**Tech Stack:** SQLAlchemy Core (select, join, union, and_, or_)

**Filigree issue:** `elspeth-5cfe3615b6`

**Key safety notes for the implementer:**
- This is a **pure refactoring** — no behavioral change. The public interface of `PurgeManager` is unchanged.
- SQLAlchemy `FromClause` join objects are **immutable clause elements**. Reusing the same join object in multiple `select_from()` calls is safe — each produces an independent `Select`. The original code already does this (e.g. `call_state_join` defined once, used in both expired and active blocks).
- The helper's keyword-only parameters (`*` separator) are deliberate — these joins have no meaningful positional order and swapping `call_state_join`/`call_op_join` would silently produce wrong SQL.
- Pass keyword arguments **directly** at both call sites (not via `dict(**kwargs)`). Direct arguments give mypy full visibility into the keyword-only contract.
- `_find_affected_run_ids_chunk` (lines 328+) has similar-looking duplication but a **different query shape** (IN-clause filtering by refs, not run-condition joins). It is intentionally out of scope.
- The `nodes` table has a **composite PK** `(node_id, run_id)`. All joins through `node_states` must use `node_states.run_id` directly (denormalized column), never join through `nodes` on `node_id` alone. The existing code and this refactoring both follow this pattern — preserve it.

---

### Task 1: Extract `_build_ref_union_query` helper and replace duplicated blocks

This is a single-commit refactoring. The existing tests are comprehensive and cover all ref types, the expired/active distinction, shared refs, and edge cases. No new tests are needed — the existing suite is the regression safety net.

**Files:**
- Modify: `src/elspeth/core/retention/purge.py:122-275`

**Step 1: Verify existing tests pass before touching anything**

Run: `.venv/bin/python -m pytest tests/unit/core/retention/test_purge.py -v`
Expected: All tests PASS

**Step 2: Add the helper method to `PurgeManager`**

Add this method to the class, before `find_expired_payload_refs`:

```python
def _build_ref_union_query(
    self,
    run_condition: ColumnElement[bool],
    *,
    rows_join: FromClause,
    operation_join: FromClause,
    call_state_join: FromClause,
    call_op_join: FromClause,
    routing_join: FromClause,
) -> CompoundSelect:
    """Build a UNION of all 8 payload ref sub-queries for a given run condition.

    Each sub-query selects a single ref column from a different table/join,
    filtered by the run condition and a NOT NULL guard on the ref column.

    Args:
        run_condition: SQLAlchemy WHERE clause for run filtering
            (e.g. expired condition or active condition)
        rows_join: Pre-built join for rows → runs
        operation_join: Pre-built join for operations → runs
        call_state_join: Pre-built join for calls → node_states → runs
        call_op_join: Pre-built join for calls → operations → runs
        routing_join: Pre-built join for routing_events → node_states → runs

    Returns:
        UNION of all 8 sub-queries
    """
    return union(
        # 1. Row payloads
        select(rows_table.c.source_data_ref)
        .select_from(rows_join)
        .where(and_(run_condition, rows_table.c.source_data_ref.isnot(None))),
        # 2. Operation input payloads
        select(operations_table.c.input_data_ref)
        .select_from(operation_join)
        .where(and_(run_condition, operations_table.c.input_data_ref.isnot(None))),
        # 3. Operation output payloads
        select(operations_table.c.output_data_ref)
        .select_from(operation_join)
        .where(and_(run_condition, operations_table.c.output_data_ref.isnot(None))),
        # 4. Call request payloads (transform calls via state_id)
        select(calls_table.c.request_ref)
        .select_from(call_state_join)
        .where(and_(run_condition, calls_table.c.request_ref.isnot(None))),
        # 5. Call response payloads (transform calls via state_id)
        select(calls_table.c.response_ref)
        .select_from(call_state_join)
        .where(and_(run_condition, calls_table.c.response_ref.isnot(None))),
        # 6. Call request payloads (source/sink calls via operation_id)
        select(calls_table.c.request_ref)
        .select_from(call_op_join)
        .where(and_(run_condition, calls_table.c.request_ref.isnot(None))),
        # 7. Call response payloads (source/sink calls via operation_id)
        select(calls_table.c.response_ref)
        .select_from(call_op_join)
        .where(and_(run_condition, calls_table.c.response_ref.isnot(None))),
        # 8. Routing reason payloads
        select(routing_events_table.c.reason_ref)
        .select_from(routing_join)
        .where(and_(run_condition, routing_events_table.c.reason_ref.isnot(None))),
    )
```

**Step 3: Replace the duplicated blocks in `find_expired_payload_refs`**

Replace lines 122-275 (the two `=== Build queries ...` blocks and the two `union()` calls) with:

```python
# === Build joins (shared between expired and active queries) ===
# NOTE: Use node_states.run_id directly (denormalized column) instead of
# joining through nodes table. The nodes table has composite PK (node_id, run_id),
# so joining on node_id alone would be ambiguous when node_id is reused across runs.
rows_join = rows_table.join(runs_table, rows_table.c.run_id == runs_table.c.run_id)
operation_join = operations_table.join(runs_table, operations_table.c.run_id == runs_table.c.run_id)
call_state_join = calls_table.join(
    node_states_table, calls_table.c.state_id == node_states_table.c.state_id
).join(runs_table, node_states_table.c.run_id == runs_table.c.run_id)
# XOR constraint: calls have either state_id OR operation_id, not both
call_op_join = calls_table.join(
    operations_table, calls_table.c.operation_id == operations_table.c.operation_id
).join(runs_table, operations_table.c.run_id == runs_table.c.run_id)
routing_join = routing_events_table.join(
    node_states_table, routing_events_table.c.state_id == node_states_table.c.state_id
).join(runs_table, node_states_table.c.run_id == runs_table.c.run_id)

expired_refs_query = self._build_ref_union_query(
    run_expired_condition,
    rows_join=rows_join,
    operation_join=operation_join,
    call_state_join=call_state_join,
    call_op_join=call_op_join,
    routing_join=routing_join,
)
active_refs_query = self._build_ref_union_query(
    run_active_condition,
    rows_join=rows_join,
    operation_join=operation_join,
    call_state_join=call_state_join,
    call_op_join=call_op_join,
    routing_join=routing_join,
)
```

**Step 4: Update imports**

Add the three new type imports to the existing SQLAlchemy import line (line 14):

```python
from sqlalchemy import ColumnElement, CompoundSelect, FromClause, and_, or_, select, union
```

**Step 5: Run all purge tests to verify no behavioral change**

Run: `.venv/bin/python -m pytest tests/unit/core/retention/test_purge.py -v`
Expected: All tests PASS (identical results to Step 1)

**Step 6: Run the broader test suites that exercise purge**

Run: `.venv/bin/python -m pytest tests/property/core/test_retention_monotonicity.py tests/unit/cli/test_purge_command.py -v`
Expected: All PASS

**Step 7: Run type checking**

Run: `.venv/bin/python -m mypy src/elspeth/core/retention/purge.py`
Expected: No errors

**Step 8: Run linting**

Run: `.venv/bin/python -m ruff check src/elspeth/core/retention/purge.py`
Expected: No errors

**Step 9: Commit**

```bash
git add src/elspeth/core/retention/purge.py
git commit -m "$(cat <<'EOF'
(refactor) Extract _build_ref_union_query — deduplicate 8 near-identical query pairs in find_expired_payload_refs

The expired-refs and active-refs query blocks were structurally identical
across 8 sub-query pairs (16 total queries), differing only in the WHERE
condition. Extracted a shared helper that takes the run condition and
pre-built join objects, called twice.

Note: _find_affected_run_ids_chunk has similar-looking duplication but a
different query shape (IN-clause filtering by refs, not run-condition joins)
and is intentionally not covered by this helper.
EOF
)"
```

### Task 2: Close the Filigree issue

Close `elspeth-5cfe3615b6` with a reason referencing the commit.
