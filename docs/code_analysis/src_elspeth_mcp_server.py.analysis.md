# Analysis: src/elspeth/mcp/server.py

**Lines:** 2,355
**Role:** MCP (Model Context Protocol) analysis server. Provides read-only access to the Landscape audit database via a JSON-RPC style API. Exposes 25 tools for querying pipeline runs, tokens, errors, performance, DAG structure, schema contracts, and emergency diagnostics. Intended for Claude Code sessions investigating pipeline failures. Also includes CLI entry point with auto-discovery of SQLite database files.
**Key dependencies:** `mcp.server` (MCP protocol), `elspeth.core.landscape.database.LandscapeDB`, `elspeth.core.landscape.recorder.LandscapeRecorder`, `elspeth.core.landscape.lineage.explain`, `elspeth.core.landscape.formatters.{dataclass_to_dict, serialize_datetime}`, `elspeth.contracts.enums.CallStatus`, SQLAlchemy Core. Imported by `tests/mcp/test_contract_tools.py`.
**Analysis depth:** FULL

## Summary

The file is generally well-structured and follows the composite-key join pattern documented in CLAUDE.md. The most significant concern is the SQL injection protection in `query()`, which relies on keyword-blocklist filtering that has known bypass vectors and false-positive issues. There are several N+1 query patterns, a code smell with `__import__` inline, a blanket exception handler at the tool dispatch level that silently converts all errors to text strings, and missing input validation for integer parameters that could cause resource exhaustion (unbounded `limit` values). Test coverage is narrow -- only the Phase 5 contract tools have tests; the remaining 22 tools (including `query()`) appear untested.

## Critical Findings

### [619-627] SQL injection protection relies on fragile keyword blocklist

**What:** The `query()` method validates SQL safety by uppercasing the input and checking `startswith("SELECT")`, then scanning for a list of 9 dangerous keywords. This approach has multiple weaknesses:

1. **Missing dangerous keywords for SQLite.** The blocklist omits `REPLACE`, `PRAGMA`, `ATTACH`, `DETACH`, `VACUUM`, and `REINDEX`. While these cannot appear as standalone statements since the input must start with `SELECT`, future changes to the execution mechanism or driver could alter this assumption.

2. **False positives on legitimate queries.** A query like `SELECT * FROM rows WHERE error LIKE '%DELETE%'` or `SELECT created_at FROM runs` (which contains `CREATE`) will be rejected because the keyword scan is a naive substring match on the uppercased SQL. The word `CREATE` appears inside `created_at`, and `UPDATE` appears inside `updated_at`. This makes the tool unreliable for querying tables with columns containing these substrings.

3. **No protection against resource exhaustion.** A `SELECT` with a `CROSS JOIN` producing a cartesian product on large tables, or a `WITH RECURSIVE` CTE generating infinite rows, will be executed without any timeout or row limit. The `fetchall()` call on line 634 will attempt to materialize the entire result set into memory.

**Why it matters:** The false positive on `created_at` containing `CREATE` means that basic queries against the `runs` table using that column will fail silently (well, with an error, but a confusing one). Users of the MCP tool will get `"Query contains forbidden keyword: CREATE"` for legitimate audit queries. The resource exhaustion vector could cause out-of-memory crashes for the MCP server process.

**Evidence:**
```python
# Line 619-627
sql_normalized = sql.strip().upper()
if not sql_normalized.startswith("SELECT"):
    raise ValueError("Only SELECT queries are allowed")

dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE"]
for keyword in dangerous:
    if keyword in sql_normalized:  # Substring match - matches inside identifiers
        raise ValueError(f"Query contains forbidden keyword: {keyword}")
```

The column `runs.created_at` uppercases to `CREATED_AT` which contains `CREATE`. The column `runs.export_status` or any query involving `UPDATE` as a substring (e.g., `updated_at`) would similarly fail. The word `ALTER` appears in `unaltered`, `DELETE` appears in `deleted_at`, etc.

**Mitigating factors:** The underlying safety is partially provided by the driver layer -- Python's `sqlite3` module rejects multi-statement execution in `cursor.execute()`, which prevents the most dangerous attack vector (appending destructive statements after a semicolon). SQLAlchemy's `text()` execution is similarly single-statement. The MCP server is also typically run locally by the developer, not exposed to untrusted network input. However, MCP clients (like Claude Code) pass through user-constructed queries, and the query tool is explicitly documented as accepting raw SQL.

### [2154-2155] Blanket exception handler silently converts all errors to success responses

**What:** The `call_tool` handler on line 2047-2155 wraps every tool invocation in a `try/except Exception` that converts any exception into a text response `"Error: {message}"`. The MCP protocol response is still a successful tool result (a `TextContent` list), not an error.

**Why it matters:** From the MCP client's perspective, every call succeeds. Database corruption, connection failures, schema mismatches, and `SchemaCompatibilityError` are all silently converted to text strings. This means:
- The client cannot programmatically distinguish between a successful query that returned "Error: ..." text and an actual error.
- Critical database integrity issues (which per CLAUDE.md Tier 1 trust should crash) are silently swallowed and presented as chat text.
- Stack traces are lost. Only `str(e)` is preserved, making debugging difficult.

**Evidence:**
```python
# Line 2154-2155
except Exception as e:
    return [TextContent(type="text", text=f"Error: {e!s}")]
```

This catches `SchemaCompatibilityError`, `sqlalchemy.exc.OperationalError` (database locked, corrupt), `sqlite3.DatabaseError`, and all other exceptions uniformly. The MCP protocol supports error responses that would allow the client to distinguish errors from results.

## Warnings

### [1224] Inline `__import__("datetime")` is a code smell

**What:** The `diagnose()` method uses `__import__("datetime").timedelta(hours=1)` inline within a SQLAlchemy expression, despite `datetime` already being imported at the top of the file and `timedelta` being imported locally at line 1482 in `get_recent_activity()`.

**Why it matters:** This is functionally correct but violates the project's code clarity standards. The `datetime` module is already imported at line 20. `timedelta` can be imported from there. The `__import__()` call is unusual in application code, harder to read, and adds cognitive overhead during review. It also means static analysis tools cannot track the `timedelta` dependency.

**Evidence:**
```python
# Line 1224
.where(operations_table.c.started_at < (datetime.now(UTC) - __import__("datetime").timedelta(hours=1)))
```

### [1507-1519] N+1 query pattern in `get_recent_activity()`

**What:** After fetching the list of recent runs (one query), the method loops over each run and executes 2 additional queries per run (count rows, count node states). For N recent runs, this executes 1 + 2N queries.

**Why it matters:** While the time window typically limits results, there is no `LIMIT` on the runs query (line 1496-1505). If a high-frequency pipeline creates many runs in the time window (or if `minutes` is set to a large value), this could result in hundreds of queries. The data could be fetched in 2-3 queries using GROUP BY with JOINs.

**Evidence:**
```python
# Lines 1507-1519
run_stats = []
for run in recent_runs:
    row_count = (
        conn.execute(select(func.count()).select_from(rows_table).where(rows_table.c.run_id == run.run_id)).scalar() or 0
    )
    state_count = (
        conn.execute(
            select(func.count()).select_from(node_states_table).where(node_states_table.c.run_id == run.run_id)
        ).scalar()
        or 0
    )
```

### [60-65] Docstring status values disagree with RunStatus enum

**What:** The `list_runs()` docstring says status filter accepts `(PENDING, RUNNING, COMPLETED, FAILED)` but `RunStatus` enum only defines `RUNNING`, `COMPLETED`, `FAILED`. There is no `PENDING` value. The tool's JSON schema (line 1744) correctly lists `["running", "completed", "failed"]` without pending.

Similarly, `get_node_states()` docstring (line 548) says `(PENDING, RUNNING, COMPLETED, FAILED)` but `NodeStateStatus` defines `OPEN, PENDING, COMPLETED, FAILED` -- no `RUNNING`. The tool schema (line 1884) correctly lists `["open", "pending", "completed", "failed"]`.

**Why it matters:** A developer reading the docstring and not the tool schema would pass incorrect filter values. The validation would reject them at runtime, but the error message would be confusing since the docstring gave wrong guidance.

### [47-53] `LandscapeAnalyzer.__init__` creates a `LandscapeRecorder` for a read-only use case

**What:** The constructor instantiates a `LandscapeRecorder`, which is the class designed for writing audit records to the database. While the analyzer only calls read methods on it (`get_run`, `get_nodes`, `get_edges`, `get_calls`, `get_run_contract`), the recorder also holds write capabilities that are never used.

**Why it matters:** This is a minor design concern. The `LandscapeRecorder` might hold resources or establish connection patterns optimized for writes. More importantly, there is no enforcement that the analyzer only performs reads. A future change to the analyzer that accidentally calls a write method on the recorder would silently succeed, potentially corrupting the audit trail of a production database being examined.

### [1290-1296] `diagnose()` counts quarantined outcomes across ALL runs, not just recent ones

**What:** The quarantined count query on line 1291-1295 has no `run_id` filter and no time-based filter, unlike the other diagnostic queries which are scoped to recent/failed runs. It counts all quarantined outcomes in the entire database.

**Why it matters:** Over time, the quarantine count will accumulate and always be non-zero, making this diagnostic less useful. The "INFO" severity message "N row(s) have been quarantined across all runs" becomes noise rather than signal, since it reports historical quarantines from long-completed runs alongside genuinely new problems.

**Evidence:**
```python
# Line 1291-1295
quarantined_count = (
    conn.execute(
        select(func.count(token_outcomes_table.c.outcome_id)).where(token_outcomes_table.c.outcome == "quarantined")
    ).scalar()
    or 0
)
```

### [No limit validation] Integer parameters accept arbitrarily large values

**What:** Parameters like `limit`, `offset`, and `minutes` are accepted as integers from the MCP client without upper-bound validation. A client could pass `limit=999999999` or `minutes=525600` (one year), causing the server to attempt to materialize massive result sets or scan the entire database.

**Why it matters:** While the MCP server is typically used locally, unbounded queries can cause memory exhaustion or long-running locks on the SQLite database. The `fetchall()` pattern used throughout means results are fully materialized in memory before serialization.

### [2047-2155] Tool dispatch uses long if/elif chain instead of registry pattern

**What:** The `call_tool` async handler is a 100-line if/elif chain mapping tool names to method calls. Adding a new tool requires changes in three places: the `LandscapeAnalyzer` class (method), `list_tools` (schema), and `call_tool` (dispatch).

**Why it matters:** This is a maintainability concern. If a tool is added to `list_tools` but not to `call_tool`, it will silently return "Unknown tool" instead of raising an error at startup. The three-location update requirement increases the chance of such inconsistencies.

## Observations

### [56-58] `LandscapeAnalyzer.close()` is defined but never called

The `close()` method delegates to `self._db.close()` to dispose of the engine, but the `create_server()` function on line 1718 creates the analyzer without any cleanup mechanism. The MCP server runs until the process exits, so the SQLAlchemy engine's connection pool is never explicitly disposed. For SQLite this is benign (connections are just file handles), but for PostgreSQL it would leak connection pool resources.

### [39-41] Module-level aliases for imported functions serve no purpose

Lines 39-41 create `_serialize_datetime` and `_dataclass_to_dict` as module-level aliases to `serialize_datetime` and `dataclass_to_dict` respectively. These aliases are used throughout the file instead of the original names. The original names would work identically and are already imported.

### Test coverage gap

Only `tests/mcp/test_contract_tools.py` exists, covering `get_run_contract`, `explain_field`, and `list_contract_violations` (3 of 25 tools). The remaining 22 tools -- including the security-critical `query()` tool, the emergency `diagnose()` tool, and all core query tools -- have no test coverage. The false-positive keyword blocking issue in `query()` would likely have been caught with basic tests using column names like `created_at`.

### [680-683] Mermaid diagram generation truncates node IDs, creating potential collisions

Node IDs are truncated to 8 characters for the Mermaid diagram (lines 680, 683). If two nodes share the same 8-character prefix (plausible for UUID-based IDs that share timestamp prefixes), the diagram will contain ambiguous references. This would produce a visually incorrect diagram.

### [632] `connection()` auto-commits read-only transactions

The `connection()` context manager uses `engine.begin()` which auto-commits on successful exit. For pure SELECT queries, this means an implicit COMMIT is issued after every read operation. In SQLite WAL mode this is harmless, but it is semantically unusual for a read-only API.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The SQL keyword blocklist in `query()` needs to be replaced with a word-boundary-aware check (e.g., regex `\bCREATE\b`) to eliminate false positives on column names like `created_at`. The blanket exception handler in `call_tool` should at minimum log the full traceback and ideally distinguish between expected errors (ValueError for bad input) and unexpected errors (database corruption). The `get_recent_activity()` N+1 pattern should be refactored to use JOINs. Test coverage for the core 22 tools is absent and should be added before release, particularly for `query()` where the current implementation demonstrably breaks on standard audit table columns. The `__import__` on line 1224 should be replaced with a normal import.
**Confidence:** HIGH -- All findings are based on direct code analysis with verified understanding of the SQLAlchemy execution model, SQLite driver behavior, and the project's enum definitions. The `CREATE`-in-`created_at` false positive is deterministic and reproducible.
