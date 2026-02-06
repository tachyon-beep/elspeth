# Analysis: src/elspeth/core/landscape/database.py

**Lines:** 327
**Role:** Database connection management for the Landscape audit trail. Provides `LandscapeDB`, the class that wraps SQLAlchemy engine creation, SQLite configuration, schema validation, and table creation. Serves as the single entry point for all database access throughout the system.
**Key dependencies:** Imports `schema.metadata` for table creation, `LandscapeJournal` for JSONL backup streaming. Imported by `recorder.py`, `exporter.py`, `reproducibility.py`, `cli.py`, `mcp/server.py`, and `engine/__init__.py`. The `SchemaCompatibilityError` exception is re-exported from `__init__.py`.
**Analysis depth:** FULL

## Summary

The database module is well-structured with clear separation of concerns. The main risks are: (1) a missing SQLite `busy_timeout` PRAGMA that will cause `SQLITE_BUSY` failures under concurrent access in WAL mode, (2) the `in_memory()` factory bypasses `__init__` via `__new__`, creating a fragile maintenance path, and (3) the `_validate_schema` method's composite FK check will silently miss broken FK definitions when the source table does not yet exist. No data corruption risks found; the transactional model via `engine.begin()` is correct.

## Critical Findings

### [124-131] Missing SQLite busy_timeout PRAGMA -- concurrent access will fail

**What:** The `_configure_sqlite` method sets `journal_mode=WAL` and `foreign_keys=ON`, but does not set `busy_timeout`. SQLite's default busy timeout is 0 milliseconds, meaning any concurrent write attempt immediately raises `SQLITE_BUSY` (database is locked).

**Why it matters:** WAL mode was explicitly chosen for "better concurrency" (line 127 comment), but without `busy_timeout`, the concurrency benefit is largely negated. In production, the orchestrator writes audit records while the MCP analysis server or CLI tools may be reading/querying the same database. With busy_timeout=0, any timing overlap between a write transaction and a concurrent reader (even in WAL mode, where readers and one writer can proceed concurrently, but two writers cannot) will cause an immediate `OperationalError: database is locked`. The `DatabaseOps` methods do not catch or retry on this error, so the entire pipeline will crash.

This is especially dangerous during `export_run()` operations, which issue many read queries while the pipeline may still be running and writing audit records.

**Evidence:**
```python
# Lines 124-131 - no busy_timeout set
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

A `cursor.execute("PRAGMA busy_timeout=5000")` (5 seconds) would allow SQLite to wait and retry internally before raising the error. This is the standard recommendation when using WAL mode.

## Warnings

### [229-244] `in_memory()` bypasses `__init__` via `__new__`, creating fragile construction path

**What:** The `in_memory()` class method constructs a `LandscapeDB` instance by calling `cls.__new__(cls)` and manually setting attributes, completely bypassing `__init__`. The `from_url()` method at lines 247-299 does the same thing.

**Why it matters:** If any new attribute is added to `__init__`, both `in_memory()` and `from_url()` must be manually updated to set the same attribute. Missing an attribute will result in `AttributeError` at runtime when that attribute is accessed. This is the exact class of bug that the CLAUDE.md "Test Path Integrity" section warns about -- a manual construction path that can diverge from the production path.

Current state: `__init__` sets `self.connection_string`, `self._engine`, `self._journal`. Both `in_memory()` (lines 241-243) and `from_url()` (lines 280-282) set these same three attributes. The correspondence is maintained today, but it is fragile.

**Evidence:**
```python
# __init__ sets these:
self.connection_string = connection_string  # line 84
self._engine: Engine | None = None          # line 85
self._journal: LandscapeJournal | None = None  # line 86

# in_memory() manually sets:
instance.connection_string = "sqlite:///:memory:"  # line 241
instance._engine = engine                           # line 242
instance._journal = None                            # line 243
```

### [107] SQLite detection via string prefix is brittle

**What:** SQLite is detected by `self.connection_string.startswith("sqlite")` at lines 107, 147, and 275. This works for standard URLs like `sqlite:///path` but would fail for dialect-specific URLs like `sqlite+pysqlite:///path` or `sqlite+aiosqlite:///path`.

**Why it matters:** If a future deployment uses an alternative SQLite driver (e.g., `sqlite+pysqlite://`), the PRAGMA configuration (WAL, foreign_keys) would not be applied, silently degrading audit integrity. The `_derive_journal_path` method at line 305 correctly uses `make_url().drivername.startswith("sqlite")`, which handles dialect variants. The inconsistency means some code paths are more robust than others.

**Evidence:**
```python
# Brittle (line 107):
if self.connection_string.startswith("sqlite"):

# Robust (line 305):
if not url.drivername.startswith("sqlite"):
```

### [133-135] `_create_tables()` uses shared global `metadata` object

**What:** `_create_tables()` calls `metadata.create_all(self.engine)` where `metadata` is a module-level singleton from `schema.py`. In a process with multiple `LandscapeDB` instances (e.g., tests), all instances share the same `metadata` object.

**Why it matters:** SQLAlchemy `MetaData.create_all()` is safe to call with different engines (it inspects the target engine's existing tables). However, if table definitions are ever modified at runtime (which should not happen but is technically possible via the mutable `MetaData` object), all instances would be affected. This is a low-risk but architecturally fragile pattern.

### [96-97] Validation order: `_validate_schema()` runs before `_create_tables()`

**What:** In `__init__`, `_validate_schema()` is called at line 96 before `_create_tables()` at line 97. The comment says "Check BEFORE create_tables". This is intentional: validation catches stale schemas before `create_all` could partially succeed.

**Why it matters:** This ordering is correct and important. However, the validation at line 158 skips tables that don't exist yet ("Table will be created by create_all, skip"). This means a completely fresh database passes validation trivially, and validation only fires for databases that already have some tables. If a user has a database with *some* old tables but not all, the validation will only check the tables that exist. New tables will be created by `create_all`, but existing tables with missing columns will trigger `SchemaCompatibilityError`. This behavior is correct but worth understanding: validation is "stale database" detection, not "complete schema" verification.

### [170-182] FK validation may produce false negatives for tables not yet created

**What:** The FK validation loop at lines 170-182 checks `_REQUIRED_FOREIGN_KEYS` but skips tables that don't exist. If a stale database has (for example) the `validation_errors` table without the required FK to `nodes`, but the `nodes` table doesn't exist yet, the check would still fire correctly because it only checks the *source* table's FKs. However, if the source table (`validation_errors`) doesn't exist, the check is skipped entirely.

**Why it matters:** This is correct behavior (the table will be created with proper FKs by `create_all`), but it means validation cannot detect a scenario where `create_all` is called on a database that has *some* tables with incorrect FKs but the referenced table doesn't exist. This is an extremely unlikely edge case in practice.

## Observations

### [312-326] `connection()` context manager uses `engine.begin()` -- correct transactional semantics

The `connection()` method correctly uses `engine.begin()`, which provides auto-commit on clean exit and auto-rollback on exception. This is the recommended SQLAlchemy pattern for write-heavy workloads. Every database operation in the system (via `DatabaseOps`) uses this context manager, ensuring consistent transaction handling.

### [211-215] `close()` properly disposes the engine

The `close()` method calls `engine.dispose()` which closes all pooled connections. The `__exit__` method delegates to `close()`. This is correct resource management.

### [62-97] Constructor does I/O during `__init__`

The constructor performs database connection, schema validation, and table creation during `__init__`. This means construction can raise exceptions from any of these operations. This is acceptable for this use case (database initialization is a one-time setup operation), but it means the class cannot be constructed lazily.

### No PostgreSQL-specific configuration

The code configures SQLite (PRAGMAs) but provides no PostgreSQL-specific configuration (pool settings, statement timeout, etc.). The comment at line 141 says "PostgreSQL deployments are expected to use Alembic migrations." This is fine for RC-2 but will need attention for production deployments.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add `PRAGMA busy_timeout=5000` to `_configure_sqlite()` -- this is the most impactful fix and addresses a real production failure mode. (2) Consider refactoring `in_memory()` and `from_url()` to call `__init__` via a common internal initializer to avoid the attribute-setting divergence risk. (3) Standardize SQLite detection to use `make_url().drivername.startswith("sqlite")` consistently.
**Confidence:** HIGH -- The busy_timeout issue is a well-known SQLite concurrency problem and the code clearly does not set it. The `__new__` bypass pattern is directly observable. The string-prefix detection inconsistency is minor but provable.
