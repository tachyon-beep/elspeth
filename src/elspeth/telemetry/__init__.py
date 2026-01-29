# src/elspeth/telemetry/__init__.py
"""Telemetry subsystem for pipeline observability.

This package provides Tier 1 (global) telemetry - framework-level audit events
streamed to external observability platforms. It complements but does not
replace the Landscape audit trail:

- Landscape: Legal record, complete lineage, persisted forever
- Telemetry: Operational visibility, real-time streaming, ephemeral

Components:
- events: TelemetryEvent base and all event dataclasses
- buffer: BoundedBuffer for event batching with overflow tracking
- protocols: ExporterProtocol for implementing exporters
- hookspecs: pluggy hooks for exporter discovery
- errors: TelemetryExporterError for configuration failures

Usage:
    from elspeth.telemetry import (
        # Events
        TelemetryEvent,
        RunStarted,
        RunCompleted,
        PhaseChanged,
        RowCreated,
        TransformCompleted,
        GateEvaluated,
        TokenCompleted,
        ExternalCallCompleted,
        # Buffer
        BoundedBuffer,
        # Protocol
        ExporterProtocol,
        # Errors
        TelemetryExporterError,
    )
"""

from elspeth.telemetry.buffer import BoundedBuffer
from elspeth.telemetry.errors import TelemetryExporterError
from elspeth.telemetry.events import (
    ExternalCallCompleted,
    GateEvaluated,
    PhaseChanged,
    RowCreated,
    RunCompleted,
    RunStarted,
    TelemetryEvent,
    TokenCompleted,
    TransformCompleted,
)
from elspeth.telemetry.protocols import ExporterProtocol

__all__ = [
    "BoundedBuffer",
    "ExporterProtocol",
    "ExternalCallCompleted",
    "GateEvaluated",
    "PhaseChanged",
    "RowCreated",
    "RunCompleted",
    "RunStarted",
    "TelemetryEvent",
    "TelemetryExporterError",
    "TokenCompleted",
    "TransformCompleted",
]
