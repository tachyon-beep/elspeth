# Architecture Analysis: core/landscape/ Subsystem

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Analyst:** Claude Opus 4.6
**Scope:** All 21 files in `src/elspeth/core/landscape/` (11,681 lines)

---

## 1. Subsystem Responsibility

The `core/landscape/` subsystem is the **audit backbone** of ELSPETH. It provides complete, immutable, and cryptographically verifiable recording of every operation during pipeline execution -- from run lifecycle and node registration through token processing, routing decisions, external calls, aggregation batches, and terminal outcomes. The subsystem enforces Tier 1 (full trust) semantics: any anomaly in audit data causes an immediate crash rather than silent degradation. It supports SQLite (development), PostgreSQL (production), and SQLCipher (encrypted) backends, with optional JSONL change journaling for emergency backup. Every piece of data written through this subsystem is hashed via RFC 8785 canonical JSON, enabling post-hoc integrity verification even after payload purging.

---

## 2. Per-File Analysis

### 2.1. recorder.py (121 lines)

**Purpose:** Main entry point class `LandscapeRecorder` that composes all recording functionality through mixin inheritance.

**Key classes:**
- `LandscapeRecorder` -- Composes 8 mixins into a single API: `RunRecordingMixin`, `GraphRecordingMixin`, `NodeStateRecordingMixin`, `TokenRecordingMixin`, `CallRecordingMixin`, `BatchRecordingMixin`, `ErrorRecordingMixin`, `QueryMethodsMixin`.

**Dependencies:** All mixin modules, `LandscapeDB`, all 14 repository classes from `repositories.py`, `DatabaseOps`, `PayloadStore` (optional, TYPE_CHECKING).

**Data flow:** Receives pipeline events from the engine, delegates to mixins for recording, persists through `DatabaseOps` to `LandscapeDB`.

**Architectural patterns:**
- **Mixin composition** -- The monolithic recorder is split across 8 focused files but assembled into one class. Each mixin declares shared state annotations (`_db`, `_ops`, repository instances) that are initialized in `LandscapeRecorder.__init__()`.
- **Repository pattern** -- 14 repository instances for row-to-object conversion.
- **Thread-safe call indexing** -- Per-state and per-operation call indices with a `Lock`.

**Concerns:**
- **(P3) Mixin anti-pattern:** The 8 mixins share state through implicit class attribute annotations rather than explicit composition. Each mixin declares `_db: LandscapeDB` etc. as type annotations but relies on `LandscapeRecorder.__init__()` to set them. This works but is fragile -- a mixin can reference any attribute from any other mixin with no compile-time safety. If a mixin accesses a repository owned by another mixin, mypy cannot verify it.
- **(P3) God object tendency:** Despite decomposition into mixins, `LandscapeRecorder` is effectively a 3,000+ line class with ~60 public methods. The mixin split is a file organization strategy, not a true separation of concerns.
- **(P4) 14 repository instances:** Every `LandscapeRecorder` instantiates all 14 repositories regardless of which methods will be called. The repositories are lightweight (no state), so the cost is negligible, but it hints at potential for lazy initialization.

---

### 2.2. database.py (500 lines)

**Purpose:** Database connection management -- handles SQLite, PostgreSQL, and SQLCipher backends with schema validation and migration detection.

**Key classes:**
- `LandscapeDB` -- Connection manager with `engine` property, `connection()` context manager, and factory methods `in_memory()` and `from_url()`.
- `SchemaCompatibilityError` -- Raised when schema is outdated.

**Dependencies:** `sqlalchemy` (Engine, create_engine, event, inspect), `LandscapeJournal`, `schema.metadata`.

**Data flow:** Creates/validates database, provides `Connection` objects via context manager.

**Architectural patterns:**
- **Factory methods** -- `in_memory()` for testing, `from_url()` for production, `__init__()` for standard construction.
- **Schema validation on init** -- `_validate_schema()` checks for required columns and foreign keys before `create_all()`.
- **SQLCipher integration** -- Creator callback pattern keeps passphrase out of URL/logs.
- **SQLite PRAGMAs** -- WAL mode, foreign keys ON, busy timeout via connection event hooks.

**Concerns:**
- **(P2) `in_memory()` bypasses `__init__`:** Uses `cls.__new__(cls)` and manually sets attributes, bypassing the normal constructor. If `__init__` adds new attributes, `in_memory()` must be updated manually. This has been stable but is a latent maintenance risk.
- **(P3) `from_url()` also bypasses `__init__`:** Same pattern as `in_memory()`. Two factory methods that both manually set instance attributes creates a maintenance burden.
- **(P3) Schema validation is SQLite-only:** PostgreSQL relies on Alembic migrations, but there is no check that Alembic is actually configured or that migrations have been run. A stale PostgreSQL schema would not be caught here.

---

### 2.3. schema.py (524 lines)

**Purpose:** SQLAlchemy Core table definitions for all 17 Landscape tables plus indexes and constraints.

**Key tables (17):**
- `runs_table` -- Run lifecycle and configuration
- `nodes_table` -- Plugin instances (composite PK: `node_id, run_id`)
- `edges_table` -- DAG edges with composite FKs
- `rows_table` -- Source rows
- `tokens_table` -- Row instances in DAG paths
- `token_outcomes_table` -- Terminal states with partial unique index
- `token_parents_table` -- Multi-parent relationships for joins
- `node_states_table` -- Processing records (discriminated union)
- `operations_table` -- Source/sink I/O (parent for calls)
- `calls_table` -- External calls with XOR parent constraint
- `artifacts_table` -- Sink outputs
- `routing_events_table` -- Routing decisions
- `batches_table`, `batch_members_table`, `batch_outputs_table` -- Aggregation
- `checkpoints_table` -- Crash recovery
- `secret_resolutions_table` -- Key Vault audit trail
- `validation_errors_table`, `transform_errors_table` -- Error tracking

**Dependencies:** SQLAlchemy Core only (no ORM).

**Architectural patterns:**
- **Composite primary keys** -- `nodes_table` uses `(node_id, run_id)` to allow same pipeline across runs.
- **Composite foreign keys** -- Multiple tables use `ForeignKeyConstraint` for `(node_id, run_id)`.
- **Partial unique indexes** -- Terminal outcome uniqueness, call parent uniqueness.
- **XOR constraint** -- `calls_table` enforces exactly one parent (`state_id` XOR `operation_id`).
- **Denormalized run_id** -- On `node_states`, `tokens`, etc. for efficient filtering.

**Concerns:**
- **(P3) No Alembic migration files visible in this subsystem:** The schema is defined here but migration management is separate. The `_validate_schema()` approach in `database.py` is a workaround for SQLite; PostgreSQL deployments depend on external Alembic configuration.
- **(P4) `NODE_ID_COLUMN_LENGTH = 64`:** Exported constant consumed by `dag/models.py`. A schema-level constant leaking to DAG construction is a minor coupling.
- **Sound:** The schema is well-designed with appropriate constraints, indexes, and referential integrity. The composite PK pattern and XOR constraint are correctly implemented.

---

### 2.4. exporter.py (595 lines)

**Purpose:** Exports complete audit data for a run as a flat sequence of typed records, suitable for compliance review. Supports HMAC signing with hash chain manifest.

**Key classes:**
- `LandscapeExporter` -- Exports run data as `Iterator[dict[str, Any]]`, optionally signed. Supports flat iteration and grouped output.

**Dependencies:** `LandscapeRecorder` (query methods), `canonical_json`, contract types from `elspeth.contracts`.

**Data flow:** Reads all audit data for a run via recorder, transforms to flat dicts, optionally signs with HMAC.

**Architectural patterns:**
- **Batch query optimization (Bug 76r fix):** Pre-loads all tokens, parents, states, routing events, calls, and outcomes in ~10 queries, then iterates in memory. Eliminated the previous N+1 pattern (~25,000 queries for 1,000 rows).
- **Hash chain manifest:** Running SHA-256 hash of all signed records produces a tamper-evident chain.
- **Discriminated union handling:** Explicitly handles `NodeStateOpen`, `NodeStatePending`, `NodeStateCompleted`, `NodeStateFailed` with type-specific field mapping.

**Concerns:**
- **(P2) Untyped dict output:** Every record is emitted as `dict[str, Any]`. There are no frozen dataclasses or TypedDicts for export records. The exporter manually constructs dicts with string keys, making field name typos invisible to type checking. This is a known pattern from the "Untyped Dicts at Tier 1 Boundary" bug pattern in MEMORY.md.
- **(P3) Full in-memory materialization:** All data for a run is loaded into memory (6 batch queries). For very large runs (100k+ rows), this could cause memory pressure. No streaming/chunking for the inner loop.
- **(P3) NodeState isinstance chain:** The 4-way isinstance check for NodeState variants is repeated here rather than having a `to_export_dict()` method on the NodeState types. This creates duplication and a maintenance risk if a 5th variant is added.

---

### 2.5. journal.py (287 lines)

**Purpose:** Append-only JSONL journal of committed database writes for emergency backup.

**Key classes:**
- `LandscapeJournal` -- Attaches to SQLAlchemy engine events, buffers write statements per-connection, flushes on commit, discards on rollback.
- `JournalRecord`, `PayloadInfo` -- TypedDict definitions for journal entries.

**Dependencies:** SQLAlchemy events, `_helpers.now`, `formatters.serialize_datetime`, `FilesystemPayloadStore`.

**Data flow:** Intercepts SQL statements via `after_cursor_execute`, buffers per-connection, writes to JSONL file on `commit`, discards on `rollback`.

**Architectural patterns:**
- **Event-driven capture:** Uses SQLAlchemy `after_cursor_execute`, `commit`, and `rollback` events.
- **Transaction-aware buffering:** Records are buffered in `conn.info` (connection-local storage) and only written on commit. Rollbacks discard the buffer.
- **Circuit breaker:** After 5 consecutive failures, disables journaling with periodic recovery attempts (every 100 dropped records).
- **Optional payload enrichment:** Can inline payload data for calls records.

**Concerns:**
- **(P2) Non-atomic file writes:** The journal writes to file via `handle.write(payload)` without fsync or atomic rename. A crash mid-write could produce a truncated JSONL line. This is documented as a known issue in MEMORY.md.
- **(P3) SQL parsing fragility:** `_parse_insert_statement()` uses string parsing to extract table name and column names from SQL statements. This is sensitive to SQLAlchemy's generated SQL format changes.
- **(P3) Silent degradation path:** When `fail_on_error=False` (default), the journal silently drops records after failures and periodically logs warnings. While the journal is explicitly documented as "not the canonical audit record," silent data loss in a backup mechanism is worth noting.

---

### 2.6. lineage.py (237 lines)

**Purpose:** Composes recorder query results into a complete `LineageResult` for a token or row. This is the "explain" API.

**Key classes/functions:**
- `LineageResult` -- Dataclass containing token, source row, node states, routing events, calls, parent tokens, errors, and outcome.
- `explain()` -- Function that resolves token/row IDs, validates lineage integrity, and assembles the complete result.

**Dependencies:** `LandscapeRecorder` (TYPE_CHECKING), contract types.

**Data flow:** Takes `(run_id, token_id|row_id, sink?)` and returns a fully assembled `LineageResult` with all audit data.

**Architectural patterns:**
- **Tier 1 integrity enforcement:** Validates group ID consistency (fork XOR join XOR expand), bidirectional parent/group consistency, and parent token existence. Crashes on any anomaly.
- **Disambiguation protocol:** Row-based explain requires exactly one terminal token, or a sink parameter to disambiguate forks.
- **Batch query optimization:** Uses `get_routing_events_for_states()` and `get_calls_for_states()` to avoid N+1 patterns.

**Concerns:**
- **(P4) N+1 for parent tokens:** The parent token loop (`for parent in parents: recorder.get_token(parent.parent_token_id)`) is still N+1. For typical forks (2-3 parents) this is negligible, but for large joins it could matter.
- **Sound:** Excellent Tier 1 enforcement. The integrity checks are thorough and correct.

---

### 2.7. formatters.py (248 lines)

**Purpose:** Output formatters for different export formats (JSON, CSV, text) and serialization utilities.

**Key classes/functions:**
- `serialize_datetime()` -- Recursive converter for datetime-to-ISO with NaN/Infinity rejection.
- `dataclass_to_dict()` -- Recursive dataclass-to-dict converter with Enum handling.
- `ExportFormatter` (Protocol), `JSONFormatter`, `CSVFormatter`, `LineageTextFormatter`.

**Dependencies:** Standard library only (json, math, dataclasses, enum). `LineageResult` via TYPE_CHECKING.

**Concerns:**
- **(P3) `dataclass_to_dict` uses `__dataclass_fields__`:** Direct access to the dunder attribute rather than `fields()` from `dataclasses`. Both work, but `fields()` is the public API.
- **Sound:** Clean implementation with proper NaN/Infinity rejection per CLAUDE.md requirements.

---

### 2.8. repositories.py (564 lines)

**Purpose:** Repository layer converting SQLAlchemy rows to domain dataclasses. Enforces Tier 1 invariants during deserialization.

**Key classes (14 repositories):**
- `RunRepository`, `NodeRepository`, `EdgeRepository`, `RowRepository`, `TokenRepository`, `TokenParentRepository`, `CallRepository`, `RoutingEventRepository`, `BatchRepository`, `NodeStateRepository`, `ValidationErrorRepository`, `TransformErrorRepository`, `TokenOutcomeRepository`, `ArtifactRepository`, `BatchMemberRepository`.

**Dependencies:** `elspeth.contracts.audit` dataclasses, `elspeth.contracts.enums`.

**Architectural patterns:**
- **Enum-at-boundary conversion:** Strings from DB are converted to enums in the repository `load()` method. Invalid enum values crash (Tier 1).
- **Discriminated union for NodeState:** `NodeStateRepository.load()` dispatches on `status` field to construct the correct variant, with extensive invariant validation per status.
- **TokenOutcome cross-validation:** Validates `is_terminal` integer (must be exactly 0 or 1, rejects bools), then cross-checks against `RowOutcome.is_terminal`.

**Concerns:**
- **(P2) Operation model not through repository:** `get_operation()`, `get_operations_for_run()` in `_call_recording.py` construct `Operation` directly from DB rows without a repository class. This is inconsistent -- Operations bypass the repository pattern that all other models use.
- **(P3) `NodeRepository.load()` inline `import json`:** The json import is inside the method body rather than at module level. Functional but unusual.
- **Sound:** Excellent Tier 1 enforcement in `NodeStateRepository` and `TokenOutcomeRepository`. The discriminated union validation is thorough.

---

### 2.9. reproducibility.py (149 lines)

**Purpose:** Computes and manages reproducibility grades (FULL_REPRODUCIBLE, REPLAY_REPRODUCIBLE, ATTRIBUTABLE_ONLY).

**Key classes/functions:**
- `ReproducibilityGrade` (StrEnum)
- `compute_grade()` -- Checks node determinism values.
- `update_grade_after_purge()` -- Atomic conditional downgrade after payload purge.

**Dependencies:** `LandscapeDB` (TYPE_CHECKING), `Determinism` enum, schema tables.

**Concerns:**
- **(P4) Two separate connections for compute_grade:** Opens one connection to verify run exists, then a second for the determinism query. Could be consolidated.
- **Sound:** Correct atomic conditional update pattern (WHERE clause as CAS). Proper Tier 1 validation of enum values.

---

### 2.10. row_data.py (71 lines)

**Purpose:** Explicit state discrimination for row data retrieval results, replacing ambiguous `dict | None`.

**Key classes:**
- `RowDataState` (StrEnum) -- 5 states: AVAILABLE, PURGED, NEVER_STORED, STORE_NOT_CONFIGURED, ROW_NOT_FOUND.
- `RowDataResult` (frozen dataclass) -- State + optional data with `__post_init__` invariant validation.

**Dependencies:** None (self-contained value type).

**Concerns:**
- **Sound:** Excellent pattern. The explicit state discrimination eliminates the "why is it None?" ambiguity. The `__post_init__` validation ensures invariants.

---

### 2.11. _batch_recording.py (469 lines)

**Purpose:** Batch lifecycle (create, add members, update status, complete, retry) and artifact registration.

**Key methods:** `create_batch()`, `add_batch_member()`, `update_batch_status()`, `complete_batch()`, `get_incomplete_batches()`, `retry_batch()`, `register_artifact()`, `get_artifacts()`.

**Concerns:**
- **(P3) Truthiness checks for filters:** `if status:` and `if node_id:` in `get_batches()` and `get_artifacts()` use truthiness rather than `is not None`. This means `status=BatchStatus(0)` or `node_id=""` would be silently ignored. Should be `if status is not None:`.
- **Sound:** Otherwise well-structured with proper terminal status validation.

---

### 2.12. _call_recording.py (603 lines)

**Purpose:** External call recording (state-parented and operation-parented), call index allocation, replay lookup, operations lifecycle.

**Key methods:** `allocate_call_index()`, `record_call()`, `begin_operation()`, `complete_operation()`, `record_operation_call()`, `find_call_by_request_hash()`, `get_call_response_data()`.

**Concerns:**
- **(P2) `complete_operation()` accesses `self._ops._db` directly:** Line 278 uses `self._ops._db.connection()` rather than going through `self._db.connection()`. This breaks the encapsulation of `DatabaseOps` by reaching into its private attribute. The operation needs raw connection for the check-and-update pattern, but this creates a coupling.
- **(P2) Operation model lacks repository:** As noted in 2.8, Operations are constructed inline rather than through a repository class. This means enum validation for `operation_type` and `status` does not happen at the deserialization boundary.
- **(P3) `get_call_response_data()` catches `KeyError` for purged payloads:** Returns `None` for purged data, but also returns `None` when payload store is not configured or call not found. While the method documents this, callers cannot distinguish these cases (unlike `RowDataResult`).

---

### 2.13. _error_recording.py (298 lines)

**Purpose:** Validation error and transform error recording with Tier-3 boundary handling.

**Key methods:** `record_validation_error()`, `record_transform_error()`, `get_validation_errors_for_row()`, `get_validation_errors_for_run()`, `get_transform_errors_for_token()`, `get_transform_errors_for_run()`.

**Architectural patterns:**
- **Tier-3 boundary at error recording:** Validation error row data may be non-canonical (NaN, Infinity, non-dict). Uses `repr_hash()` and `NonCanonicalMetadata` fallback.
- **Cross-run contamination prevention:** `_validate_token_run_ownership_for_error()` crashes on mismatch.

**Concerns:**
- **(P3) `record_transform_error()` calls `stable_hash(row_data)` without quarantine fallback:** The `row_data` parameter accepts `PipelineRow | dict`. For transform errors, the row has already passed source validation (Tier 2), so this is likely safe. But the validation error path has the fallback and this one does not -- inconsistency worth noting.
- **Sound:** Good Tier-3 handling for validation errors. The `NonCanonicalMetadata` fallback preserves audit trail even for garbage input.

---

### 2.14. _graph_recording.py (366 lines)

**Purpose:** Node and edge registration in the execution graph, plus schema contract audit recording.

**Key methods:** `register_node()`, `register_edge()`, `get_node()`, `get_nodes()`, `get_node_contracts()`, `get_edges()`, `get_edge()`, `get_edge_map()`, `update_node_output_contract()`.

**Concerns:**
- **(P3) `get_edge()` raises ValueError for audit integrity:** While correct per Tier 1, this uses `ValueError` rather than `AuditIntegrityError`. Other places in the codebase use `AuditIntegrityError` for the same class of error.
- **Sound:** Proper composite PK handling for node lookups. Good contract audit trail integration.

---

### 2.15. _helpers.py (43 lines)

**Purpose:** Shared utility functions: `now()`, `generate_id()`, `coerce_enum()`.

**Concerns:**
- **(P4) `coerce_enum()` appears unused:** A grep through the mixin files shows no usage of `coerce_enum()`. The repositories handle enum conversion directly. This may be dead code.
- **Sound:** Simple and correct.

---

### 2.16. _node_state_recording.py (368 lines)

**Purpose:** Node state lifecycle (begin, complete) and routing event recording (single and multi-destination).

**Key methods:** `begin_node_state()`, `complete_node_state()` (with overloads), `record_routing_event()`, `record_routing_events()`.

**Architectural patterns:**
- **Type-safe overloads:** `complete_node_state()` uses `@overload` to return the correct discriminated union variant based on the status literal.
- **Quarantine-aware hashing:** `begin_node_state()` accepts a `quarantined` flag to use `repr_hash` fallback.
- **Batch routing in single transaction:** `record_routing_events()` uses `self._db.connection()` directly for atomic multi-row insert.

**Concerns:**
- **(P3) Direct DB connection in `record_routing_events`:** Uses `self._db.connection()` directly rather than `self._ops`, which means it bypasses the zero-rows-affected check in `DatabaseOps.execute_insert()`. While justified by the need for a single transaction, it creates two code paths for inserts.
- **Sound:** Excellent overload pattern for type safety.

---

### 2.17. _query_methods.py (500 lines)

**Purpose:** Read-only query methods for entities, batch queries for export/lineage, and explain methods.

**Key methods:** Per-entity getters (`get_row()`, `get_token()`, etc.), batch getters for states (`get_routing_events_for_states()`, `get_calls_for_states()`), batch getters for runs (`get_all_tokens_for_run()`, etc.), `explain_row()`.

**Architectural patterns:**
- **Chunked IN queries:** `get_routing_events_for_states()` and `get_calls_for_states()` chunk state_ids into groups of 500 to respect SQLite's `SQLITE_MAX_VARIABLE_NUMBER` limit.
- **Graceful payload degradation:** `explain_row()` handles purged payloads, infrastructure errors, and JSON decode errors distinctly.
- **Tier 1 enforcement:** Corrupt payloads (non-dict JSON) raise `AuditIntegrityError`.

**Concerns:**
- **(P3) `get_all_tokens_for_run()` joins through `rows_table` instead of using `tokens_table.c.run_id`:** The tokens table has a denormalized `run_id` column (added per CLAUDE.md pattern), but this batch query joins through rows instead of filtering directly. Not incorrect, but unnecessarily complex.
- **(P3) `get_all_token_parents_for_run()` joins through tokens AND rows:** Double join to reach `run_id`, when it could use `tokens.run_id` directly. Same issue as above.
- **Sound:** Good chunking strategy for SQLite compatibility.

---

### 2.18. _run_recording.py (545 lines)

**Purpose:** Run lifecycle -- begin, complete, finalize, status updates, export status, secret resolutions, field resolution, and schema contracts.

**Key methods:** `begin_run()`, `complete_run()`, `finalize_run()`, `get_run()`, `list_runs()`, `get_source_schema()`, `record_source_field_resolution()`, `get_source_field_resolution()`, `update_run_status()`, `update_run_contract()`, `get_run_contract()`, `record_secret_resolutions()`, `set_export_status()`, `compute_reproducibility_grade()`.

**Concerns:**
- **(P2) `record_secret_resolutions()` accepts `list[dict[str, Any]]`:** This is the exact "untyped dict at Tier 1 boundary" anti-pattern. Secret resolution data arrives as `dict[str, Any]` and is destructured with string key access (`rec["timestamp"]`, `rec["env_var_name"]`, etc.). Should be a frozen dataclass.
- **(P3) `begin_run()` stores `status` as enum value rather than `.value`:** Line 105 assigns `status=run.status` rather than `status=run.status.value`. Since `RunStatus` inherits from `str` (StrEnum), this works, but it's inconsistent with other methods that explicitly call `.value`.
- **Sound:** Good Tier 1 validation in `get_source_field_resolution()` and `get_run_contract()`. Schema contract hash verification is correct.

---

### 2.19. _token_recording.py (809 lines)

**Purpose:** Token lifecycle -- creation, forking, coalescing, expanding, outcome recording.

**Key methods:** `create_row()`, `create_token()`, `fork_token()`, `coalesce_tokens()`, `expand_token()`, `record_token_outcome()`, `get_token_outcome()`, `get_token_outcomes_for_row()`.

**Architectural patterns:**
- **Atomic fork/expand:** Fork and expand operations create children AND record parent outcome in a single transaction.
- **Ownership validation:** Every mutation validates token-to-run and token-to-row ownership via `_validate_token_run_ownership()` and `_validate_token_row_ownership()`.
- **Outcome contract enforcement:** `_validate_outcome_fields()` enforces required fields per outcome type.
- **Quarantine-aware hashing:** `create_row()` supports quarantined data with `repr_hash` fallback.

**Concerns:**
- **(P3) Redundant ownership lookups:** `fork_token()` calls both `_validate_token_run_ownership()` and `_validate_token_row_ownership()`, each of which calls `_resolve_token_ownership()`. This results in 2 DB queries for what could be 1 (resolve once, validate both).
- **(P3) `coalesce_tokens()` has O(n) DB queries for parent validation:** Each parent token gets its own `_validate_token_row_ownership()` + `_resolve_token_ownership()` call (2 queries per parent). For small coalesces (2-3 parents) this is fine; for larger ones it's suboptimal.
- **Sound:** Excellent atomic transaction patterns. The ownership validation is thorough and correct.

---

### 2.20. _database_ops.py (58 lines)

**Purpose:** Helper class reducing connection management boilerplate.

**Key class:** `DatabaseOps` with `execute_fetchone()`, `execute_fetchall()`, `execute_insert()`, `execute_update()`.

**Architectural patterns:**
- **Zero-rows-affected guard:** Both `execute_insert()` and `execute_update()` raise `ValueError` if `rowcount == 0`. This is Tier 1 enforcement -- a write that affected no rows means the target doesn't exist or a constraint was violated.

**Concerns:**
- **(P3) Each operation opens a new connection:** Every call to `execute_*()` does `with self._db.connection() as conn:`, which opens a new transaction. This means sequential recorder calls (e.g., `begin_node_state()` then `complete_node_state()`) each get their own transaction. This is correct for isolation but means there's no way to group related writes into a single transaction through `DatabaseOps`.
- **(P4) `ValueError` rather than `AuditIntegrityError`:** Uses generic `ValueError` instead of the project's `AuditIntegrityError` for audit write failures.

---

### 2.21. __init__.py (149 lines)

**Purpose:** Public API surface definition. Re-exports model classes from `elspeth.contracts`, database/recorder classes, formatters, lineage, schema tables.

**Concerns:**
- **(P3) Re-exports contract types:** The `__init__.py` re-exports ~30 types from `elspeth.contracts`. This creates a dual import path (`from elspeth.core.landscape import Run` vs `from elspeth.contracts import Run`). While convenient, it means the landscape package's public API includes types it doesn't own.
- **(P4) `batch_outputs_table` exported but no recorder methods:** The `batch_outputs_table` is in schema and exported, but there is no `BatchOutputRepository` and no recorder methods for it. The table appears unused in the recorder -- writes may happen elsewhere or it may be dead schema.

---

## 3. Internal Architecture

```
                    __init__.py (public API surface)
                         |
                    recorder.py (LandscapeRecorder = 8 mixins)
                   /    |    \    \    \    \    \    \
    _run_recording  _graph_  _node_state  _token_  _call_  _batch_  _error_  _query_
         .py        recording  recording  recording recording recording recording methods
                      .py        .py        .py       .py       .py       .py       .py
                         \       |       /
                        _database_ops.py (DatabaseOps)
                              |
                         database.py (LandscapeDB)
                              |
                         schema.py (table definitions)
                              |
                         journal.py (JSONL backup)

    Supporting:
        repositories.py (row -> domain object conversion)
        _helpers.py (now, generate_id, coerce_enum)
        formatters.py (export formatting)
        lineage.py (explain query composition)
        reproducibility.py (grade computation)
        row_data.py (explicit state discrimination)
```

**Module relationships:**
1. `recorder.py` is the central hub, composed of 8 mixins that all depend on `_database_ops.py` and `_helpers.py`.
2. `database.py` owns the connection and delegates to `schema.py` for table metadata and `journal.py` for backup.
3. `repositories.py` is used exclusively by the mixin modules for deserializing DB rows.
4. `lineage.py` and `exporter.py` are consumers of the recorder's query methods.
5. `reproducibility.py` operates directly on `database.py` (bypasses recorder) for grade computation.
6. `row_data.py` and `formatters.py` are pure value/utility modules with no dependencies on other landscape modules.

---

## 4. External Dependencies

### What landscape/ imports from other subsystems:

| Dependency | Files Using It | Purpose |
|-----------|---------------|---------|
| `elspeth.contracts` (audit, enums, errors, schema_contract) | All mixin files, repositories, exporter, lineage, __init__ | Domain model types, enum definitions, error types |
| `elspeth.core.canonical` (canonical_json, stable_hash, repr_hash) | _run_recording, _graph_recording, _node_state_recording, _token_recording, _call_recording, _error_recording, exporter | Hashing and serialization |
| `elspeth.contracts.payload_store` (PayloadStore protocol) | recorder, _call_recording, _node_state_recording, _token_recording, _run_recording, _query_methods | Payload persistence |
| `elspeth.core.payload_store` (FilesystemPayloadStore) | journal.py | Payload enrichment for journal |
| `sqlalchemy` | database, schema, all mixins, _database_ops | Database operations |

### Who depends on landscape/

| Consumer | What It Imports | How It Uses It |
|----------|----------------|---------------|
| `engine/orchestrator/core.py` | `LandscapeDB`, `LandscapeRecorder` | Creates DB, recorder; delegates all audit recording |
| `engine/processor.py` | `LandscapeRecorder` | Records node states, routing, token outcomes during traversal |
| `engine/executors/*` | `LandscapeRecorder` | Records calls, artifacts, errors during execution |
| `engine/tokens.py` | `LandscapeRecorder` | Token lifecycle (fork, coalesce, expand) |
| `engine/coalesce_executor.py` | `LandscapeRecorder` | Coalesce barrier operations |
| `plugins/clients/*` | `LandscapeRecorder` | Call recording for HTTP/LLM clients |
| `plugins/llm/*` | `LandscapeRecorder` | Call recording for LLM plugins |
| `plugins/transforms/azure/*` | `LandscapeRecorder` | Call recording for safety transforms |
| `mcp/analyzer.py`, `mcp/analyzers/*` | `LandscapeDB`, `LandscapeRecorder`, schema tables | Read-only analysis of audit data |
| `cli.py` | `LandscapeDB`, `LandscapeRecorder`, `explain` | CLI commands for explain, status, purge |
| `tui/*` | `LandscapeDB`, `LandscapeRecorder` | TUI explain screen |
| `core/retention/purge.py` | `update_grade_after_purge`, schema tables, `LandscapeDB` | Payload purge with grade degradation |
| `core/checkpoint/*` | `LandscapeDB`, `LandscapeRecorder`, schema tables | Checkpoint persistence and recovery |
| `core/dag/models.py` | `NODE_ID_COLUMN_LENGTH` | DAG node ID length validation |
| `contracts/plugin_context.py` | `LandscapeRecorder` | Plugin context type annotation |
| `core/operations.py` | `LandscapeRecorder` | Operation tracking type annotation |

**Observation:** Landscape is the most widely imported subsystem in the codebase. Nearly every subsystem depends on it either for recording (write path) or querying (read path). The `LandscapeRecorder` is the dominant API surface.

---

## 5. Architectural Patterns

### 5.1. Dominant Patterns

1. **Mixin Composition:** The recorder is split into 8 focused files joined by multiple inheritance. State is shared through implicit attribute annotations.

2. **Repository Pattern:** 14 repository classes handle the SQLAlchemy-row-to-dataclass conversion, centralizing Tier 1 validation (enum conversion, invariant checks).

3. **Tier 1 Crash-on-Anomaly:** Throughout the subsystem, invalid audit data causes immediate crashes via `ValueError`, `AuditIntegrityError`, or `FrameworkBugError`. No coercion, no defaults, no silent recovery.

4. **Canonical Hashing:** All data written to the audit trail is hashed via RFC 8785 canonical JSON (`stable_hash`). Hashes survive payload deletion.

5. **Denormalized run_id:** Multiple tables carry a denormalized `run_id` to enable efficient filtering without joining through the composite PK on `nodes`.

6. **Composite Primary Keys/Foreign Keys:** The `nodes` table uses `(node_id, run_id)` as PK, with composite FKs propagated to dependent tables.

7. **Batch Query Optimization:** Both the exporter and lineage modules use batch queries (pre-load all data, then iterate in memory) to avoid N+1 patterns.

8. **Transaction Atomicity:** Fork and expand operations use explicit `self._db.connection()` blocks to ensure children + parent outcome are recorded atomically.

### 5.2. Notable Deviations

1. **Operations bypass repository pattern:** The `Operation` model is constructed inline in `_call_recording.py` rather than through a repository class.

2. **Some methods bypass DatabaseOps:** `record_routing_events()`, `fork_token()`, `coalesce_tokens()`, `expand_token()` use `self._db.connection()` directly for multi-statement transactions. `complete_operation()` reaches into `self._ops._db`.

3. **Secret resolutions use untyped dicts:** `record_secret_resolutions()` accepts `list[dict[str, Any]]` rather than a typed dataclass.

---

## 6. Concerns and Recommendations (Ranked by Severity)

### P2 (High) -- Should be addressed in RC3.3

1. **Untyped dict at Tier 1 boundary in `record_secret_resolutions()`** (`_run_recording.py:388-417`): Accepts `list[dict[str, Any]]` and destructures with string keys. Per the open bug pattern in MEMORY.md, this should be a frozen dataclass. A typo in a key name would silently fail or crash at runtime with an unhelpful KeyError.

2. **Missing `OperationRepository`** (`_call_recording.py:426-440, 466-483`): Operations are constructed inline from DB rows without enum validation. If `operation_type` or `status` contains an invalid value, it will not be caught at deserialization. All other models use repositories with Tier 1 validation.

3. **`in_memory()` and `from_url()` bypass `__init__`** (`database.py:388-473`): Both factory methods use `cls.__new__()` and manually set attributes. Adding a new instance variable to `__init__` requires remembering to update two other methods. A refactoring to use a shared `_initialize()` method would eliminate this risk.

4. **Non-atomic journal writes** (`journal.py:152`): File writes without fsync or atomic rename. Documented known issue but worth tracking.

5. **Exporter outputs `dict[str, Any]` without typed records** (`exporter.py`): Every export record is an untyped dict. For an audit subsystem where correctness is paramount, TypedDict or dataclass export records would provide compile-time safety.

### P3 (Medium) -- Worth addressing but not blocking

6. **Truthiness checks for filter parameters** (`_batch_recording.py:239-240, 462-463`): `if status:` and `if node_id:` should be `if status is not None:` and `if node_id is not None:`. An empty string or zero-value enum would be silently ignored.

7. **Mixin anti-pattern with shared state** (`recorder.py`): Mixins share state through implicit attribute annotations. No compile-time verification that the recorder initializes what the mixins expect. Consider a protocol or explicit dependency injection.

8. **Unnecessary joins in batch queries** (`_query_methods.py:311-318, 405-413`): `get_all_tokens_for_run()` and `get_all_token_parents_for_run()` join through rows when they could use the denormalized `tokens.run_id` or `tokens.run_id` respectively. This is the exact anti-pattern CLAUDE.md warns against (though here it's a performance issue rather than a correctness issue).

9. **Inconsistent error types:** Some Tier 1 violations raise `ValueError`, others raise `AuditIntegrityError`, and `_database_ops.py` uses `ValueError`. Should standardize on `AuditIntegrityError` for all audit integrity violations.

10. **Redundant ownership lookups in fork/coalesce** (`_token_recording.py`): `fork_token()` makes 2 DB queries for ownership validation that could be 1. `coalesce_tokens()` is O(2n) queries for n parents.

11. **`complete_operation()` breaks DatabaseOps encapsulation** (`_call_recording.py:278`): Accesses `self._ops._db` directly.

12. **Re-exported contract types in `__init__.py`**: Creates dual import paths. Consider exporting only landscape-owned types and letting consumers import contract types from `elspeth.contracts` directly.

### P4 (Low) -- Nice to have

13. **`coerce_enum()` in `_helpers.py` appears unused.** Candidate for removal.

14. **`batch_outputs_table` has no recorder support.** Schema exists but no repository or recorder methods. May be dead schema.

15. **Two separate DB connections in `compute_grade()`** (`reproducibility.py`). Could be consolidated into one.

---

## 7. Tier Model Compliance

### Tier 1 (Audit Data = Full Trust): **STRONG COMPLIANCE**

The subsystem demonstrates excellent Tier 1 adherence:

- **Crash on anomaly:** `NodeStateRepository.load()` validates 6+ invariants per status variant and crashes on any violation. `TokenOutcomeRepository.load()` validates `is_terminal` is exactly `int(0)` or `int(1)` and cross-checks against enum. `get_source_field_resolution()` validates every key and value type in the resolution mapping.

- **No coercion:** Enum values are converted via `EnumType(value)` which raises `ValueError` on invalid values. No fallback defaults.

- **Cross-run contamination prevention:** `_validate_token_run_ownership()`, `_validate_token_run_ownership_for_error()`, and `_validate_token_row_ownership()` crash on cross-run/cross-row mismatches. The `AuditIntegrityError` messages are detailed and diagnostic.

- **Hash integrity:** `get_run_contract()` verifies stored hash matches recomputed hash. `compute_grade()` validates all determinism values before computing.

### Tier 1 Violations Found:

1. **`record_secret_resolutions()` uses untyped dicts** -- String key access without validation is a weak point.
2. **Operations lack repository validation** -- `operation_type` and `status` are not validated through enum conversion at deserialization.
3. **Truthiness checks** -- `if status:` instead of `if status is not None:` could silently skip valid zero/empty values.
4. **Inconsistent error types** -- Some integrity violations use `ValueError` instead of `AuditIntegrityError`.

### Tier 3 (External Data = Zero Trust): **CORRECT HANDLING**

The subsystem correctly handles Tier 3 data at the ingestion boundary:

- `record_validation_error()` uses `repr_hash()` and `NonCanonicalMetadata` fallback for non-canonical row data.
- `create_row()` supports quarantined data with `repr_hash()` and JSON repr fallback for payload storage.
- `begin_node_state()` accepts `quarantined=True` for non-canonical input hashing.
- `record_transform_error()` wraps `error_details` serialization in try/except for non-canonical transform results.

---

## 8. Confidence Assessment

**Confidence: HIGH**

**Reasoning:**
- All 21 files were read in their entirety (11,681 lines total).
- The subsystem has clear architectural patterns (mixins, repositories, Tier 1 enforcement) that are consistently applied.
- The concerns identified are real but mostly P3/P4 -- the subsystem is fundamentally sound.
- The most significant issues (untyped dicts, missing OperationRepository, factory method bypass) are real architectural risks but have been stable in practice.
- The Tier 1 compliance is strong -- this is one of the most carefully hardened subsystems in the codebase.
- External dependency analysis confirms Landscape is the most widely imported subsystem, validating the "audit backbone" description.

The primary risk area is the gradual accumulation of P3 concerns (truthiness checks, inconsistent error types, unnecessary joins) that individually are minor but collectively create maintenance burden. The P2 issues (untyped dicts, missing OperationRepository) are concrete and should be addressed in RC3.3.
