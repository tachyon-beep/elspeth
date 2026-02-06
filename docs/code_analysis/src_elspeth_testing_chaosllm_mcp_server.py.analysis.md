# Analysis: src/elspeth/testing/chaosllm_mcp/server.py

**Lines:** 1,071
**Role:** MCP (Model Context Protocol) server providing Claude-optimized read-only analysis tools for ChaosLLM metrics databases. Exposes tools like `diagnose`, `analyze_aimd_behavior`, `analyze_errors`, `analyze_latency`, `find_anomalies`, drill-down tools, and raw SQL query access. Designed to run as a stdio MCP server for AI-assisted investigation of ChaosLLM test results.
**Key dependencies:** Imports `mcp.server.Server`, `mcp.server.stdio.stdio_server`, `mcp.types.TextContent`/`Tool` for MCP protocol. Uses `sqlite3` directly (not SQLAlchemy). No imports from main ELSPETH codebase -- this is a standalone analysis server.
**Analysis depth:** FULL

## Summary

The file implements a clean read-only analysis server with good tool design for LLM consumption. The main concerns are: (1) a SQL injection bypass in the `query()` method's keyword blocklist approach, (2) database connection lifecycle issues (no cleanup on server shutdown), and (3) potential unbounded memory consumption when loading all latencies into memory. The analysis logic itself is statistically sound and well-organized. Confidence is HIGH for the security findings and MEDIUM for the resource exhaustion concerns (depends on dataset size in practice).

## Critical Findings

### [721-737] SQL injection bypass via keyword blocklist is insufficient

**What:** The `query()` method attempts to restrict SQL to read-only SELECT statements by checking `sql_normalized.startswith("SELECT")` and then scanning for dangerous keywords like INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE. This blocklist approach has multiple bypass vectors:

1. **ATTACH DATABASE**: Not in the blocklist. `SELECT 1; ATTACH DATABASE '/tmp/evil.db' AS evil` would pass the SELECT check. SQLite's `ATTACH` can create new database files on disk.
2. **Subquery exploitation**: Keywords inside string literals or identifiers could cause false positives (e.g., `SELECT * FROM requests WHERE endpoint LIKE '%UPDATE%'` is rejected despite being a valid read-only query). Conversely, SQL comments could hide mutations.
3. **PRAGMA abuse**: `PRAGMA` is not in the blocklist. While most PRAGMAs are read-only, some like `PRAGMA journal_mode=DELETE` or `PRAGMA wal_checkpoint` can modify database state.
4. **SQLite-specific**: `REPLACE` and `UPSERT` are not blocked. Though they require INSERT context, the blocklist is fragile.

**Why it matters:** This is an MCP server designed to be called by an AI assistant. If the AI is given arbitrary tool access, a prompt injection attack or confused-deputy scenario could craft SQL that bypasses the blocklist. For a testing/analysis tool the blast radius is limited (only the metrics database is exposed), but the pattern is dangerous if copied to higher-trust contexts.

**Evidence:** Lines 722-730 implement the blocklist:
```python
sql_normalized = sql.strip().upper()
if not sql_normalized.startswith("SELECT"):
    raise ValueError("Only SELECT queries are allowed")
dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
for keyword in dangerous:
    if keyword in sql_normalized:
        raise ValueError(f"Query contains forbidden keyword: {keyword}")
```
The keyword check is a substring match on the uppercased SQL, which catches keywords inside string literals and identifiers (false positives) but misses ATTACH, PRAGMA, and potential future SQLite mutations.

### [46-51] Database connection is never closed on server shutdown

**What:** The `ChaosLLMAnalyzer.__init__()` stores `self._conn = None` and lazily creates a connection in `_get_connection()`. The `close()` method exists (lines 53-57) but is never called by `create_server()`, `run_server()`, or `main()`. When the MCP server exits (e.g., stdio EOF), the connection is abandoned without being closed.

**Why it matters:** Abandoned SQLite connections can leave WAL files and shared-memory files (`.db-wal`, `.db-shm`) on disk, and in rare cases can cause database locking issues. For a read-only analysis tool this is low-severity, but it is a resource leak.

**Evidence:** `create_server()` (line 798) creates `analyzer = ChaosLLMAnalyzer(database_path)` but never registers cleanup. `run_server()` (line 968) uses `async with stdio_server()` but has no teardown for the analyzer. The `close()` method on line 53 exists but is orphaned.

## Warnings

### [370-381] Percentile calculation loads all latencies into memory

**What:** `analyze_latency()` executes `SELECT latency_ms FROM requests WHERE latency_ms IS NOT NULL ORDER BY latency_ms` and loads all results into a Python list (line 372). For large test runs with millions of requests, this could consume significant memory.

**Why it matters:** ChaosLLM is a load testing tool. A stress test might generate hundreds of thousands or millions of requests. Loading all latency values into a Python list for percentile calculation could cause memory pressure or OOM in the MCP server process. SQLite can handle the sort efficiently, but pulling all rows into Python is the bottleneck.

**Evidence:** Line 371-372:
```python
cursor = conn.execute("SELECT latency_ms FROM requests WHERE latency_ms IS NOT NULL ORDER BY latency_ms")
latencies = [row["latency_ms"] for row in cursor.fetchall()]
```
This pattern also appears in `diagnose()` indirectly via time-series queries, but latency is the worst case because it is per-request rather than per-bucket.

### [378-381] Off-by-one in percentile indexing

**What:** The percentile calculation uses `int(n * 0.50)`, `int(n * 0.95)`, `int(n * 0.99)` to find indices. For a list of length 1, `int(1 * 0.50) = 0` which is correct. For length 100, `int(100 * 0.95) = 95` which accesses the 96th element (0-indexed), which is a reasonable p95 approximation. However, `int(100 * 0.99) = 99` which is the last element -- this is the max, not the p99. Line 381 applies `min(int(n * 0.99), n - 1)` as a bounds check for p99 but not for p50 or p95, creating inconsistent handling.

**Why it matters:** For small datasets (e.g., 10-20 requests), the percentile values will be crude approximations. For p95 with exactly 20 requests, `int(20 * 0.95) = 19` which is the max value, not p95. This is a known limitation of the nearest-rank method without interpolation, but the inconsistent bounds checking between p99 (has `min()` guard) and p50/p95 (no guard) could cause IndexError if the calculation somehow yielded an out-of-bounds index.

**Evidence:** Lines 378-381:
```python
p50 = latencies[int(n * 0.50)] if n > 0 else 0
p95 = latencies[int(n * 0.95)] if n > 0 else 0
p99 = latencies[min(int(n * 0.99), n - 1)] if n > 0 else 0
```
For `n > 0`, `int(n * 0.95)` could equal `n` when `n * 0.95` is exactly an integer (e.g., n=20), causing `latencies[20]` to be an IndexError on a 20-element list. However, `int(20 * 0.95) = 19` (since `20 * 0.95 = 19.0` and `int(19.0) = 19`), so this specific case is actually safe. The risk is when `n * 0.95` produces a value >= n due to floating-point, which would require very specific n values. The inconsistent guarding still suggests the author was aware of the risk for p99 but not for p95.

### [726-729] Keyword blocklist has false-positive problem

**What:** The dangerous keyword check uses `if keyword in sql_normalized`, which is a substring match. This means queries like `SELECT * FROM requests WHERE error_type = 'connection_stall_UPDATED'` or column aliases containing "DROP" would be incorrectly rejected.

**Why it matters:** Users trying to query for error types or endpoints that happen to contain blocklisted substrings will get confusing "forbidden keyword" errors. For example, querying for `endpoint LIKE '%create%'` would be rejected because "CREATE" appears in the uppercased string.

**Evidence:** Line 729: `if keyword in sql_normalized` does substring matching on the entire uppercased SQL string, not word-boundary matching.

### [929-963] Broad exception handler in call_tool suppresses all errors

**What:** The `call_tool()` handler wraps everything in `try/except Exception as e` (line 962) and returns the error as a text message. This means any bug in the analysis code (e.g., a KeyError, TypeError, or logic error) is silently converted to a user-facing "Error: ..." message instead of propagating as a proper MCP error.

**Why it matters:** During development and debugging of the MCP server itself, this catch-all suppresses stack traces and makes it difficult to identify the root cause of failures. A `sqlite3.OperationalError` from a corrupt database looks the same as a `TypeError` from a code bug.

**Evidence:** Lines 929-963:
```python
try:
    result: Any
    if name == "diagnose":
        result = analyzer.diagnose()
    # ... many elif branches ...
except Exception as e:
    return [TextContent(type="text", text=f"Error: {e!s}")]
```

### [452-462] find_anomalies() expected_codes set missing 403 and 404

**What:** The `expected_codes` set on line 452 is `{200, 429, 500, 502, 503, 504, 529}`. However, the ChaosLLM error injector can produce 403 (Forbidden) and 404 (Not Found) responses (see error_injector.py HTTP_ERRORS dict, lines 115-124). These would be flagged as "unexpected_status" anomalies when they are in fact configured error injections.

**Why it matters:** If a test run includes forbidden or not-found error injection, the anomaly detector will report false-positive "unexpected_status" anomalies for these expected codes. This reduces trust in the anomaly detection output.

**Evidence:** Line 452: `expected_codes = {200, 429, 500, 502, 503, 504, 529}`. Compare with error_injector.py line 115-124 `HTTP_ERRORS` which includes `"forbidden": 403` and `"not_found": 404`.

## Observations

### [29-57] ChaosLLMAnalyzer design is clean but not async

All analysis methods are synchronous, executing SQLite queries directly. Since the MCP tools are registered as async handlers but call synchronous analyzer methods, long-running queries (e.g., on large datasets) will block the asyncio event loop. For a single-user analysis tool this is acceptable, but worth noting if the server is ever used in a multi-client context.

### [975-1015] Database auto-discovery is well-implemented

The `_find_metrics_databases()` function uses sensible priority ordering (chaosllm+metrics > chaosllm > metrics > other), skips hidden directories, respects depth limits, and sorts by modification time. This is a good UX pattern for the CLI entry point.

### [798-965] MCP tool registration is comprehensive and well-structured

The tool definitions include clear descriptions, proper JSON schemas with required fields, and sensible defaults. The separation between high-level analysis tools and drill-down tools is well-organized for LLM consumption.

### [132-166] Pattern detection thresholds are hardcoded

The burst detection threshold (>50% rate limited), timeout cluster threshold (>10), and error diversity threshold (>=5 types) are all hardcoded. These are reasonable defaults for the current use case but cannot be tuned without code changes.

### [653-705] get_time_window() Unix timestamp to ISO conversion is correct

The `datetime.fromtimestamp(start_sec, tz=UTC).isoformat()` pattern is the correct way to convert Unix timestamps to ISO format for SQLite string comparison. The timezone handling is explicit and correct.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Replace the SQL keyword blocklist with a proper approach -- either use `sqlite3.connect(..., readonly=True)` (available in Python 3.12+ via URI mode `?mode=ro`) or wrap the connection in a read-only transaction with `BEGIN DEFERRED` and reject at the SQLite level. (2) Add 403 and 404 to the `expected_codes` set in `find_anomalies()`. (3) Register cleanup for the analyzer's database connection on server shutdown. (4) Consider using SQLite's built-in aggregation functions or sampling for percentile calculations on large datasets.
**Confidence:** HIGH for the SQL bypass and missing expected codes findings. MEDIUM for the memory/resource concerns (depends on actual test dataset sizes).
