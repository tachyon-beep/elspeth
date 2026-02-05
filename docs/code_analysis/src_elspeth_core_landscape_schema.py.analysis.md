# Analysis: src/elspeth/core/landscape/schema.py

**Lines:** 506
**Role:** Defines all SQLAlchemy Core table definitions for the Landscape audit database. This is the physical schema for the entire audit trail -- runs, nodes, edges, rows, tokens, node states, external calls, operations, artifacts, routing events, batches, validation/transform errors, checkpoints, and secret resolutions. The `metadata` object is the shared registry used by `create_all()` and inspected by the validation logic in `database.py`.
**Key dependencies:** Imports only from `sqlalchemy`. Imported by `database.py` (for `metadata`), `recorder.py` (for all table objects), `__init__.py` (re-exports subset), `mcp/server.py`, `checkpoint/`, `retention/purge.py`, and `reproducibility.py`.
**Analysis depth:** FULL

## Summary

The schema is well-designed with comprehensive foreign key relationships, composite primary keys, and proper use of constraints (CHECK, UNIQUE, partial indexes). The main concerns are: (1) the `batch_members` table lacks a primary key, which is a schema design issue that can cause problems with some ORMs/tools and prevents individual row identification; (2) the `validation_errors` composite FK to `nodes` with a nullable `node_id` creates a semantic ambiguity in FK enforcement; and (3) inconsistent use of `ondelete` cascading across foreign keys -- most FKs have no cascade behavior defined, meaning some deletions (e.g., retention purge) could hit FK violations. No data corruption risks from the schema itself; the design correctly implements the audit integrity requirements.

## Critical Findings

### [353-361] `batch_members` table has no primary key

**What:** The `batch_members_table` is the only table in the schema without a primary key. It has two `UniqueConstraint` definitions (`batch_id, ordinal` and `batch_id, token_id`) but no `primary_key=True` on any column and no `PrimaryKeyConstraint`.

**Why it matters:** A table without a primary key has several consequences:
1. **SQLAlchemy Core will still create the table**, but tools that introspect the schema (Alembic, database GUIs, some BI tools) may behave unexpectedly.
2. **SQLite will use the implicit `rowid`** as the internal identifier, which is an implementation detail not a design choice.
3. **Row identification is ambiguous** -- there is no single canonical way to identify a specific row. The `(batch_id, token_id)` unique constraint acts as a natural key, but it is not formally declared as the primary key.
4. **Retention/purge operations** that need to delete specific batch members have no primary key to target.
5. **Database migration tools** (Alembic) may not generate correct migration scripts for tables without explicit PKs.

This matters for audit integrity because batch membership is part of the aggregation audit trail. Being unable to uniquely and canonically reference a batch member row weakens traceability.

**Evidence:**
```python
batch_members_table = Table(
    "batch_members",
    metadata,
    Column("batch_id", String(64), ForeignKey("batches.batch_id"), nullable=False),
    Column("token_id", String(64), ForeignKey("tokens.token_id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    UniqueConstraint("batch_id", "ordinal"),
    UniqueConstraint("batch_id", "token_id"),  # Prevent duplicate token in same batch
)
```

Compare with `batch_outputs_table` (line 363) which has a `batch_output_id` surrogate PK, and `token_parents_table` (line 178) which uses a composite `(token_id, parent_token_id)` PK.

## Warnings

### [396-421] Composite FK with nullable `node_id` on `validation_errors` creates ambiguous enforcement

**What:** The `validation_errors_table` has `node_id` as nullable (line 401: `Column("node_id", String(64))` with no `nullable=False`), but also has a composite `ForeignKeyConstraint(["node_id", "run_id"], ["nodes.node_id", "nodes.run_id"])` at lines 416-420.

**Why it matters:** In SQL, a foreign key with any NULL component is not enforced (the standard says composite FKs with NULLs use "match simple" semantics by default). This means:
- When `node_id` is NULL, the FK is not checked at all -- `run_id` could reference a non-existent run and the FK would not catch it. However, `run_id` also has its own separate FK to `runs.run_id` (line 400), so that specific case is covered.
- The composite FK effectively becomes a no-op when `node_id` is NULL. The `_REQUIRED_FOREIGN_KEYS` check in `database.py` (line 53) validates `("validation_errors", "node_id", "nodes")` which checks the FK exists, but does not verify that nullable semantics are intentional.

This is not a data corruption risk because the separate `run_id` FK catches invalid run references. But the composite FK gives a false sense of protection -- when `node_id` is NULL, the FK does not enforce that `run_id` references a valid node run. Since `record_validation_error()` in the recorder accepts `node_id: str | None`, rows with NULL `node_id` do exist in practice.

**Evidence:**
```python
Column("node_id", String(64)),  # Source node where validation failed (nullable)
# ...
ForeignKeyConstraint(
    ["node_id", "run_id"],
    ["nodes.node_id", "nodes.run_id"],
    ondelete="RESTRICT",
)
```

### [151] `is_terminal` uses Integer instead of Boolean for SQLite compatibility

**What:** Line 151: `Column("is_terminal", Integer, nullable=False)` with comment "SQLite doesn't have Boolean, use Integer".

**Why it matters:** This is a reasonable choice for SQLite compatibility, but it means the application layer must enforce that only 0 and 1 are stored. There is no `CheckConstraint` restricting the values. If any code path inserts a value other than 0 or 1, the partial unique index at line 168 (`sqlite_where=(token_outcomes_table.c.is_terminal == 1)`) will still work correctly for value 1, but values like 2 or -1 would not be caught by the uniqueness constraint while potentially being truthy in Python code. A `CheckConstraint("is_terminal IN (0, 1)")` would make this airtight.

**Evidence:**
```python
Column("is_terminal", Integer, nullable=False),  # SQLite doesn't have Boolean, use Integer
```

### [416-420, 441-445] Inconsistent `ondelete` policy across FKs

**What:** The `validation_errors` and `transform_errors` tables specify `ondelete="RESTRICT"` on their composite FKs to `nodes`. However, most other FKs in the schema (e.g., `node_states` FK to `nodes`, `calls` FK to `node_states`, `rows` FK to `nodes`) have no `ondelete` policy, which defaults to `NO ACTION`.

**Why it matters:** `RESTRICT` and `NO ACTION` behave identically in PostgreSQL (both prevent deletion of referenced rows). In SQLite with `foreign_keys=ON`, they also behave the same. However, the explicit `RESTRICT` on some tables but not others creates a maintenance inconsistency -- it suggests the error tables have special deletion protection, but in practice all tables with FKs have the same protection. This inconsistency could confuse developers implementing retention/purge logic.

### [492-503] `secret_resolutions` table stores `timestamp` as `Float` instead of `DateTime`

**What:** Line 496: `Column("timestamp", Float, nullable=False)` with comment "When secret was loaded (before run)".

**Why it matters:** Every other timestamp in the schema uses `DateTime(timezone=True)`. Using `Float` (presumably epoch seconds) for this one table creates a consistency violation. Code that queries or exports this data must handle two different timestamp formats. The `serialize_datetime` formatter used by the exporter expects `datetime` objects, not floats, which means this column requires special handling.

The reason for using Float is likely that secrets are loaded before the run is created, so the timestamp predates the run's `started_at`. However, this could have been a `DateTime(timezone=True)` column storing a `datetime` object derived from the epoch time.

**Evidence:**
```python
# All other tables:
Column("started_at", DateTime(timezone=True), nullable=False),
Column("created_at", DateTime(timezone=True), nullable=False),

# This table:
Column("timestamp", Float, nullable=False),  # When secret was loaded (before run)
```

### [168-174] Partial unique index syntax may not work on all backends

**What:** The partial unique index at lines 168-174 uses both `sqlite_where` and `postgresql_where` keyword arguments. This covers the two supported backends, but if a third backend is ever added (e.g., MySQL), the partial index would not be applied and the uniqueness constraint for terminal outcomes would not be enforced.

**Why it matters:** Low risk since the project explicitly supports only SQLite and PostgreSQL, but worth noting that partial indexes are not universally supported.

## Observations

### [87] Composite PK on `nodes` is well-designed

The `PrimaryKeyConstraint("node_id", "run_id")` correctly handles the requirement that the same node configuration can appear in multiple runs. This is documented in CLAUDE.md and the schema follows through correctly.

### [264-267] XOR constraint on `calls` table is correctly implemented

The `CheckConstraint` ensures exactly one parent (state OR operation) is set for each call. This is paired with partial unique indexes at lines 275-291 that enforce `(state_id, call_index)` and `(operation_id, call_index)` uniqueness within each parent type. This is a clean implementation.

### [373-393] Index coverage is comprehensive

The indexes cover the primary query patterns: run-based filtering, token-to-row lookups, state-to-token lookups, and routing event lookups. The batch-related indexes and operation indexes added in later phases are also present.

### [43-46] Comments mentioning "backward compatibility" for nullable columns

Lines 43, 46 have comments saying "Nullable for backward compatibility". Per the project's No Legacy Code Policy, these should be nullable because they were added to an existing table (and `CREATE TABLE IF NOT EXISTS` plus `create_all` won't add columns to existing tables), not because of backwards compatibility with old data. The comments are slightly misleading but the nullable design is correct for the schema evolution mechanism.

### [470] `format_version` on checkpoints is nullable

`Column("format_version", Integer, nullable=True)` with comment "Nullable for backwards compat with existing checkpoints". Again, the No Legacy Code Policy should mean old checkpoints are simply deleted, not accommodated. However, since this is a data-at-rest concern (existing databases), the nullable design is pragmatic.

### Table count

The schema defines 19 tables, which is a substantial but well-organized schema for a comprehensive audit trail. The table groupings (runs/config, graph structure, data flow, execution recording, aggregation, error tracking, checkpoints, secrets) are logical.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add a primary key to `batch_members` -- either a `PrimaryKeyConstraint("batch_id", "token_id")` (replacing the UniqueConstraint) or a surrogate `batch_member_id` column. (2) Add a `CheckConstraint("is_terminal IN (0, 1)")` to `token_outcomes`. (3) Consider standardizing the `secret_resolutions.timestamp` column to `DateTime(timezone=True)` for consistency with the rest of the schema. (4) Review whether the nullable node_id + composite FK on `validation_errors` achieves the intended constraint behavior.
**Confidence:** HIGH -- Schema analysis is deterministic and the issues identified are structural. The `batch_members` PK issue is factual and the nullable FK semantics are well-documented in the SQL standard.
