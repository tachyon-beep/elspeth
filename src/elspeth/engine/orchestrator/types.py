# src/elspeth/engine/orchestrator/types.py
"""Pipeline configuration and result types.

These types define the interface for pipeline execution:
- PipelineConfig: Input configuration for a run
- RunResult: Output statistics from a run
- RouteValidationError: Configuration validation failure
- AggregationFlushResult: Result of flushing aggregation buffers

IMPORTANT: Import Cycle Prevention
----------------------------------
This module is a LEAF MODULE - it must NOT import from other orchestrator
submodules (validation.py, export.py, aggregation.py, core.py).

Other modules import FROM here (e.g., validation.py imports RouteValidationError).
If types.py were to import from those modules, a circular import would occur.

Keep types.py as pure data definitions with minimal dependencies.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspeth.core.config import AggregationSettings, CoalesceSettings, GateSettings
    from elspeth.plugins.protocols import SinkProtocol, SourceProtocol

from elspeth.contracts import RunStatus

# Import protocols at runtime (not TYPE_CHECKING) because RowPlugin type alias
# is used in runtime annotations and isinstance() checks
from elspeth.plugins.protocols import GateProtocol, TransformProtocol

# Type alias for row-processing plugins in the transforms pipeline
# NOTE: BaseAggregation was DELETED - aggregation is now handled by
# batch-aware transforms (is_batch_aware=True on TransformProtocol)
RowPlugin = TransformProtocol | GateProtocol
"""Union of all row-processing plugin types for pipeline transforms list."""


@dataclass
class PipelineConfig:
    """Configuration for a pipeline run.

    All plugin fields are now properly typed for IDE support and
    static type checking.

    Attributes:
        source: Source plugin instance
        transforms: List of transform/gate plugin instances (processed first)
        sinks: Dict of sink_name -> sink plugin instance
        config: Additional run configuration
        gates: Config-driven gates (processed AFTER transforms, BEFORE sinks)
        aggregation_settings: Dict of node_id -> AggregationSettings
        coalesce_settings: List of coalesce configurations for merging fork paths
    """

    source: SourceProtocol
    transforms: list[RowPlugin]
    sinks: dict[str, SinkProtocol]
    config: dict[str, Any] = field(default_factory=dict)
    gates: list[GateSettings] = field(default_factory=list)
    aggregation_settings: dict[str, AggregationSettings] = field(default_factory=dict)
    coalesce_settings: list[CoalesceSettings] = field(default_factory=list)


@dataclass
class RunResult:
    """Result of a pipeline run."""

    run_id: str
    status: RunStatus
    rows_processed: int
    rows_succeeded: int
    rows_failed: int
    rows_routed: int
    rows_quarantined: int = 0
    rows_forked: int = 0
    rows_coalesced: int = 0
    rows_coalesce_failed: int = 0  # Coalesce failures (quorum_not_met, incomplete_branches)
    rows_expanded: int = 0  # Deaggregation parent tokens
    rows_buffered: int = 0  # Passthrough mode buffered tokens
    routed_destinations: dict[str, int] = field(default_factory=dict)  # sink_name -> count


@dataclass(frozen=True, slots=True)
class AggregationFlushResult:
    """Result of flushing aggregation buffers.

    Replaces the 9-element tuple return type with named fields for clarity
    and type safety. Using frozen dataclass prevents accidental mutation.
    """

    rows_succeeded: int = 0
    rows_failed: int = 0
    rows_routed: int = 0
    rows_quarantined: int = 0
    rows_coalesced: int = 0
    rows_forked: int = 0
    rows_expanded: int = 0
    rows_buffered: int = 0
    routed_destinations: dict[str, int] = field(default_factory=dict)

    def __add__(self, other: AggregationFlushResult) -> AggregationFlushResult:
        """Combine two results by summing all counters."""
        combined_destinations: Counter[str] = Counter(self.routed_destinations)
        combined_destinations.update(other.routed_destinations)
        return AggregationFlushResult(
            rows_succeeded=self.rows_succeeded + other.rows_succeeded,
            rows_failed=self.rows_failed + other.rows_failed,
            rows_routed=self.rows_routed + other.rows_routed,
            rows_quarantined=self.rows_quarantined + other.rows_quarantined,
            rows_coalesced=self.rows_coalesced + other.rows_coalesced,
            rows_forked=self.rows_forked + other.rows_forked,
            rows_expanded=self.rows_expanded + other.rows_expanded,
            rows_buffered=self.rows_buffered + other.rows_buffered,
            routed_destinations=dict(combined_destinations),
        )


@dataclass
class ExecutionCounters:
    """Mutable counters accumulated during pipeline execution.

    Replaces the 11 loose counter variables + routed_destinations Counter
    that were duplicated in both _execute_run() and _process_resumed_rows().

    Mutable (not frozen) because counters are incremented row-by-row during
    the processing loop. Frozen would require creating new instances on
    every update.
    """

    rows_processed: int = 0
    rows_succeeded: int = 0
    rows_failed: int = 0
    rows_routed: int = 0
    rows_quarantined: int = 0
    rows_forked: int = 0
    rows_coalesced: int = 0
    rows_coalesce_failed: int = 0
    rows_expanded: int = 0
    rows_buffered: int = 0
    routed_destinations: Counter[str] = field(default_factory=Counter)

    def accumulate_flush_result(self, result: AggregationFlushResult) -> None:
        """Merge an AggregationFlushResult into these counters.

        Replaces the 9 manual additions that appeared after every
        check_aggregation_timeouts() and flush_remaining_aggregation_buffers() call.
        """
        self.rows_succeeded += result.rows_succeeded
        self.rows_failed += result.rows_failed
        self.rows_routed += result.rows_routed
        self.rows_quarantined += result.rows_quarantined
        self.rows_coalesced += result.rows_coalesced
        self.rows_forked += result.rows_forked
        self.rows_expanded += result.rows_expanded
        self.rows_buffered += result.rows_buffered
        for dest, count in result.routed_destinations.items():
            self.routed_destinations[dest] += count

    def to_run_result(self, run_id: str, status: RunStatus = RunStatus.RUNNING) -> RunResult:
        """Build a RunResult from these counters.

        Args:
            run_id: The run identifier.
            status: Run status (default RUNNING, caller updates to COMPLETED).
        """
        return RunResult(
            run_id=run_id,
            status=status,
            rows_processed=self.rows_processed,
            rows_succeeded=self.rows_succeeded,
            rows_failed=self.rows_failed,
            rows_routed=self.rows_routed,
            rows_quarantined=self.rows_quarantined,
            rows_forked=self.rows_forked,
            rows_coalesced=self.rows_coalesced,
            rows_coalesce_failed=self.rows_coalesce_failed,
            rows_expanded=self.rows_expanded,
            rows_buffered=self.rows_buffered,
            routed_destinations=dict(self.routed_destinations),
        )


class RouteValidationError(Exception):
    """Raised when route configuration is invalid.

    This error is raised at pipeline initialization, before any rows are
    processed. It indicates a configuration problem that would cause
    failures during processing.
    """
