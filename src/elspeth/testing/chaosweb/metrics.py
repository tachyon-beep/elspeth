# src/elspeth/testing/chaosweb/metrics.py
"""Metrics storage and aggregation for ChaosWeb server.

Thread-safe SQLite storage for request metrics and time-series aggregation.
Adapted from ChaosLLM's metrics.py with web-specific fields: content_type,
encoding, redirect tracking, and web-centric outcome classification.
"""

import contextlib
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from elspeth.testing.chaosllm.config import MetricsConfig

# SQLite schema for web metrics tables.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    request_id TEXT PRIMARY KEY,
    timestamp_utc TEXT NOT NULL,
    path TEXT NOT NULL,
    outcome TEXT NOT NULL,
    status_code INTEGER,
    error_type TEXT,
    injection_type TEXT,
    latency_ms REAL,
    injected_delay_ms REAL,
    content_type_served TEXT,
    encoding_served TEXT,
    redirect_target TEXT,
    redirect_hops INTEGER
);

CREATE TABLE IF NOT EXISTS timeseries (
    bucket_utc TEXT PRIMARY KEY,
    requests_total INTEGER NOT NULL DEFAULT 0,
    requests_success INTEGER NOT NULL DEFAULT 0,
    requests_rate_limited INTEGER NOT NULL DEFAULT 0,
    requests_forbidden INTEGER NOT NULL DEFAULT 0,
    requests_not_found INTEGER NOT NULL DEFAULT 0,
    requests_server_error INTEGER NOT NULL DEFAULT 0,
    requests_connection_error INTEGER NOT NULL DEFAULT 0,
    requests_malformed INTEGER NOT NULL DEFAULT 0,
    requests_redirect INTEGER NOT NULL DEFAULT 0,
    avg_latency_ms REAL,
    p99_latency_ms REAL
);

CREATE TABLE IF NOT EXISTS run_info (
    run_id TEXT PRIMARY KEY,
    started_utc TEXT NOT NULL,
    config_json TEXT NOT NULL,
    preset_name TEXT
);

CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_requests_outcome ON requests(outcome);
CREATE INDEX IF NOT EXISTS idx_requests_path ON requests(path);
"""


def _get_bucket_utc(timestamp_utc: str, bucket_sec: int) -> str:
    """Calculate the time bucket for a given timestamp."""
    dt = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
    total_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
    bucket_seconds = (total_seconds // bucket_sec) * bucket_sec
    bucket_dt = dt.replace(
        hour=bucket_seconds // 3600,
        minute=(bucket_seconds % 3600) // 60,
        second=bucket_seconds % 60,
        microsecond=0,
    )
    return bucket_dt.isoformat()


def _classify_web_outcome(
    outcome: str,
    status_code: int | None,
    error_type: str | None,
) -> tuple[bool, bool, bool, bool, bool, bool, bool, bool]:
    """Classify an outcome for web time-series aggregation.

    Returns:
        Tuple of booleans: (success, rate_limited, forbidden, not_found,
        server_error, connection_error, malformed, redirect)
    """
    is_success = outcome == "success"
    is_rate_limited = status_code == 429
    is_forbidden = status_code == 403
    is_not_found = status_code == 404
    is_server_error = status_code is not None and 500 <= status_code < 600
    is_connection_error = status_code is None and error_type in (
        "timeout",
        "connection_reset",
        "connection_stall",
    )
    is_malformed = outcome == "error_malformed"
    is_redirect = outcome == "error_redirect"

    return (
        is_success,
        is_rate_limited,
        is_forbidden,
        is_not_found,
        is_server_error,
        is_connection_error,
        is_malformed,
        is_redirect,
    )


class WebMetricsRecorder:
    """Thread-safe SQLite metrics recorder for ChaosWeb.

    Mirrors ChaosLLM's MetricsRecorder with web-specific fields and
    classification (forbidden/not_found/redirect instead of
    capacity_error/client_error).
    """

    def __init__(
        self,
        config: MetricsConfig,
        *,
        run_id: str | None = None,
    ) -> None:
        self._config = config
        self._run_id = run_id if run_id is not None else str(uuid.uuid4())
        self._started_utc = datetime.now(UTC).isoformat()

        self._local = threading.local()
        self._lock = threading.Lock()
        self._connections: list[sqlite3.Connection] = []

        self._use_uri = config.database.startswith("file:")
        self._is_memory_db = config.database == ":memory:" or "mode=memory" in config.database

        if not self._is_memory_db and not self._use_uri:
            db_path = Path(config.database)
            if db_path.parent != Path("."):
                db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local database connection."""
        try:
            connection: sqlite3.Connection = self._local.connection
            return connection
        except AttributeError:
            conn = sqlite3.connect(
                self._config.database,
                check_same_thread=False,
                timeout=30.0,
                uri=self._use_uri,
            )
            if self._is_memory_db:
                conn.execute("PRAGMA journal_mode=MEMORY")
                conn.execute("PRAGMA synchronous=OFF")
            else:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
            with self._lock:
                self._connections.append(conn)
            return conn

    def _init_schema(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        conn.executescript(_SCHEMA)
        conn.commit()

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def started_utc(self) -> str:
        return self._started_utc

    def record_request(
        self,
        *,
        request_id: str,
        timestamp_utc: str,
        path: str,
        outcome: str,
        status_code: int | None = None,
        error_type: str | None = None,
        injection_type: str | None = None,
        latency_ms: float | None = None,
        injected_delay_ms: float | None = None,
        content_type_served: str | None = None,
        encoding_served: str | None = None,
        redirect_target: str | None = None,
        redirect_hops: int | None = None,
    ) -> None:
        """Record a single request to the metrics database."""
        conn = self._get_connection()

        conn.execute(
            """
            INSERT INTO requests (
                request_id, timestamp_utc, path, outcome, status_code,
                error_type, injection_type, latency_ms, injected_delay_ms,
                content_type_served, encoding_served, redirect_target, redirect_hops
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                timestamp_utc,
                path,
                outcome,
                status_code,
                error_type,
                injection_type,
                latency_ms,
                injected_delay_ms,
                content_type_served,
                encoding_served,
                redirect_target,
                redirect_hops,
            ),
        )

        self._update_timeseries(conn, timestamp_utc, outcome, status_code, error_type, latency_ms)
        conn.commit()

    def _update_timeseries(
        self,
        conn: sqlite3.Connection,
        timestamp_utc: str,
        outcome: str,
        status_code: int | None,
        error_type: str | None,
        latency_ms: float | None,
    ) -> None:
        """Update time-series aggregation for a request."""
        bucket = _get_bucket_utc(timestamp_utc, self._config.timeseries_bucket_sec)

        (
            is_success,
            is_rate_limited,
            is_forbidden,
            is_not_found,
            is_server_error,
            is_connection_error,
            is_malformed,
            is_redirect,
        ) = _classify_web_outcome(outcome, status_code, error_type)

        conn.execute(
            """
            INSERT INTO timeseries (
                bucket_utc, requests_total, requests_success, requests_rate_limited,
                requests_forbidden, requests_not_found, requests_server_error,
                requests_connection_error, requests_malformed, requests_redirect,
                avg_latency_ms, p99_latency_ms
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bucket_utc) DO UPDATE SET
                requests_total = requests_total + 1,
                requests_success = requests_success + ?,
                requests_rate_limited = requests_rate_limited + ?,
                requests_forbidden = requests_forbidden + ?,
                requests_not_found = requests_not_found + ?,
                requests_server_error = requests_server_error + ?,
                requests_connection_error = requests_connection_error + ?,
                requests_malformed = requests_malformed + ?,
                requests_redirect = requests_redirect + ?
            """,
            (
                bucket,
                int(is_success),
                int(is_rate_limited),
                int(is_forbidden),
                int(is_not_found),
                int(is_server_error),
                int(is_connection_error),
                int(is_malformed),
                int(is_redirect),
                latency_ms,
                latency_ms,
                # UPDATE part
                int(is_success),
                int(is_rate_limited),
                int(is_forbidden),
                int(is_not_found),
                int(is_server_error),
                int(is_connection_error),
                int(is_malformed),
                int(is_redirect),
            ),
        )

        if latency_ms is not None:
            self._update_bucket_latency_stats(conn, bucket)

    def _update_bucket_latency_stats(
        self,
        conn: sqlite3.Connection,
        bucket: str,
    ) -> None:
        """Recalculate latency statistics for a time-series bucket."""
        bucket_dt = datetime.fromisoformat(bucket)
        bucket_end = (bucket_dt + timedelta(seconds=self._config.timeseries_bucket_sec)).isoformat()

        cursor = conn.execute(
            """
            SELECT latency_ms FROM requests
            WHERE timestamp_utc >= ? AND timestamp_utc < ? AND latency_ms IS NOT NULL
            ORDER BY latency_ms
            """,
            (bucket, bucket_end),
        )
        latencies = [row[0] for row in cursor.fetchall()]
        if not latencies:
            return

        avg_latency = sum(latencies) / len(latencies)
        p99_index = min(int(len(latencies) * 0.99), len(latencies) - 1)
        p99_latency = latencies[p99_index]

        conn.execute(
            "UPDATE timeseries SET avg_latency_ms = ?, p99_latency_ms = ? WHERE bucket_utc = ?",
            (avg_latency, p99_latency, bucket),
        )

    def reset(
        self,
        *,
        config_json: str | None = None,
        preset_name: str | None = None,
    ) -> None:
        """Reset all metrics tables and start a new run."""
        with self._lock:
            self._run_id = str(uuid.uuid4())
            self._started_utc = datetime.now(UTC).isoformat()

        conn = self._get_connection()

        if config_json is None:
            cursor = conn.execute("SELECT config_json, preset_name FROM run_info LIMIT 1")
            row = cursor.fetchone()
            if row is not None:
                config_json = row["config_json"]
                if preset_name is None:
                    preset_name = row["preset_name"]

        conn.execute("DELETE FROM requests")
        conn.execute("DELETE FROM timeseries")

        if config_json is not None:
            conn.execute("DELETE FROM run_info")
            conn.execute(
                "INSERT INTO run_info (run_id, started_utc, config_json, preset_name) VALUES (?, ?, ?, ?)",
                (self._run_id, self._started_utc, config_json, preset_name),
            )
        conn.commit()

    def get_stats(self) -> dict[str, Any]:
        """Get summary statistics for the current run."""
        conn = self._get_connection()

        cursor = conn.execute("SELECT COUNT(*) FROM requests")
        total_requests = cursor.fetchone()[0]

        cursor = conn.execute("SELECT outcome, COUNT(*) FROM requests GROUP BY outcome")
        requests_by_outcome = {row[0]: row[1] for row in cursor.fetchall()}

        cursor = conn.execute("SELECT status_code, COUNT(*) FROM requests WHERE status_code IS NOT NULL GROUP BY status_code")
        requests_by_status_code = {row[0]: row[1] for row in cursor.fetchall()}

        # Latency statistics
        cursor = conn.execute("SELECT AVG(latency_ms), MAX(latency_ms) FROM requests WHERE latency_ms IS NOT NULL")
        row = cursor.fetchone()
        avg_latency = row[0]
        max_latency = row[1]

        cursor = conn.execute("SELECT latency_ms FROM requests WHERE latency_ms IS NOT NULL ORDER BY latency_ms")
        latencies = [r[0] for r in cursor.fetchall()]

        p50_latency = None
        p95_latency = None
        p99_latency = None

        if latencies:
            p50_latency = latencies[min(int(len(latencies) * 0.50), len(latencies) - 1)]
            p95_latency = latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)]
            p99_latency = latencies[min(int(len(latencies) * 0.99), len(latencies) - 1)]

        error_rate = 0.0
        if total_requests > 0:
            error_count = sum(count for outcome, count in requests_by_outcome.items() if outcome != "success")
            error_rate = (error_count / total_requests) * 100

        return {
            "run_id": self._run_id,
            "started_utc": self._started_utc,
            "total_requests": total_requests,
            "requests_by_outcome": requests_by_outcome,
            "requests_by_status_code": requests_by_status_code,
            "latency_stats": {
                "avg_ms": avg_latency,
                "p50_ms": p50_latency,
                "p95_ms": p95_latency,
                "p99_ms": p99_latency,
                "max_ms": max_latency,
            },
            "error_rate": error_rate,
        }

    def export_data(self) -> dict[str, Any]:
        """Export raw requests and time-series data."""
        conn = self._get_connection()
        requests = [dict(row) for row in conn.execute("SELECT * FROM requests ORDER BY timestamp_utc")]
        timeseries = [dict(row) for row in conn.execute("SELECT * FROM timeseries ORDER BY bucket_utc")]
        return {
            "run_id": self._run_id,
            "started_utc": self._started_utc,
            "requests": requests,
            "timeseries": timeseries,
        }

    def save_run_info(
        self,
        config_json: str,
        preset_name: str | None = None,
    ) -> None:
        """Save run information to the database."""
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO run_info (run_id, started_utc, config_json, preset_name) VALUES (?, ?, ?, ?)",
            (self._run_id, self._started_utc, config_json, preset_name),
        )
        conn.commit()

    def get_requests(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        outcome: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get request records from the database."""
        conn = self._get_connection()
        if outcome is not None:
            cursor = conn.execute(
                "SELECT * FROM requests WHERE outcome = ? ORDER BY timestamp_utc DESC LIMIT ? OFFSET ?",
                (outcome, limit, offset),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM requests ORDER BY timestamp_utc DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [dict(row) for row in cursor.fetchall()]

    def get_timeseries(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get time-series records from the database."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM timeseries ORDER BY bucket_utc DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close all database connections across all threads."""
        with self._lock:
            for conn in self._connections:
                with contextlib.suppress(sqlite3.ProgrammingError):
                    conn.close()
            self._connections.clear()
