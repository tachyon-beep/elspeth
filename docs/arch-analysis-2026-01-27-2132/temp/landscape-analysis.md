# Landscape Subsystem Architecture Analysis

**Date:** 2026-01-27
**Analyst:** Claude Opus 4.5
**Scope:** `src/elspeth/core/landscape/`

---

## Executive Summary

The Landscape subsystem is ELSPETH's audit backbone - a well-structured but incomplete system with several significant issues that need resolution before production. The overall architecture is sound, but there are data integrity gaps, missing functionality, and performance concerns.

**Critical Findings:**
- Checkpoints table defined but NO recorder methods exist for it (dead code or missing feature)
- Transaction boundary issues in DatabaseOps could cause partial writes
- N+1 query patterns in exporter and lineage
- Missing index on critical query path (token_outcomes by run_id filter)
- Repository pattern has confusing session semantics (always None)

---

## Component Analysis

### 1. schema.py - SQLAlchemy Table Definitions

**Lines:** 1-401

**Design Issues:**

1. **Checkpoints Table is Orphaned (lines 373-400)**
   - Table `checkpoints_table` is fully defined with indexes
   - NO recorder methods exist to insert/query checkpoints
   - No Checkpoint repository class in repositories.py
   - This is either dead code or a missing feature - both are problems

2. **Missing Index for Token Outcome Queries (line 134-135)**
   ```python
   Column("run_id", String(64), ForeignKey("runs.run_id"), nullable=False, index=True),
   Column("token_id", String(64), ForeignKey("tokens.token_id"), nullable=False, index=True),
   ```
   - Individual indexes exist but `get_token_outcomes_for_row()` in recorder.py joins on tokens AND filters by run_id
   - Missing composite index `(run_id, token_id)` for this common access pattern

3. **Inconsistent Boolean Handling (line 138)**
   ```python
   Column("is_terminal", Integer, nullable=False),  # SQLite doesn't have Boolean, use Integer
   ```
   - Comment says "SQLite doesn't have Boolean" but SQLAlchemy's Boolean type handles this
   - Manual Integer usage forces 0/1 conversion in recorder (lines 2110, 2477)
   - PostgreSQL would store this as integer when it could be native boolean

4. **batch_members Has No Primary Key (lines 283-291)**
   ```python
   batch_members_table = Table(
       "batch_members",
       metadata,
       Column("batch_id", ...),
       Column("token_id", ...),
       Column("ordinal", ...),
       UniqueConstraint("batch_id", "ordinal"),
       UniqueConstraint("batch_id", "token_id"),
   )
   ```
   - Two unique constraints but no explicit PK
   - SQLAlchemy Core will synthesize a rowid on SQLite but PostgreSQL behavior differs
   - Should have `PrimaryKeyConstraint("batch_id", "token_id")` for consistency

**Functionality Gaps:**

1. **No Soft Delete Mechanism**
   - Tables have no `deleted_at` column
   - Retention policy (mentioned in row_data.py) has no schema support
   - How does payload purging work without deleting rows?

2. **No Schema Version Table**
   - Alembic is mentioned in tech stack but no version tracking in schema
   - `_validate_schema()` in database.py uses hard-coded column checks

---

### 2. database.py - Connection Management

**Lines:** 1-249

**Design Issues:**

1. **In-Memory Factory Bypasses Validation (lines 188-202)**
   ```python
   @classmethod
   def in_memory(cls) -> Self:
       engine = create_engine("sqlite:///:memory:", echo=False)
       cls._configure_sqlite(engine)
       metadata.create_all(engine)
       instance = cls.__new__(cls)  # Bypasses __init__
       instance.connection_string = "sqlite:///:memory:"
       instance._engine = engine
       return instance
   ```
   - Uses `__new__` to bypass `__init__`, skipping `_validate_schema()`
   - Test databases never validate schema - could mask bugs

2. **from_url Also Partially Bypasses Init (lines 204-232)**
   ```python
   instance = cls.__new__(cls)
   instance.connection_string = url
   instance._engine = engine
   instance._validate_schema()  # Called manually
   ```
   - Manual attribute assignment is fragile
   - If `__init__` adds new attributes, these factories will miss them

3. **PostgreSQL Gets No Special Configuration (line 67-68)**
   ```python
   if self.connection_string.startswith("sqlite"):
       LandscapeDB._configure_sqlite(self._engine)
   ```
   - No PostgreSQL-specific pragmas (statement timeout, work_mem, etc.)
   - Production systems may need different settings

**Data Integrity Issues:**

1. **Schema Validation Only Checks Columns, Not Types (lines 120-123)**
   ```python
   columns = {c["name"] for c in inspector.get_columns(table_name)}
   if column_name not in columns:
       missing_columns.append((table_name, column_name))
   ```
   - Checks if column exists but not if type is correct
   - A column could exist with wrong type (String vs Text) and pass validation

---

### 3. recorder.py - High-Level Audit API

**Lines:** 1-2457

**Design Issues:**

1. **Repository Instances Receive None Session (lines 134-148)**
   ```python
   self._run_repo = RunRepository(None)
   self._node_repo = NodeRepository(None)
   # ... all repos get None
   ```
   - Repositories have `session` attribute but it's always None
   - Repositories don't use `self.session` - they just receive row data
   - Misleading design - `session` parameter serves no purpose

2. **Inconsistent Transaction Boundaries (fork_token vs create_token)**

   `create_token()` at line 693:
   ```python
   self._ops.execute_insert(tokens_table.insert()...)  # Single statement
   ```

   `fork_token()` at line 739:
   ```python
   with self._db.connection() as conn:
       for ordinal, branch_name in enumerate(branches):
           conn.execute(tokens_table.insert()...)
           conn.execute(token_parents_table.insert()...)
   ```
   - `fork_token` correctly uses single connection for atomicity
   - `create_token` uses `_ops.execute_insert` which gets NEW connection
   - If caller needs to create token + add parents atomically, they can't

3. **Call Index Counter is In-Memory Only (lines 1750-1787)**
   ```python
   self._call_indices: dict[str, int] = {}  # In-memory only
   ```
   - Counter resets if LandscapeRecorder is recreated
   - For crash recovery/resume, call indices could conflict
   - Should persist in database or query max(call_index) on demand

4. **Missing Checkpoint Methods**
   - `checkpoints_table` defined in schema.py
   - NO methods in recorder.py to:
     - `create_checkpoint()`
     - `get_latest_checkpoint()`
     - `get_checkpoints_for_run()`
   - Model `Checkpoint` exists in models.py (lines 349-367)
   - Feature is scaffolded but not implemented

5. **Inconsistent Enum Handling in update_batch_status (lines 1319-1348)**
   ```python
   def update_batch_status(
       self,
       batch_id: str,
       status: str,  # String, not BatchStatus enum!
   ```
   - Other status methods use `RunStatus | str` and coerce via `coerce_enum()`
   - `update_batch_status` accepts raw string with no validation
   - Could insert invalid status values into audit trail

**Functionality Gaps:**

1. **No Bulk Insert Methods**
   - `create_row()` inserts one row at a time
   - For 10,000 row source, that's 10,000 separate transactions
   - Should have `create_rows_batch()` for performance

2. **No Pagination in List Methods**
   - `get_rows(run_id)` returns ALL rows
   - For large runs, this could OOM
   - Should have `get_rows(run_id, offset=0, limit=1000)`

3. **explain_row Silently Returns None on Run Mismatch (lines 1905-1906)**
   ```python
   if row.run_id != run_id:
       return None
   ```
   - If caller provides wrong run_id, returns None (same as "not found")
   - Should either raise ValueError or return distinct state

---

### 4. repositories.py - Data Access Layer

**Lines:** 1-546

**Design Issues:**

1. **Session Parameter is Dead Code (all repositories)**
   ```python
   def __init__(self, session: Any) -> None:
       self.session = session
   ```
   - Every repository stores `session` but never uses it
   - Called with `None` from recorder.py
   - Either remove parameter or actually use it for queries

2. **Repositories Don't Query - They Just Transform (all repositories)**
   ```python
   def load(self, row: Any) -> Run:
       return Run(
           run_id=row.run_id,
           ...
       )
   ```
   - Repositories only convert DB rows to domain objects
   - No `save()`, no `find()`, no `query()`
   - Pattern name is misleading - these are Mappers, not Repositories

3. **No Inverse Operation (save/to_db_row)**
   - Repositories can `load()` from DB row
   - No `dump()` or `to_values()` to go other direction
   - Recorder duplicates field mapping in insert statements

**Wiring Issues:**

1. **Missing Checkpoint Repository**
   - `CheckpointRepository` not defined despite `Checkpoint` model existing
   - Even if checkpoints_table was used, there's no way to load them

---

### 5. lineage.py - explain() Query Implementation

**Lines:** 1-204

**Design Issues:**

1. **N+1 Query Pattern for Routing Events and Calls (lines 155-165)**
   ```python
   routing_events: list[RoutingEvent] = []
   for state in node_states:
       events = recorder.get_routing_events(state.state_id)  # Query per state!
       routing_events.extend(events)

   calls: list[Call] = []
   for state in node_states:
       state_calls = recorder.get_calls(state.state_id)  # Another query per state!
       calls.extend(state_calls)
   ```
   - For a token with 10 node states, this is 20 queries
   - Should use batch query: `get_routing_events_for_token(token_id)` with JOIN

2. **Validation Errors Queried by Hash, Not Row ID (lines 184-185)**
   ```python
   validation_errors = recorder.get_validation_errors_for_row(run_id, source_row.source_data_hash)
   ```
   - Queries by `source_data_hash` not `row_id`
   - If two rows have identical content (duplicate rows), this returns errors for both
   - Could be intentional but semantically confusing

**Functionality Gaps:**

1. **No Child Token Traversal**
   - `explain()` follows parent tokens but not children
   - For a token that was forked, can't see what happened to the forks
   - Need `get_child_tokens(token_id)` or include in LineageResult

2. **No Artifact Inclusion**
   - `LineageResult` doesn't include artifacts produced for this token
   - Auditors asking "what did this row produce?" can't see output files

---

### 6. exporter.py - JSON/CSV Export

**Lines:** 1-399

**Design Issues:**

1. **Severe N+1 Query Pattern in _iter_records (lines 199-329)**
   ```python
   for row in self._recorder.get_rows(run_id):  # Query 1
       for token in self._recorder.get_tokens(row.row_id):  # N queries
           for parent in self._recorder.get_token_parents(token.token_id):  # N*M queries
               yield {...}
           for state in self._recorder.get_node_states_for_token(token.token_id):  # N*O queries
               for event in self._recorder.get_routing_events(state.state_id):  # ...
                   yield {...}
               for call in self._recorder.get_calls(state.state_id):  # ...
   ```
   - For 1000 rows with avg 2 tokens, 3 states each, 1 call per state:
     - 1 + 1000 + 2000 + 6000 + 6000 + 6000 = 21,001 queries
   - Export of large runs could take hours

2. **Memory Unbounded for Grouped Export (lines 368-398)**
   ```python
   def export_run_grouped(self, run_id: str, sign: bool = False) -> dict[str, list[dict[str, Any]]]:
       groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
       for record in self.export_run(run_id, sign=sign):
           groups[record["record_type"]].append(record)
       return dict(groups)
   ```
   - Loads ALL records into memory before returning
   - Large runs could cause OOM
   - Should stream to files directly

3. **Signature Chain Can't Be Verified Incrementally (lines 122-142)**
   ```python
   running_hash.update(record["signature"].encode())
   # ...
   manifest = {
       "final_hash": running_hash.hexdigest(),
   }
   ```
   - Running hash requires all records to verify
   - No Merkle tree structure for partial verification
   - Can't verify "row 500" without processing 1-499

**Functionality Gaps:**

1. **No Validation Errors or Transform Errors in Export**
   - `_iter_records` exports: run, node, edge, row, token, state, batch, artifact
   - Missing: validation_errors, transform_errors, token_outcomes
   - Compliance review incomplete without error records

2. **No Checkpoint Export**
   - Checkpoints not exported even if they existed
   - Recovery state would be lost in export/import cycle

---

### 7. formatters.py - Output Formatting

**Lines:** 1-53

**Design Issues:**

1. **CSVFormatter.flatten() Recursively Flattens but JSON Serializes Lists (lines 33-48)**
   ```python
   if isinstance(value, dict):
       result.update(self.flatten(value, full_key))  # Recurse
   elif isinstance(value, list):
       result[full_key] = json.dumps(value)  # JSON string
   ```
   - Nested dicts become flat keys: `a.b.c`
   - Lists become JSON strings: `["x", "y"]`
   - Inconsistent - what about list of dicts?

2. **No Date Formatting**
   - datetime objects passed to `json.dumps(default=str)` in JSONFormatter
   - No ISO 8601 standardization guarantee
   - Different Python versions may format differently

**Missing Functionality:**

1. **No Schema/Header Generation for CSV**
   - CSVFormatter flattens records but no `get_headers()` method
   - Caller must infer headers from first record
   - Dynamic schemas could have different columns per row

---

### 8. row_data.py - Row State Tracking

**Lines:** 1-61

**Design Issues:**

1. **Immutable Dataclass Forces New Object Creation (line 34)**
   ```python
   @dataclass(frozen=True)
   class RowDataResult:
   ```
   - frozen=True is good for safety
   - But if we later need to attach metadata (e.g., cache hit), can't mutate
   - Minor concern but worth noting

**This module is well-designed. No significant issues.**

---

### 9. models.py - Pydantic Models

**Lines:** 1-393

**Design Issues:**

1. **Duplicate Model Definitions in Two Places**
   - models.py defines: Run, Node, Edge, Row, Token, NodeState variants, Call, Artifact, etc.
   - Same models appear to be in `elspeth.contracts.audit`
   - recorder.py imports from `elspeth.contracts`, not models.py
   - models.py may be dead code or an older version

2. **Node Model in models.py Missing schema_fields (line 63-83)**
   ```python
   @dataclass
   class Node:
       node_id: str
       # ... no schema_mode, no schema_fields
   ```
   - But NodeRepository in repositories.py loads `schema_mode` and `schema_fields`
   - The contracts.audit.Node must have these fields
   - models.py Node is out of sync

3. **Call and RoutingEvent Use str Instead of Enums (lines 267-282, 300-313)**
   ```python
   @dataclass
   class Call:
       call_type: str  # llm, http, sql, filesystem
       status: str  # success, error

   @dataclass
   class RoutingEvent:
       mode: str  # move, copy
   ```
   - But repositories.py converts to enums: `CallType(row.call_type)`
   - The models in contracts use enums; models.py uses strings
   - models.py is definitely stale

**This File May Be Dead Code:**
- recorder.py imports from `elspeth.contracts`, not `elspeth.core.landscape.models`
- Only imports I see are `from elspeth.contracts import ...`
- models.py may have been original location, now migrated

---

### 10. reproducibility.py - Grade Computation

**Lines:** 1-137

**Design Issues:**

1. **update_grade_after_purge Returns Silently on Missing Run (line 112-113)**
   ```python
   if row is None:
       return  # Run doesn't exist
   ```
   - Silent return when run doesn't exist
   - Per Data Manifesto, missing runs should crash (Tier 1 data)
   - Should raise ValueError for consistency

2. **compute_grade Queries But Doesn't Use DatabaseOps (lines 63-72)**
   ```python
   with db.connection() as conn:
       result = conn.execute(query)
   ```
   - Other methods use `self._ops.execute_*` pattern
   - This directly uses db.connection()
   - Inconsistent but not functionally wrong

---

### 11. _database_ops.py - Database Operation Helpers

**Lines:** 1-46

**Data Integrity Issues:**

1. **Each Method Opens New Connection/Transaction (lines 25-45)**
   ```python
   def execute_fetchone(self, query: Executable) -> Row[Any] | None:
       with self._db.connection() as conn:  # New connection!
           result = conn.execute(query)
           return result.fetchone()

   def execute_insert(self, stmt: Executable) -> None:
       with self._db.connection() as conn:  # Another new connection!
           conn.execute(stmt)
   ```
   - Every operation gets its own transaction
   - If recorder calls `execute_insert` then `execute_insert` again, second could fail and first is already committed
   - No way to do multi-statement atomic operations via DatabaseOps

2. **No execute_many for Bulk Operations**
   - Only single-statement methods
   - Bulk inserts must use `self._db.connection()` directly (like fork_token does)

---

### 12. _helpers.py - Common Helpers

**Lines:** 1-43

**No significant issues. Simple, focused utilities.**

---

## Cross-Cutting Concerns

### Transaction Safety

The codebase has inconsistent transaction handling:

| Pattern | Used In | Atomicity |
|---------|---------|-----------|
| `self._ops.execute_*` | Most single operations | Per-statement |
| `with self._db.connection() as conn:` | fork_token, coalesce_tokens, expand_token | Multi-statement atomic |

**Problem:** A caller might do:
```python
recorder.create_token(row_id)  # Commits
recorder.add_token_parent(...)  # Fails - token orphaned!
```

**Recommendation:** Add transaction context manager or batch operation methods.

### Query Performance Summary

| Method | Pattern | Impact |
|--------|---------|--------|
| `exporter._iter_records` | N^3 nested loops | Hours for large runs |
| `lineage.explain` | 2N for node states | Slow for complex tokens |
| `get_token_outcomes_for_row` | Good (single JOIN) | OK |
| `get_rows` / `get_tokens` | No pagination | OOM for large runs |

### Missing Features Checklist

| Feature | Schema | Recorder | Used |
|---------|--------|----------|------|
| Checkpoints | Yes (lines 373-400) | NO | NO |
| Bulk row insert | N/A | NO | - |
| Pagination | N/A | NO | - |
| Export validation_errors | Yes | NO in exporter | - |
| Export transform_errors | Yes | NO in exporter | - |
| Export token_outcomes | Yes | NO in exporter | - |
| Child token traversal | N/A | NO | - |

---

## Severity Classification

### P1 - Must Fix Before Production

1. **Checkpoint feature incomplete** - Schema exists, no methods (schema.py:373-400, recorder.py missing)
2. **Exporter N+1 queries** - Export unusable for real workloads (exporter.py:199-329)
3. **Exporter missing error/outcome records** - Compliance gap (exporter.py)
4. **BatchStatus not validated** - Can corrupt audit trail (recorder.py:1319)

### P2 - Should Fix Soon

5. **DatabaseOps transaction isolation** - Could cause partial writes (_database_ops.py:25-45)
6. **Call index counter in-memory only** - Resume could conflict (recorder.py:1750-1787)
7. **Lineage N+1 for routing/calls** - Slow explain() (lineage.py:155-165)
8. **No bulk insert methods** - Source ingestion slow (recorder.py)

### P3 - Cleanup/Improvement

9. **models.py appears dead** - Sync or delete (models.py)
10. **Repository session parameter unused** - Remove or use (repositories.py)
11. **in_memory() bypasses validation** - Could mask bugs (database.py:188-202)
12. **Missing composite index on token_outcomes** - Query perf (schema.py:134)

---

## Confidence Assessment

**Confidence:** High

**Evidence:**
- Read 100% of all 13 files in landscape/
- Cross-referenced schema definitions with recorder methods
- Traced query patterns through exporter and lineage
- Verified import paths to confirm contracts vs models usage
- Counted actual query calls in nested loops

**Known Gaps:**
- Did not examine `elspeth.contracts` modules (would confirm models.py is dead)
- Did not run actual queries to measure performance
- Did not examine Alembic migrations directory

---

## Recommendations

1. **Implement or Remove Checkpoints**
   - If feature needed: Add `create_checkpoint()`, `get_latest_checkpoint()`, `CheckpointRepository`
   - If not needed: Remove `checkpoints_table` from schema

2. **Fix Exporter Query Pattern**
   - Add batch methods: `get_tokens_for_run(run_id)`, `get_all_node_states(run_id)`, etc.
   - Use single JOIN queries in exporter
   - Add missing record types: validation_errors, transform_errors, token_outcomes

3. **Add Batch Operations**
   - `create_rows_batch(rows: list[dict])` for bulk ingestion
   - Consider SQLAlchemy's `insert().values([...])` for multi-row insert

4. **Persist Call Indices**
   - Either persist to DB or query `MAX(call_index)` when allocating
   - Critical for crash recovery

5. **Delete or Sync models.py**
   - Verify it's unused
   - If unused, delete
   - If used, sync with contracts

6. **Clean Up Repository Pattern**
   - Remove unused `session` parameter
   - Rename to `*Mapper` since they don't query
   - Or add actual query methods and use the pattern properly
