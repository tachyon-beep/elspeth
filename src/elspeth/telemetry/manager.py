# src/elspeth/telemetry/manager.py
"""TelemetryManager coordinates event emission to configured exporters.

The TelemetryManager is the central hub for telemetry:
1. Receives telemetry events from EventBus
2. Filters events based on configured granularity
3. Queues events for async export via background thread
4. Dispatches to all exporters with failure isolation
5. Tracks health metrics for monitoring
6. Implements aggregate logging to prevent Warning Fatigue

Design principles:
- Telemetry emitted AFTER Landscape recording (Landscape is the legal record)
- Individual exporter failures don't crash the pipeline
- Aggregate logging every 100 total failures (Warning Fatigue prevention)
- Configurable backpressure behavior (BLOCK vs DROP)

Thread Safety:
    TelemetryManager uses a background export thread for async export.
    - handle_event() is called from the pipeline thread (non-blocking)
    - _export_loop() runs in the background export thread
    - _events_dropped is protected by _dropped_lock (accessed from both threads)
    - All other metrics are only modified by the export thread
    - health_metrics reads are approximately consistent
"""

import queue
import threading
from typing import Any

import structlog

from elspeth.contracts.config import RuntimeTelemetryProtocol
from elspeth.contracts.config.defaults import INTERNAL_DEFAULTS
from elspeth.contracts.enums import BackpressureMode  # noqa: F401 - used in Task 5
from elspeth.telemetry.errors import TelemetryExporterError
from elspeth.telemetry.events import TelemetryEvent
from elspeth.telemetry.filtering import should_emit
from elspeth.telemetry.protocols import ExporterProtocol

logger = structlog.get_logger(__name__)


class TelemetryManager:
    """Coordinates event emission to configured exporters.

    The TelemetryManager receives telemetry events, queues them for async
    export via a background thread, and dispatches to all exporters. It
    provides failure isolation (one exporter failing doesn't affect others)
    and tracks health metrics for operational monitoring.

    Backpressure modes:
    - BLOCK: handle_event() blocks when queue is full (pipeline slows)
    - DROP: handle_event() drops events when queue is full (pipeline unaffected)

    Failure handling:
    - Individual exporter failures are logged but don't crash the pipeline
    - Aggregate logging every _LOG_INTERVAL failures prevents Warning Fatigue
    - If ALL exporters fail _max_consecutive_failures times in a row:
      - fail_on_total_exporter_failure=True: Raise TelemetryExporterError
      - fail_on_total_exporter_failure=False: Log CRITICAL and continue

    Thread Safety:
        Uses background export thread. handle_event() is thread-safe.
        _events_dropped protected by lock (both threads write).
        Other metrics single-writer (export thread only).

    Example:
        >>> from elspeth.telemetry import TelemetryManager
        >>> manager = TelemetryManager(config, exporters=[console_exporter])
        >>> manager.handle_event(run_started_event)
        >>> manager.flush()
        >>> manager.close()
    """

    _LOG_INTERVAL = 100  # Log every 100 total failures

    def __init__(
        self,
        config: RuntimeTelemetryProtocol,
        exporters: list[ExporterProtocol],
    ) -> None:
        """Initialize the TelemetryManager.

        Args:
            config: Runtime telemetry configuration with granularity,
                backpressure_mode, and fail_on_total_exporter_failure settings
            exporters: List of configured exporter instances. May be empty
                (telemetry will be a no-op).
        """
        self._config = config
        self._exporters = exporters
        self._consecutive_total_failures = 0
        self._max_consecutive_failures = 10

        # Health metrics
        self._events_emitted = 0
        self._events_dropped = 0
        self._exporter_failures: dict[str, int] = {}
        self._last_logged_drop_count: int = 0

        # Track whether we've already disabled telemetry
        self._disabled = False

        # Thread coordination
        self._shutdown_event = threading.Event()
        self._dropped_lock = threading.Lock()
        self._export_thread_ready = threading.Event()  # Signals thread is running

        # Queue for async export - read size from INTERNAL_DEFAULTS
        queue_size = int(INTERNAL_DEFAULTS["telemetry"]["queue_size"])
        self._queue: queue.Queue[TelemetryEvent | None] = queue.Queue(maxsize=queue_size)

        # Start export thread (non-daemon to ensure proper cleanup)
        self._export_thread = threading.Thread(
            target=self._export_loop,
            name="telemetry-export",
            daemon=False,
        )
        self._export_thread.start()
        # Wait for thread to be ready (prevents startup race)
        self._export_thread_ready.wait(timeout=5.0)

    def _export_loop(self) -> None:
        """Background thread: consume queue and export.

        Stub implementation - will be replaced in Task 6.
        """
        self._export_thread_ready.set()
        while True:
            event = self._queue.get()
            if event is None:  # Shutdown sentinel
                self._queue.task_done()
                break
            self._queue.task_done()

    def handle_event(self, event: TelemetryEvent) -> None:
        """Filter and dispatch event to all exporters.

        Events are filtered by granularity before dispatch. Each exporter
        receives the event independently - failures are isolated.

        When ALL exporters fail, the event is counted as dropped. After
        _max_consecutive_failures total failures, behavior depends on
        fail_on_total_exporter_failure config setting.

        Args:
            event: The telemetry event to process

        Raises:
            TelemetryExporterError: If all exporters fail repeatedly and
                fail_on_total_exporter_failure is True
        """
        # Skip if telemetry was disabled due to repeated failures
        if self._disabled:
            return

        # Skip if no exporters configured
        if not self._exporters:
            return

        # Filter by granularity
        if not should_emit(event, self._config.granularity):
            return

        # Dispatch to all exporters with failure isolation
        failures = 0
        for exporter in self._exporters:
            try:
                exporter.export(event)
            except Exception as e:
                failures += 1
                self._exporter_failures[exporter.name] = self._exporter_failures.get(exporter.name, 0) + 1
                logger.warning(
                    "Telemetry exporter failed",
                    exporter=exporter.name,
                    event_type=type(event).__name__,
                    error=str(e),
                )

        # Update metrics based on outcome
        if failures == 0:
            # Complete success
            self._events_emitted += 1
            self._consecutive_total_failures = 0
        elif failures == len(self._exporters):
            # ALL exporters failed
            self._consecutive_total_failures += 1
            self._events_dropped += 1

            # Aggregate logging every _LOG_INTERVAL
            if self._events_dropped - self._last_logged_drop_count >= self._LOG_INTERVAL:
                logger.error(
                    "ALL telemetry exporters failing - events dropped",
                    dropped_since_last_log=self._events_dropped - self._last_logged_drop_count,
                    dropped_total=self._events_dropped,
                    consecutive_failures=self._consecutive_total_failures,
                )
                self._last_logged_drop_count = self._events_dropped

            # Check if we should crash or disable
            if self._consecutive_total_failures >= self._max_consecutive_failures:
                if self._config.fail_on_total_exporter_failure:
                    raise TelemetryExporterError(
                        "all",
                        f"All {len(self._exporters)} exporters failed {self._max_consecutive_failures} consecutive times.",
                    )
                else:
                    logger.critical(
                        "Telemetry disabled after repeated total failures",
                        consecutive_failures=self._consecutive_total_failures,
                        events_dropped=self._events_dropped,
                    )
                    self._disabled = True
        else:
            # Partial success - at least one exporter worked
            self._events_emitted += 1
            self._consecutive_total_failures = 0

    @property
    def health_metrics(self) -> dict[str, Any]:
        """Return telemetry health metrics for monitoring.

        Returns a snapshot of telemetry health:
        - events_emitted: Successfully delivered to at least one exporter
        - events_dropped: Failed to deliver to any exporter
        - exporter_failures: Per-exporter failure counts
        - consecutive_total_failures: Current streak of total failures

        Returns:
            Dictionary of health metrics
        """
        return {
            "events_emitted": self._events_emitted,
            "events_dropped": self._events_dropped,
            "exporter_failures": self._exporter_failures.copy(),
            "consecutive_total_failures": self._consecutive_total_failures,
        }

    def flush(self) -> None:
        """Flush all exporters.

        Ensures all buffered events are sent. Exporter flush failures
        are logged but don't raise - telemetry should not crash the pipeline.
        """
        for exporter in self._exporters:
            try:
                exporter.flush()
            except Exception as e:
                logger.warning(
                    "Exporter flush failed",
                    exporter=exporter.name,
                    error=str(e),
                )

    def close(self) -> None:
        """Close all exporters and log final metrics.

        Should be called at pipeline shutdown. Logs final health metrics
        and releases exporter resources. Close failures are logged but
        don't raise.
        """
        logger.info("Telemetry manager closing", **self.health_metrics)
        for exporter in self._exporters:
            try:
                exporter.close()
            except Exception as e:
                logger.warning(
                    "Exporter close failed",
                    exporter=exporter.name,
                    error=str(e),
                )
