"""Telemetry-specific exceptions.

These exceptions are for telemetry subsystem errors only.
They should NOT be raised for pipeline execution errors.
"""

# Exceptions that represent transport/IO failures — safe to swallow during telemetry export.
# Everything else is a programming error that must crash.
# Individual exporters may extend this with SDK-specific transport exceptions.
TELEMETRY_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,  # covers socket.error, BrokenPipeError, ConnectionResetError, etc.
)


class TelemetryExporterError(Exception):
    """Raised when an exporter encounters a configuration or initialization error.

    This is raised during exporter setup (configure/initialization), NOT during
    export operations. Export operations must not raise - they log errors instead.

    Attributes:
        exporter_name: Name of the exporter that failed
        message: Human-readable error description
    """

    def __init__(self, exporter_name: str, message: str) -> None:
        self.exporter_name = exporter_name
        self.message = message
        super().__init__(f"Exporter '{exporter_name}' failed: {message}")
