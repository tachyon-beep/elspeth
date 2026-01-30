# src/elspeth/telemetry/events.py
"""Telemetry event definitions for pipeline observability.

These events are emitted during pipeline execution and exported to
external observability platforms. They complement (not replace) the
Landscape audit trail:

- Landscape: Legal record, complete lineage, persisted forever
- Telemetry: Operational visibility, real-time streaming, ephemeral

Event categories:
- Lifecycle: Run start/complete, phase transitions
- Row-level: Token creation, transform completion, gate routing, token completion
- External calls: LLM/HTTP/SQL call completion with timing and status
"""

from dataclasses import dataclass
from datetime import datetime

from elspeth.contracts.enums import (
    CallStatus,
    CallType,
    NodeStateStatus,
    RoutingMode,
    RowOutcome,
    RunStatus,
)
from elspeth.contracts.events import PhaseAction, PipelinePhase


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """Base class for all telemetry events.

    All events include:
    - timestamp: When the event occurred (UTC)
    - run_id: Pipeline run this event belongs to

    Events are immutable (frozen) for thread-safety and to prevent
    accidental modification during export.
    """

    timestamp: datetime
    run_id: str


# =============================================================================
# Lifecycle Events
# =============================================================================


@dataclass(frozen=True, slots=True)
class RunStarted(TelemetryEvent):
    """Emitted when a pipeline run begins.

    Attributes:
        config_hash: Hash of the pipeline configuration for change detection
        source_plugin: Name of the source plugin being used
    """

    config_hash: str
    source_plugin: str


@dataclass(frozen=True, slots=True)
class RunCompleted(TelemetryEvent):
    """Emitted when a pipeline run finishes (success or failure).

    Attributes:
        status: Final run status (completed, failed)
        row_count: Total rows processed
        duration_ms: Total run duration in milliseconds
    """

    status: RunStatus
    row_count: int
    duration_ms: float


@dataclass(frozen=True, slots=True)
class PhaseChanged(TelemetryEvent):
    """Emitted when pipeline transitions between phases.

    Phases represent major lifecycle stages (config, graph, plugins,
    database, source, process, export). This event fires on phase
    entry with the action being performed.

    Attributes:
        phase: The pipeline phase being entered
        action: What's happening in this phase (loading, validating, etc.)
    """

    phase: PipelinePhase
    action: PhaseAction


# =============================================================================
# Row-Level Events
# =============================================================================


@dataclass(frozen=True, slots=True)
class RowCreated(TelemetryEvent):
    """Emitted when a new row enters the pipeline from the source.

    Attributes:
        row_id: Stable source row identity
        token_id: Token instance for this row in the DAG
        content_hash: Hash of the row content for deduplication
    """

    row_id: str
    token_id: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class TransformCompleted(TelemetryEvent):
    """Emitted when a transform finishes processing a row.

    Attributes:
        row_id: Source row identity
        token_id: Token instance being processed
        node_id: DAG node that processed the row
        plugin_name: Name of the transform plugin
        status: Processing result (completed, failed)
        duration_ms: Transform execution time in milliseconds
        input_hash: Hash of transform input for lineage
        output_hash: Hash of transform output for lineage
    """

    row_id: str
    token_id: str
    node_id: str
    plugin_name: str
    status: NodeStateStatus
    duration_ms: float
    input_hash: str
    output_hash: str


@dataclass(frozen=True, slots=True)
class GateEvaluated(TelemetryEvent):
    """Emitted when a gate makes a routing decision.

    Attributes:
        row_id: Source row identity
        token_id: Token instance being routed
        node_id: Gate node that made the decision
        plugin_name: Name of the gate plugin
        routing_mode: How routing was performed (move, copy)
        destinations: Tuple of destination node/sink names
    """

    row_id: str
    token_id: str
    node_id: str
    plugin_name: str
    routing_mode: RoutingMode
    destinations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TokenCompleted(TelemetryEvent):
    """Emitted when a token reaches its terminal state.

    Attributes:
        row_id: Source row identity
        token_id: Token instance that completed
        outcome: Terminal outcome (completed, routed, failed, etc.)
        sink_name: Destination sink if applicable, None otherwise
    """

    row_id: str
    token_id: str
    outcome: RowOutcome
    sink_name: str | None


# =============================================================================
# External Call Events
# =============================================================================


@dataclass(frozen=True, slots=True)
class ExternalCallCompleted(TelemetryEvent):
    """Emitted when an external call (LLM, HTTP, SQL) completes.

    Attributes:
        state_id: Node state that made the call
        call_type: Type of external call (llm, http, sql, filesystem)
        provider: Service provider (e.g., "azure-openai", "anthropic")
        status: Call result (success, error)
        latency_ms: Call duration in milliseconds
        request_hash: Hash of request payload for debugging (optional)
        response_hash: Hash of response payload for debugging (optional)
        token_usage: LLM token counts if applicable (optional)
    """

    state_id: str
    call_type: CallType
    provider: str
    status: CallStatus
    latency_ms: float
    request_hash: str | None = None
    response_hash: str | None = None
    token_usage: dict[str, int] | None = None
