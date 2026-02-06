# Analysis: src/elspeth/plugins/sinks/database_sink.py

**Lines:** 407
**Role:** Database output sink -- writes pipeline results to SQL databases via SQLAlchemy Core. Handles table creation, schema-to-column type mapping, replace/append modes, batch inserts, connection management, and audit trail recording with call-level granularity.
**Key dependencies:** `BaseSink` (plugins/base.py), `DataPluginConfig` (plugins/config_base.py), `PluginSchema` / `ArtifactDescriptor` / `CallStatus` / `CallType` (contracts), `SanitizedDatabaseUrl` (contracts/url.py), `canonical_json` / `stable_hash` (core/canonical.py), `create_schema_from_config` (plugins/schema_factory.py), `PluginContext` (plugins/context.py), SQLAlchemy Core (`create_engine`, `MetaData`, `Table`, `Column`, `insert`, `inspect`). Consumed by `SinkExecutor` (engine/executors.py).
**Analysis depth:** FULL

## Summary

DatabaseSink is the cleanest of the three sinks. It correctly hashes the canonical payload BEFORE the database insert (proving intent), properly records calls to the audit trail, and handles the replace/append modes. The most significant concern is that **`String` column type without length limits** could cause issues on MySQL/MSSQL (but works on PostgreSQL/SQLite). There is also a subtle issue with the `_ensure_table` method creating column definitions from the first row but never validating subsequent rows against those columns. Overall, this file is sound and production-ready with minor concerns.

## Critical Findings

### [302-308] Hash computed on full payload including empty batch -- unnecessary work

**What:** Lines 307-308 compute `content_hash` and `payload_size` via `stable_hash(rows)` and `canonical_json(rows)` BEFORE the empty-batch check at line 310. For empty batches, this performs two full canonical JSON serialization passes (one for hash, one for size) on an empty list, only to return immediately. While not a correctness issue, the double serialization of `rows` (once for hash, once for size) is also present for non-empty batches.

**Why it matters:** For non-empty batches, `canonical_json(rows)` is called twice: once via `stable_hash(rows)` internally and once explicitly at line 308. This doubles the serialization cost. For large batches with complex data, this could be a noticeable performance hit. For an emergency dispatch system processing high-frequency events, this matters.

**Evidence:**
```python
content_hash = stable_hash(rows)                          # Serializes rows to canonical JSON
payload_size = len(canonical_json(rows).encode("utf-8"))  # Serializes rows AGAIN
```

This is a performance issue, not a correctness issue. Both calls produce the same canonical representation, but the work is done twice.

## Warnings

### [30-36, 259, 282] All inferred columns default to `String` -- schema information loss

**What:** When schema is observed (line 257-259) or when falling back (line 281-282), all columns are created as `String` type regardless of actual data types. In flexible mode (line 273-277), extra columns beyond the declared schema are also `String`.

**Why it matters:** (1) Data stored as `String` loses type information -- integers, floats, and booleans are stored as their string representations. Downstream queries like `SELECT * FROM results WHERE amount > 100` would fail or produce wrong results because `amount` is stored as text. (2) For databases with strict typing (PostgreSQL), this means the database cannot enforce data integrity at the column level. For emergency dispatch data where numeric thresholds matter (severity levels, response times), storing numbers as strings defeats database-level validation.

**Evidence:**
```python
# Observed mode: all String
return [Column(key, String) for key in row]

# Flexible mode: extras as String
for key in row:
    if key not in declared_names:
        columns.append(Column(key, String))
```

### [30-36] `String` without length -- problematic for MySQL/MSSQL

**What:** SQLAlchemy `String` without a length argument maps to `VARCHAR` without a length limit. On PostgreSQL and SQLite this works fine (maps to `TEXT` or unbounded `VARCHAR`). On MySQL, `VARCHAR` requires a length and defaults to `VARCHAR(255)` which silently truncates data. On MSSQL, `VARCHAR` without length defaults to `VARCHAR(1)`.

**Why it matters:** If DatabaseSink is used with MySQL or MSSQL, data would be silently truncated. For emergency dispatch messages that exceed 255 characters, this is data loss. Using `Text` instead of `String` would be portable across all databases.

**Evidence:**
```python
SCHEMA_TYPE_TO_SQLALCHEMY: dict[str, type[TypeEngine[Any]]] = {
    "str": String,     # No length -- VARCHAR on MySQL truncates at 255
    "int": Integer,
    "float": Float,
    "bool": Boolean,
    "any": String,     # Same issue
}
```

### [195-227] `_ensure_table` creates table from first row's columns, no validation of subsequent rows

**What:** `_ensure_table` creates the table schema based on the first row it receives. Subsequent batches may have different columns (in observed or flexible mode), but the table schema is locked to whatever the first row contained. If a later batch has extra columns, `conn.execute(insert(self._table), rows)` will raise an `OperationalError` because the insert statement references columns that do not exist in the table.

**Why it matters:** In observed mode, the schema is supposed to "infer and lock" from the first row. If the source produces rows with varying column sets (e.g., optional fields present in some rows but not others), this will crash on the second batch if it has columns the first batch lacked. The error message from SQLAlchemy will be a raw database error, not a helpful ELSPETH error explaining the schema lock violation.

**Evidence:**
```python
def _ensure_table(self, row: dict[str, Any]) -> None:
    # ...
    if self._table is None:
        columns = self._create_columns_from_schema_or_row(row)
        self._table = Table(self._table_name, self._metadata, *columns)
        self._metadata.create_all(self._engine, checkfirst=True)
    # No validation that row's keys match self._table.columns for subsequent calls
```

### [213-216] Replace mode drops table only on first write -- stale table on subsequent instance creation

**What:** The `_table_replaced` flag prevents re-dropping the table on subsequent writes. But if `close()` is called (which sets `self._table = None`) and then `write()` is called again, `_ensure_table` will try to create the table again. Since `_table_replaced` is still True, it will NOT drop the existing table, so `create_all(checkfirst=True)` will find the table already exists and skip creation. This means the new instance inherits the old table schema even if the new data has different columns.

**Why it matters:** In a resume scenario or error recovery where the sink is closed and reopened, the replace mode semantics break silently. The table retains its old schema instead of being replaced.

**Evidence:**
```python
if self._if_exists == "replace" and not self._table_replaced:
    self._drop_table_if_exists()
    self._table_replaced = True
```
After `close()`, `self._table = None` but `self._table_replaced = True`. Next `_ensure_table` call skips the drop.

### [331-367] Insert failure records error but does not distinguish transient from permanent failures

**What:** The exception handler at line 351-367 catches all exceptions from the insert, records a `CallStatus.ERROR` to the audit trail, and re-raises. There is no distinction between transient failures (connection timeout, deadlock) and permanent failures (constraint violation, data too long). The re-raised exception propagates to the SinkExecutor which marks all token states as FAILED.

**Why it matters:** Transient database errors (which are common in production -- network blips, connection pool exhaustion, lock contention) should ideally be retried. Currently, a single transient error fails the entire batch permanently. For an emergency dispatch system, this means a momentary database hiccup could cause dispatch records to be marked as FAILED rather than retried.

## Observations

### [267] Direct dictionary key access on `field_def.field_type` without validation

**What:** `SCHEMA_TYPE_TO_SQLALCHEMY[field_def.field_type]` does a direct dictionary lookup. If `field_def.field_type` contains a value not in the map, this raises `KeyError`. The `FieldDefinition` Literal type constrains this to `{str, int, float, bool, any}`, and the map covers all five. This is correct behavior per CLAUDE.md -- if the type system is violated, it should crash.

### [99] Raw URL stored as `self._url`

**What:** `self._url = cfg.url` stores the raw database URL (potentially containing passwords) as an instance attribute. While `self._sanitized_url` is used for the audit trail, `self._url` persists in memory and could be exposed via debug logging, error messages, or memory dumps.

### [377-389] `flush()` is a no-op -- documented correctly

**What:** `flush()` does nothing because DatabaseSink commits within `write()` via `engine.begin()`. This is correct and well-documented. The comment about future enhancement (holding transaction open between write and flush) would be a significant architectural change.

### No display header support

**What:** Unlike CSVSink and JSONSink, DatabaseSink has no display header functionality. This is appropriate since database column names are identifiers, not display strings. The simpler design avoids the complexity and duplication issues present in the file-based sinks.

### No content hash re-read issue

**What:** Unlike CSVSink and JSONSink, DatabaseSink hashes the payload BEFORE writing to the database. This is the correct approach: hash the intent, not the result. The database may transform data (auto-increment, timestamps, etc.), so hashing the input is more semantically correct.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The double serialization (Critical finding) should be fixed by computing canonical JSON once and deriving both the hash and the size from the same serialized bytes. The `String` type mapping should be changed to `Text` for portability, or at minimum documented as SQLite/PostgreSQL-only. The replace-mode state management after close/reopen should be reviewed. The insert error handling should consider allowing the SinkExecutor or retry layer to distinguish transient from permanent database errors.
**Confidence:** HIGH -- all findings are based on direct code reading with full SQLAlchemy and dependency context. The type mapping issue is database-dialect-specific and could be a non-issue for SQLite-only deployments.
