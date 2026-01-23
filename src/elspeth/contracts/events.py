"""Observability events for pipeline execution.

These domain events provide visibility into pipeline phases, progress,
and completion status. Events are emitted by the orchestrator and consumed
by CLI formatters for human-readable or structured output.
"""

from dataclasses import dataclass
from enum import Enum


class PipelinePhase(str, Enum):
    """Pipeline lifecycle phases for observability events.

    Uses (str, Enum) pattern for consistency with existing codebase
    (see contracts/enums.py RunStatus).
    """

    CONFIG = "config"
    GRAPH = "graph"
    PLUGINS = "plugins"
    AGGREGATIONS = "aggregations"
    DATABASE = "database"
    SCHEMA_VALIDATION = "schema_validation"
    SOURCE = "source"
    PROCESS = "process"
    EXPORT = "export"


class PhaseAction(str, Enum):
    """Actions within a pipeline phase."""

    LOADING = "loading"
    VALIDATING = "validating"
    BUILDING = "building"
    CONNECTING = "connecting"
    INITIALIZING = "initializing"
    PROCESSING = "processing"
    EXPORTING = "exporting"


class RunCompletionStatus(str, Enum):
    """Final status for RunCompleted events."""

    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class PhaseStarted:
    """Emitted when a pipeline phase begins.

    Phases represent major lifecycle stages:
    - config: Loading and validating settings
    - graph: Building and validating execution graph
    - plugins: Instantiating source, transforms, and sinks
    - aggregations: Instantiating aggregation plugins
    - database: Connecting to Landscape database
    - schema_validation: Validating plugin schemas
    - source: Loading source data
    - process: Processing rows through transforms
    - export: Exporting results (when enabled)

    Attributes:
        phase: The lifecycle phase starting
        action: What's happening (e.g., "loading", "validating")
        target: Optional target (e.g., file path, plugin name)
    """

    phase: PipelinePhase
    action: PhaseAction
    target: str | None = None


@dataclass(frozen=True, slots=True)
class PhaseCompleted:
    """Emitted when a pipeline phase completes successfully."""

    phase: PipelinePhase
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class PhaseError:
    """Emitted when a pipeline phase fails.

    Stores the full exception object to preserve traceback, exception type,
    and chained causes for debugging and audit trail integrity.
    """

    phase: PipelinePhase
    error: BaseException
    target: str | None = None  # What failed (plugin name, file path, etc.)

    @property
    def error_message(self) -> str:
        """Human-readable error message for formatting."""
        return str(self.error)


@dataclass(frozen=True, slots=True)
class RunCompleted:
    """Emitted when pipeline run finishes (success or failure).

    Provides final summary for CI integration.
    """

    run_id: str
    status: RunCompletionStatus
    total_rows: int
    succeeded: int
    failed: int
    quarantined: int
    duration_seconds: float
    exit_code: int  # 0=success, 1=partial failure, 2=total failure
