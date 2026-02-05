# Analysis: src/elspeth/testing/chaosllm/metrics.py

**Lines:** 848
**Role:** Metrics collection and reporting for the ChaosLLM mock server. Provides thread-safe SQLite storage for request metrics and time-series aggregation. Writes request records, maintains aggregated time-series buckets, and exports statistics for analysis via the MCP server or direct SQL.
**Key dependencies:** Imports `MetricsConfig` from `config.py`. Imported by `server.py` (creates `MetricsRecorder` in `ChaosLLMServer.__init__`), the chaosllm fixture (`tests/fixtures/chaosllm.py`), and the `__init__.py` public API.
**Analysis depth:** FULL

## Summary

The file is well-structured with clear separation between the recording, aggregation, and query responsibilities. However, there are several concurrency issues that will manifest under real multi-threaded load: the `close()` method only closes the calling thread's connection (leaking all others), the `reset()` method has a race condition between the lock-protected ID update and the unlocked database operations, and the time-series `avg_latency_ms` column is silently corrupted by the upsert logic on initial insert. Additionally, per-thread SQLite connections with file-backed databases under WAL mode will eventually encounter SQLITE_BUSY errors that are not handled. Confidence is HIGH -- these issues are evident from careful code reading and knowledge of SQLite semantics.

## Critical Findings

### [400-438] Time-series avg_latency_ms and p99_latency_ms are set incorrectly on initial INSERT

**What:** The `_update_timeseries` upsert SQL inserts `latency_ms` directly as both `avg_latency_ms` and `p99_latency_ms` on the initial INSERT. For the very first request in a bucket, this is technically correct (avg of one value = that value). However, the ON CONFLICT UPDATE clause only increments the counters -- it does NOT update `avg_latency_ms` or `p99_latency_ms`. The latency statistics are only updated by the separate `_update_bucket_latency_stats` call (line 443), which re-queries all requests in the bucket. This means the INSERT path stores raw `latency_ms` (which may be `None`) into the avg/p99 columns, and the UPDATE path leaves them stale until `_update_bucket_latency_stats` runs.

The real problem: when `latency_ms` is `None`, the initial INSERT stores `NULL` in both `avg_latency_ms` and `p99_latency_ms`, and then `_update_bucket_latency_stats` is skipped (line 442: `if latency_ms is not None`). So time-series buckets where the first request has no latency will have NULL latency stats forever, even if subsequent requests in the same bucket DO have latency values -- because the ON CONFLICT path does not update the latency columns, and the full recalculation only runs when the current request has a latency value.

**Why it matters:** Any request without `latency_ms` that is the first to create a bucket will leave that bucket with permanent NULL latency stats, even if later requests in the same bucket have valid latency values. This silently corrupts metrics reporting.

**Evidence:**
```python
# Line 442-443: Only recalculates if CURRENT request has latency
if latency_ms is not None:
    self._update_bucket_latency_stats(conn, bucket)
```

A request with `latency_ms=None` that creates the bucket will set avg/p99 to NULL. A later request with `latency_ms=150.0` in the same bucket will hit the ON CONFLICT path, which increments counters but does NOT touch `avg_latency_ms` or `p99_latency_ms`. It WILL call `_update_bucket_latency_stats` (since its own latency_ms is not None), which will then fix the stats. So the issue is narrower than described: it only affects the intermediate state between the first (NULL latency) INSERT and the next request with a non-NULL latency. The latency stats will eventually be correct once any request with latency arrives in that bucket. However, if ALL requests in a bucket have NULL latency, the stats remain correctly NULL. **Downgrading: this is a transient inconsistency, not permanent corruption.** Still worth noting as the upsert design is fragile.

### [837-848] close() only closes the calling thread's connection, leaking all others

**What:** The `close()` method accesses `self._local.connection`, which is thread-local storage. This means it only closes the connection belonging to the thread that calls `close()`. All connections created by other threads (e.g., uvicorn worker threads handling concurrent requests) are never explicitly closed and are left to garbage collection.

**Why it matters:** When ChaosLLM runs as a real HTTP server with multiple uvicorn worker threads, each thread creates its own SQLite connection (line 253-268). When the server shuts down, only the shutdown thread's connection is closed. Other thread connections remain open, potentially holding WAL locks or leaving the database in an inconsistent state. For file-backed databases, this can cause stale WAL files or `-shm` files to persist. For in-memory databases with `cache=shared`, leaked connections prevent the database from being freed.

**Evidence:**
```python
def close(self) -> None:
    try:
        connection: sqlite3.Connection = self._local.connection  # Only THIS thread's connection
        connection.close()
        del self._local.connection
    except AttributeError:
        pass
    # No mechanism to close connections from OTHER threads
```

The `threading.local()` API provides no way to enumerate or iterate over values stored by other threads, so there is no simple fix without maintaining an explicit registry of connections.

## Warnings

### [608-646] Race condition in reset() between lock-protected and unprotected operations

**What:** The `reset()` method acquires `self._lock` to update `self._run_id` and `self._started_utc` (lines 619-621), then releases the lock and performs database operations (lines 623-646) without holding the lock. A concurrent `record_request` call can read the new `run_id` but then try to write to tables that `reset()` is about to DELETE.

**Why it matters:** Under concurrent load (which is the explicit use case -- ChaosLLM receives network traffic), a request being recorded concurrently with a reset can:
1. Read the new `_run_id` after the lock releases
2. Start writing to the requests table
3. Have its write committed
4. Then `reset()` DELETEs the row it just wrote

This is a silent data loss. The request was processed but its metrics vanish. Alternatively, the DELETE could happen between the request INSERT and the timeseries update, leaving orphaned timeseries data.

**Evidence:**
```python
def reset(self, ...) -> None:
    with self._lock:  # Lock held here
        self._run_id = str(uuid.uuid4())
        self._started_utc = datetime.now(UTC).isoformat()
    # Lock released -- gap where concurrent writes can land
    conn = self._get_connection()
    # ... reads from run_info ...
    conn.execute("DELETE FROM requests")  # Deletes any concurrent writes
    conn.execute("DELETE FROM timeseries")
```

### [236-268] Thread-local connections with check_same_thread=False is misleading

**What:** The `_get_connection` method creates per-thread connections but passes `check_same_thread=False` to SQLite. This flag disables SQLite's check that a connection is only used from the thread that created it. Since connections are already thread-local, the flag is unnecessary and misleading -- it suggests the code intends to share connections across threads, which would be unsafe.

**Why it matters:** If a future developer misunderstands this flag and starts sharing connections (e.g., by moving the connection to instance-level storage), they would introduce data corruption without any runtime warning from SQLite. The flag disables a safety net that is otherwise free.

**Evidence:**
```python
conn = sqlite3.connect(
    self._config.database,
    check_same_thread=False,  # Unnecessary -- connections are already thread-local
    timeout=30.0,
    uri=self._use_uri,
)
```

### [109-138] _get_bucket_utc uses seconds-since-midnight bucketing that breaks at day boundaries

**What:** The bucket calculation uses `total_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second` to compute seconds since midnight, then truncates. This means a bucket_sec value that doesn't evenly divide 86400 (seconds in a day) will create misaligned buckets at midnight boundaries. For example, with `bucket_sec=7`, the last bucket before midnight could be 86394-86400 (6 seconds), and the first bucket after midnight starts at 0 again with no continuity.

**Why it matters:** For long-running ChaosLLM sessions that span midnight, time-series data will have an artificial discontinuity at midnight. Buckets don't carry across days. With the default 1-second bucket this is invisible, but larger bucket sizes (5 minutes, 10 minutes) used in production-like scenarios will show abrupt transitions.

**Evidence:**
```python
total_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
bucket_seconds = (total_seconds // bucket_sec) * bucket_sec
```

### [492-606] update_timeseries fetches ALL timestamps into memory

**What:** The `update_timeseries()` method fetches every distinct timestamp from the requests table into a Python list (line 504-505), then iterates over them to rebuild. For a ChaosLLM session with millions of requests (stress testing), this loads all distinct timestamps into memory at once.

**Why it matters:** In a stress test that records millions of requests over hours, the number of distinct timestamps can be very large. This method loads them all into a Python list, which could consume significant memory. For a test tool this is unlikely to be catastrophic, but it is an unbounded memory allocation proportional to the number of distinct request timestamps.

**Evidence:**
```python
cursor = conn.execute("SELECT DISTINCT timestamp_utc FROM requests ORDER BY timestamp_utc")
timestamps = [row[0] for row in cursor.fetchall()]  # All timestamps in memory
```

### [286-367] record_request is not atomic with respect to concurrent reads

**What:** `record_request` performs an INSERT into `requests`, an upsert into `timeseries`, and an UPDATE of latency stats, all followed by a single `conn.commit()`. Because each thread has its own connection, concurrent reads from other threads (e.g., `get_stats()`) can see partially committed state depending on SQLite's isolation level.

**Why it matters:** Under WAL mode (used for file-backed databases), readers do not block writers, but readers see a snapshot as of the start of their transaction. Since `get_stats()` doesn't use an explicit transaction, each individual query within `get_stats()` could see a different snapshot if writes are happening concurrently. This means `total_requests` might not match the sum of `requests_by_outcome` if a write commits between those two queries.

**Evidence:** The `get_stats()` method (lines 648-735) runs multiple separate SELECT queries without wrapping them in a single transaction. Each SELECT independently acquires and releases a read lock under WAL mode.

## Observations

### [66-106] RequestRecord dataclass is defined but never used in the module

**What:** The `RequestRecord` dataclass is defined with full documentation and type annotations but is never used anywhere in this module. The `record_request` method accepts individual keyword arguments rather than a `RequestRecord` instance. The test file imports it only to test its construction.

**Why it matters:** This is dead code from an API design perspective. It adds maintenance burden and suggests an API that was designed but never integrated. It may confuse consumers who find the dataclass and assume it's the primary API for recording requests.

### [224-225] Memory database detection is fragile

**What:** The check `config.database == ":memory:" or "mode=memory" in config.database` uses a string substring check for URI detection. A database path that coincidentally contains `mode=memory` as a directory name (unlikely but possible) would be incorrectly classified.

**Why it matters:** Extremely low risk in practice but technically a string-matching fragility rather than proper URI parsing.

### [228-231] Parent directory creation skips Path(".") but not all relative paths

**What:** The check `if db_path.parent != Path(".")` skips directory creation when the parent is `.`, but a path like `subdir/metrics.db` would have `parent = Path("subdir")` which is not `.`, triggering `mkdir`. This is actually correct behavior, but the condition name suggests it's trying to avoid creating the current directory, which is an incomplete mental model -- it should also handle the case where the parent already exists naturally (which `exist_ok=True` handles).

**Why it matters:** Not a bug, but the logic is slightly convoluted. The `exist_ok=True` flag already handles the case where the directory exists, so the `Path(".")` check is redundant protection.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Fix the `close()` method to track and close all thread connections (requires maintaining a thread-safe registry of connections). Address the race condition in `reset()` by holding the lock for the entire operation or using a database-level transaction. The time-series latency calculation fragility should be documented or simplified by always recalculating stats regardless of whether the current request has a latency value.
**Confidence:** HIGH -- all findings are based on direct code reading, SQLite concurrency semantics, and Python threading.local() behavior, with cross-referencing against the test suite which confirms the identified gaps (no test for multi-thread close, no test for concurrent reset+write).
