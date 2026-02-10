# src/elspeth/testing/chaosweb/metrics.py
"""Metrics storage and aggregation for ChaosWeb server.

The WebMetricsRecorder provides typed wrappers around the shared MetricsStore
for web-specific request recording and outcome classification (forbidden,
not_found, redirect tracking, encoding, content type).
"""

from typing import Any

from elspeth.testing.chaosengine.metrics_store import MetricsStore
from elspeth.testing.chaosengine.types import ColumnDef, MetricsConfig, MetricsSchema

# Schema definition for web metrics tables.
WEB_METRICS_SCHEMA = MetricsSchema(
    request_columns=(
        ColumnDef("request_id", "TEXT", primary_key=True),
        ColumnDef("timestamp_utc", "TEXT", nullable=False),
        ColumnDef("path", "TEXT", nullable=False),
        ColumnDef("outcome", "TEXT", nullable=False),
        ColumnDef("status_code", "INTEGER"),
        ColumnDef("error_type", "TEXT"),
        ColumnDef("injection_type", "TEXT"),
        ColumnDef("latency_ms", "REAL"),
        ColumnDef("injected_delay_ms", "REAL"),
        ColumnDef("content_type_served", "TEXT"),
        ColumnDef("encoding_served", "TEXT"),
        ColumnDef("redirect_target", "TEXT"),
        ColumnDef("redirect_hops", "INTEGER"),
    ),
    timeseries_columns=(
        ColumnDef("bucket_utc", "TEXT", primary_key=True),
        ColumnDef("requests_total", "INTEGER", nullable=False, default="0"),
        ColumnDef("requests_success", "INTEGER", nullable=False, default="0"),
        ColumnDef("requests_rate_limited", "INTEGER", nullable=False, default="0"),
        ColumnDef("requests_forbidden", "INTEGER", nullable=False, default="0"),
        ColumnDef("requests_not_found", "INTEGER", nullable=False, default="0"),
        ColumnDef("requests_server_error", "INTEGER", nullable=False, default="0"),
        ColumnDef("requests_connection_error", "INTEGER", nullable=False, default="0"),
        ColumnDef("requests_malformed", "INTEGER", nullable=False, default="0"),
        ColumnDef("requests_redirect", "INTEGER", nullable=False, default="0"),
        ColumnDef("avg_latency_ms", "REAL"),
        ColumnDef("p99_latency_ms", "REAL"),
    ),
    request_indexes=(
        ("idx_requests_timestamp", "timestamp_utc"),
        ("idx_requests_outcome", "outcome"),
        ("idx_requests_path", "path"),
    ),
)


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

    Composes a MetricsStore for all SQLite infrastructure, adding web-specific
    typed wrappers for request recording and outcome classification (forbidden,
    not_found, redirect instead of capacity_error, client_error).

    Usage:
        config = MetricsConfig(database="./metrics.db")
        recorder = WebMetricsRecorder(config)

        # Record a request
        recorder.record_request(
            request_id="abc123",
            timestamp_utc="2024-01-15T10:30:00+00:00",
            path="/page.html",
            outcome="success",
            latency_ms=150.5,
        )

        # Get statistics
        stats = recorder.get_stats()

        # Reset for new run
        recorder.reset()
    """

    def __init__(
        self,
        config: MetricsConfig,
        *,
        run_id: str | None = None,
    ) -> None:
        """Initialize the web metrics recorder.

        Args:
            config: Metrics configuration
            run_id: Optional run ID (default: auto-generated UUID)
        """
        self._config = config
        self._store = MetricsStore(config, WEB_METRICS_SCHEMA, run_id=run_id)

    @property
    def run_id(self) -> str:
        """Get the current run ID."""
        return self._store.run_id

    @property
    def started_utc(self) -> str:
        """Get the run start time in UTC."""
        return self._store.started_utc

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
        """Record a single request to the metrics database.

        This method is thread-safe and non-blocking. It writes the request
        to the requests table and updates the appropriate time-series bucket.

        Args:
            request_id: Unique identifier for this request
            timestamp_utc: ISO-formatted timestamp in UTC
            path: The request path (e.g., '/page.html')
            outcome: Request outcome ('success', 'error_injected', 'error_malformed', 'error_redirect')
            status_code: HTTP status code (optional)
            error_type: Type of error if any (optional)
            injection_type: Type of injected behavior if any (optional)
            latency_ms: Total response latency in milliseconds (optional)
            injected_delay_ms: Artificial delay injected in milliseconds (optional)
            content_type_served: Content-Type header served (optional)
            encoding_served: Encoding served (optional)
            redirect_target: Redirect target URL (optional)
            redirect_hops: Number of redirect hops (optional)
        """
        # Insert into requests table
        self._store.record(
            request_id=request_id,
            timestamp_utc=timestamp_utc,
            path=path,
            outcome=outcome,
            status_code=status_code,
            error_type=error_type,
            injection_type=injection_type,
            latency_ms=latency_ms,
            injected_delay_ms=injected_delay_ms,
            content_type_served=content_type_served,
            encoding_served=encoding_served,
            redirect_target=redirect_target,
            redirect_hops=redirect_hops,
        )

        # Classify and update time-series
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

        bucket = self._store.get_bucket_utc(timestamp_utc)
        self._store.update_timeseries(
            bucket,
            requests_success=int(is_success),
            requests_rate_limited=int(is_rate_limited),
            requests_forbidden=int(is_forbidden),
            requests_not_found=int(is_not_found),
            requests_server_error=int(is_server_error),
            requests_connection_error=int(is_connection_error),
            requests_malformed=int(is_malformed),
            requests_redirect=int(is_redirect),
        )

        # Update latency statistics for the bucket
        self._store.update_bucket_latency(bucket, latency_ms)

        # Commit all three operations atomically
        self._store.commit()

    def reset(
        self,
        *,
        config_json: str | None = None,
        preset_name: str | None = None,
    ) -> None:
        """Reset all metrics tables and start a new run."""
        self._store.reset(config_json=config_json, preset_name=preset_name)

    def get_stats(self) -> dict[str, Any]:
        """Get summary statistics for the current run."""
        return self._store.get_stats()

    def export_data(self) -> dict[str, Any]:
        """Export raw requests and time-series data."""
        return self._store.export_data()

    def save_run_info(
        self,
        config_json: str,
        preset_name: str | None = None,
    ) -> None:
        """Save run information to the database."""
        self._store.save_run_info(config_json, preset_name)

    def get_requests(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        outcome: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get request records from the database."""
        return self._store.get_requests(limit=limit, offset=offset, outcome=outcome)

    def get_timeseries(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get time-series records from the database."""
        return self._store.get_timeseries(limit=limit, offset=offset)

    def close(self) -> None:
        """Close all database connections across all threads."""
        self._store.close()
