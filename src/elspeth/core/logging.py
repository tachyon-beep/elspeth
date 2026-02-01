# src/elspeth/core/logging.py
"""Structured logging configuration for ELSPETH.

Uses structlog for structured logging that complements
OpenTelemetry spans for observability.
"""

import logging
import sys
from typing import Any

import structlog

# Third-party loggers that are excessively verbose at DEBUG level.
# These emit HTTP connection details, credential operations, etc. that
# are noise rather than signal. Silence them to WARNING even when
# ELSPETH runs in DEBUG mode.
_NOISY_LOGGERS: tuple[str, ...] = (
    # Azure SDK - emits HTTP request/response details for every call
    "azure",
    "azure.core",
    "azure.core.pipeline",
    "azure.core.pipeline.policies",
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
    "azure.monitor",
    # urllib3 - connection pool management noise
    "urllib3",
    "urllib3.connectionpool",
    # OpenTelemetry SDK internals - span processing details
    "opentelemetry",
    "opentelemetry.sdk",
    "opentelemetry.exporter",
    # httpx/httpcore - async HTTP client internals
    "httpx",
    "httpcore",
)


def configure_logging(
    *,
    json_output: bool = False,
    level: str = "INFO",
) -> None:
    """Configure structlog for ELSPETH.

    Args:
        json_output: If True, output JSON. If False, human-readable.
        level: Log level (DEBUG, INFO, WARNING, ERROR).
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
        force=True,  # Allow reconfiguration
    )

    # Silence noisy third-party loggers that spam DEBUG output.
    # These inherit from root logger, so we must explicitly set them to WARNING
    # AFTER basicConfig() sets the root level.
    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # Shared processors
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_output:
        # JSON output for machine processing
        processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console output for humans
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        # IMPORTANT: Disable caching to allow reconfiguration in tests
        # Without this, tests that reconfigure logging will get stale loggers
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a bound logger for a module.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Bound structlog logger.
    """
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
