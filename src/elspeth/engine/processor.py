# src/elspeth/engine/processor.py
"""RowProcessor: Orchestrates row processing through pipeline.

Coordinates:
- Token creation
- Transform execution
- Gate evaluation (plugin and config-driven)
- Aggregation handling
- Final outcome recording
"""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

from elspeth.contracts import RouteDestination, RowOutcome, RowResult, SourceRow, TokenInfo, TransformResult
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.contracts.types import BranchName, CoalesceName, NodeID, SinkName, StepResolver

if TYPE_CHECKING:
    from elspeth.contracts.events import TelemetryEvent
    from elspeth.contracts.payload_store import PayloadStore
    from elspeth.engine.clock import Clock
    from elspeth.engine.coalesce_executor import CoalesceExecutor
    from elspeth.engine.executors import GateOutcome
    from elspeth.engine.orchestrator.types import RowPlugin
    from elspeth.telemetry import TelemetryManager

from elspeth.contracts.enums import NodeStateStatus, OutputMode, RoutingKind, RoutingMode, TriggerType
from elspeth.contracts.errors import OrchestrationInvariantError, TransformErrorReason
from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.results import FailureInfo
from elspeth.core.config import AggregationSettings, GateSettings
from elspeth.core.landscape import LandscapeRecorder
from elspeth.engine.clock import DEFAULT_CLOCK
from elspeth.engine.executors import (
    AggregationExecutor,
    GateExecutor,
    TransformExecutor,
)
from elspeth.engine.retry import MaxRetriesExceeded, RetryManager
from elspeth.engine.spans import SpanFactory
from elspeth.engine.tokens import TokenManager
from elspeth.plugins.clients.llm import LLMClientError
from elspeth.plugins.protocols import BatchTransformProtocol, GateProtocol, TransformProtocol

# Iteration guard to prevent infinite loops from bugs
MAX_WORK_QUEUE_ITERATIONS = 10_000


@dataclass(frozen=True, slots=True)
class DAGTraversalContext:
    """Precomputed DAG traversal data for the processor. Built by orchestrator.

    All dict fields are stored as MappingProxyType to enforce true
    immutability — frozen=True only prevents attribute reassignment,
    not mutation of mutable values held by those attributes.
    """

    node_step_map: Mapping[NodeID, int]
    node_to_plugin: Mapping[NodeID, RowPlugin | GateSettings]
    first_transform_node_id: NodeID | None
    node_to_next: Mapping[NodeID, NodeID | None]
    coalesce_node_map: Mapping[CoalesceName, NodeID]

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_step_map", MappingProxyType(dict(self.node_step_map)))
        object.__setattr__(self, "node_to_plugin", MappingProxyType(dict(self.node_to_plugin)))
        object.__setattr__(self, "node_to_next", MappingProxyType(dict(self.node_to_next)))
        object.__setattr__(self, "coalesce_node_map", MappingProxyType(dict(self.coalesce_node_map)))


def make_step_resolver(
    node_step_map: Mapping[NodeID, int],
    source_node_id: NodeID,
) -> StepResolver:
    """Create a StepResolver from a precomputed step map.

    Single source of truth for audit step resolution. Used by both RowProcessor
    (for its internal executors) and the orchestrator (for CoalesceExecutor and
    its TokenManager, which are constructed before the processor).

    Resolution order:
    1. Known node in step_map → return mapped step
    2. Source node (not in map) → return 0
    3. Unknown node → raise OrchestrationInvariantError
    """
    # Defensive copy so callers can't mutate the map after creation
    _map = dict(node_step_map)
    _source = source_node_id

    def resolve(node_id: NodeID) -> int:
        if node_id in _map:
            return _map[node_id]
        if node_id == _source:
            return 0
        raise OrchestrationInvariantError(f"Node ID '{node_id}' missing from traversal step map")

    return resolve


@dataclass(frozen=True)
class _WorkItem:
    """Item in the work queue for DAG processing.

    Frozen to prevent post-construction mutation. Use _create_work_item()
    factory method for construction with coalesce node resolution.
    """

    token: TokenInfo
    current_node_id: NodeID | None
    coalesce_node_id: NodeID | None = None
    coalesce_name: CoalesceName | None = None  # Name of the coalesce point (if any)
    on_success_sink: str | None = None  # Inherited sink for terminal children (deagg)

    def __post_init__(self) -> None:
        has_id = self.coalesce_node_id is not None
        has_name = self.coalesce_name is not None
        if has_id != has_name:
            raise OrchestrationInvariantError(
                f"_WorkItem coalesce fields must be both set or both None: "
                f"coalesce_node_id={self.coalesce_node_id}, coalesce_name={self.coalesce_name}"
            )


class RowProcessor:
    """Processes rows through the DAG-defined pipeline topology.

    Processing follows the DAG topology built from explicit input/on_success
    connections. Transforms, gates, and aggregations are interleaved per their
    declared wiring — there is no fixed "transforms first, then gates" order.

    Handles:
    1. Creating initial tokens from source rows
    2. Executing transforms, gates, and aggregations per DAG traversal order
    3. Routing tokens to sinks or downstream processing nodes
    4. Recording final outcomes via Landscape audit trail

    Example:
        processor = RowProcessor(
            recorder, span_factory, run_id, source_node_id,
            traversal=traversal_context,
        )

        result = processor.process_row(
            row_index=0,
            source_row=SourceRow.valid({"value": 42}, contract=contract),
            transforms=[transform1, transform2],
            ctx=ctx,
        )
    """

    def __init__(
        self,
        recorder: LandscapeRecorder,
        span_factory: SpanFactory,
        run_id: str,
        source_node_id: NodeID,
        *,
        source_on_success: str,
        edge_map: dict[tuple[NodeID, str], str] | None = None,
        route_resolution_map: dict[tuple[NodeID, str], RouteDestination] | None = None,
        traversal: DAGTraversalContext,
        aggregation_settings: dict[NodeID, AggregationSettings] | None = None,
        retry_manager: RetryManager | None = None,
        coalesce_executor: CoalesceExecutor | None = None,
        branch_to_coalesce: dict[BranchName, CoalesceName] | None = None,
        branch_to_sink: dict[BranchName, SinkName] | None = None,
        sink_names: frozenset[str] | None = None,
        coalesce_on_success_map: dict[CoalesceName, str] | None = None,
        restored_aggregation_state: dict[NodeID, dict[str, Any]] | None = None,
        payload_store: PayloadStore | None = None,
        clock: Clock | None = None,
        max_workers: int | None = None,
        telemetry_manager: TelemetryManager | None = None,
    ) -> None:
        """Initialize processor.

        Args:
            recorder: Landscape recorder
            span_factory: Span factory for tracing
            run_id: Current run ID
            source_node_id: Source node ID
            source_on_success: Source's on_success sink name for COMPLETED routing
            edge_map: Map of (node_id, label) -> edge_id
            route_resolution_map: Map of (node_id, label) -> resolved route destination
            traversal: Precomputed DAG traversal context from orchestrator
            aggregation_settings: Map of node_id -> AggregationSettings for trigger evaluation
            retry_manager: Optional retry manager for transform execution
            coalesce_executor: Optional coalesce executor for fork/join operations
            branch_to_coalesce: Map of branch_name -> coalesce_name for fork/join routing
            sink_names: Set of valid sink names for route resolution validation.
                If None, sink validation on jump-target resolution is skipped.
            coalesce_on_success_map: Map of coalesce_name -> terminal sink_name
                for COALESCED outcomes produced at terminal coalesce points
            restored_aggregation_state: Map of node_id -> state dict for crash recovery
            payload_store: Optional PayloadStore for persisting source row payloads
            clock: Optional clock for time access. Defaults to system clock.
                   Inject MockClock for deterministic testing.
            max_workers: Maximum concurrent workers for transform execution (None = no limit)
            telemetry_manager: Optional TelemetryManager for emitting telemetry events.
                               If None, telemetry emission is disabled.
        """
        self._recorder = recorder
        self._spans = span_factory
        self._run_id = run_id
        self._source_node_id: NodeID = source_node_id
        self._source_on_success: str = source_on_success
        self._traversal = traversal
        self._node_step_map: dict[NodeID, int] = dict(traversal.node_step_map)
        self._step_resolver: StepResolver = make_step_resolver(traversal.node_step_map, source_node_id)
        self._node_to_plugin: dict[NodeID, RowPlugin | GateSettings] = dict(traversal.node_to_plugin)
        self._first_transform_node_id: NodeID | None = traversal.first_transform_node_id
        self._node_to_next: dict[NodeID, NodeID | None] = dict(traversal.node_to_next)
        self._retry_manager = retry_manager
        self._coalesce_executor = coalesce_executor
        self._coalesce_node_ids: dict[CoalesceName, NodeID] = dict(traversal.coalesce_node_map)
        self._coalesce_name_by_node_id: dict[NodeID, CoalesceName] = {
            node_id: coalesce_name for coalesce_name, node_id in self._coalesce_node_ids.items()
        }
        self._structural_node_ids: frozenset[NodeID] = frozenset(nid for nid in self._node_to_next if nid not in self._node_to_plugin)
        self._branch_to_coalesce: dict[BranchName, CoalesceName] = branch_to_coalesce or {}
        self._branch_to_sink: dict[BranchName, SinkName] = branch_to_sink or {}
        overlap = set(self._branch_to_coalesce.keys()) & set(self._branch_to_sink.keys())
        if overlap:
            raise OrchestrationInvariantError(
                f"Branch names {sorted(overlap)} appear in both branch_to_coalesce and branch_to_sink. "
                "A fork branch must route to EITHER a coalesce node OR a direct sink, not both."
            )
        self._sink_names: frozenset[str] = sink_names or frozenset()
        self._coalesce_on_success_map: dict[CoalesceName, str] = coalesce_on_success_map or {}
        self._aggregation_settings: dict[NodeID, AggregationSettings] = aggregation_settings or {}
        self._clock = clock if clock is not None else DEFAULT_CLOCK

        # Build error edge map: transform node_id -> DIVERT edge_id.
        # Scans edge_map for __error_{name}__ labels (created by dag.py for transforms
        # with on_error pointing to a real sink, not "discard").
        _edge_map = edge_map or {}
        error_edge_ids: dict[NodeID, str] = {}
        for (node_id, label), edge_id in _edge_map.items():
            if label.startswith("__error_") and label.endswith("__"):
                error_edge_ids[node_id] = edge_id
        self._error_edge_ids = error_edge_ids

        self._token_manager = TokenManager(
            recorder,
            step_resolver=self._step_resolver,
            payload_store=payload_store,
        )
        self._transform_executor = TransformExecutor(
            recorder,
            span_factory,
            self._step_resolver,
            max_workers=max_workers,
            error_edge_ids=error_edge_ids,
        )
        self._gate_executor = GateExecutor(recorder, span_factory, self._step_resolver, edge_map, route_resolution_map)
        self._aggregation_executor = AggregationExecutor(
            recorder,
            span_factory,
            self._step_resolver,
            run_id,
            aggregation_settings=aggregation_settings,
            clock=self._clock,
        )
        self._telemetry_manager = telemetry_manager

        # Restore aggregation state if provided (crash recovery)
        if restored_aggregation_state:
            for node_id, state in restored_aggregation_state.items():
                self._aggregation_executor.restore_state(node_id, state)

    @property
    def token_manager(self) -> TokenManager:
        """Expose token manager for orchestrator to create tokens for quarantined rows."""
        return self._token_manager

    def _create_work_item(
        self,
        *,
        token: TokenInfo,
        current_node_id: NodeID | None,
        coalesce_name: CoalesceName | None = None,
        coalesce_node_id: NodeID | None = None,
        on_success_sink: str | None = None,
    ) -> _WorkItem:
        """Create node-id based work item."""
        resolved_coalesce_node_id = coalesce_node_id
        if resolved_coalesce_node_id is None and coalesce_name is not None:
            resolved_coalesce_node_id = self._coalesce_node_ids[coalesce_name]

        return _WorkItem(
            token=token,
            current_node_id=current_node_id,
            coalesce_node_id=resolved_coalesce_node_id,
            coalesce_name=coalesce_name,
            on_success_sink=on_success_sink,
        )

    def resolve_node_step(self, node_id: NodeID) -> int:
        """Resolve a node ID to processor step index (0-indexed)."""
        if node_id not in self._node_step_map:
            raise OrchestrationInvariantError(f"Node ID '{node_id}' missing from traversal step map")
        return self._node_step_map[node_id]

    def resolve_sink_step(self) -> int:
        """Resolve the audit step index for sink writes.

        Sinks are always the last step in processing, after all transforms,
        gates, aggregations, and coalesce nodes. Returns max(step_map) + 1.
        """
        return max(self._node_step_map.values()) + 1

    def _resolve_plugin_for_node(self, node_id: NodeID) -> TransformProtocol | GateProtocol | GateSettings | None:
        """Resolve the plugin/gate associated with a processing node.

        Returns None for structural nodes (e.g. coalesce points) that exist in
        the DAG traversal but have no plugin to execute. The caller skips these
        nodes and continues to the next processing node.

        Raises OrchestrationInvariantError for unknown nodes that are neither
        plugin-bearing nor structural — this would indicate a graph construction bug.
        """
        if node_id in self._node_to_plugin:
            return self._node_to_plugin[node_id]
        if node_id in self._structural_node_ids:
            return None
        raise OrchestrationInvariantError(
            f"Node ID '{node_id}' is neither a plugin node nor a known structural node (coalesce). "
            f"Plugin nodes: {sorted(self._node_to_plugin.keys())}, "
            f"structural nodes: {sorted(self._structural_node_ids)}"
        )

    def _resolve_next_node_for_processing(self, node_id: NodeID) -> NodeID | None:
        """Resolve the next processing node from traversal metadata."""
        if node_id not in self._node_to_next:
            raise OrchestrationInvariantError(
                f"Node ID '{node_id}' missing from traversal next-node map (terminal nodes must have explicit None entries)"
            )
        return self._node_to_next[node_id]

    def _resolve_audit_step_for_node(self, node_id: NodeID) -> int:
        """Resolve 1-indexed audit step for a processing node.

        Delegates to the factory-produced StepResolver (make_step_resolver).
        """
        return self._step_resolver(node_id)

    def _resolve_continuation_node_for_work_item(self, current_node_id: NodeID) -> NodeID | None:
        """Resolve next processing node for continuation work."""
        return self._resolve_next_node_for_processing(current_node_id)

    def _resolve_jump_target_on_success_sink(self, start_node_id: NodeID) -> str | None:
        """Resolve terminal on_success sink reachable from a route jump target."""
        node_id: NodeID | None = start_node_id
        resolved_sink: str | None = None
        iterations = 0
        max_iterations = len(self._node_to_next) + 1

        while node_id is not None:
            iterations += 1
            if iterations > max_iterations:
                raise OrchestrationInvariantError(
                    f"Jump-target sink resolution exceeded {max_iterations} iterations from node '{start_node_id}'. "
                    "Possible cycle in traversal map."
                )

            plugin = self._resolve_plugin_for_node(node_id)
            if isinstance(plugin, TransformProtocol) and plugin.on_success is not None:
                candidate_sink = plugin.on_success
                if not self._sink_names or candidate_sink in self._sink_names:
                    resolved_sink = candidate_sink

            next_node_id = self._resolve_next_node_for_processing(node_id)
            if next_node_id is None and node_id in self._coalesce_name_by_node_id:
                coalesce_name = self._coalesce_name_by_node_id[node_id]
                if coalesce_name not in self._coalesce_on_success_map:
                    raise OrchestrationInvariantError(
                        f"Coalesce '{coalesce_name}' not in on_success map. "
                        f"Available: {sorted(self._coalesce_on_success_map.keys())}. "
                        f"Walk started at node '{start_node_id}'."
                    )
                resolved_sink = self._coalesce_on_success_map[coalesce_name]

            node_id = next_node_id

        if resolved_sink is not None and self._sink_names and resolved_sink not in self._sink_names:
            raise OrchestrationInvariantError(
                f"Jump-target sink resolution returned '{resolved_sink}' which is not a configured sink. "
                f"Available sinks: {sorted(self._sink_names)}. Walk started at node '{start_node_id}'."
            )
        return resolved_sink

    def _create_continuation_work_item(
        self,
        *,
        token: TokenInfo,
        current_node_id: NodeID,
        coalesce_name: CoalesceName | None = None,
        on_success_sink: str | None = None,
    ) -> _WorkItem:
        """Create child work item that continues after current node or resumes at coalesce."""
        if coalesce_name is not None:
            coalesce_node_id = self._coalesce_node_ids[coalesce_name]
            return self._create_work_item(
                token=token,
                current_node_id=coalesce_node_id,
                coalesce_name=coalesce_name,
                coalesce_node_id=coalesce_node_id,
                on_success_sink=on_success_sink,
            )

        return self._create_work_item(
            token=token,
            current_node_id=self._resolve_continuation_node_for_work_item(current_node_id),
            on_success_sink=on_success_sink,
        )

    def _emit_telemetry(self, event: TelemetryEvent) -> None:
        """Emit telemetry event if manager is configured.

        Telemetry is emitted AFTER Landscape recording succeeds. Landscape is
        the legal record; telemetry is operational visibility.

        Args:
            event: The telemetry event to emit
        """
        if self._telemetry_manager is not None:
            self._telemetry_manager.handle_event(event)

    def _emit_transform_completed(
        self,
        token: TokenInfo,
        transform: TransformProtocol,
        transform_result: TransformResult,
    ) -> None:
        """Emit TransformCompleted telemetry event.

        Called AFTER Landscape recording succeeds in TransformExecutor.

        Args:
            token: Token that was processed
            transform: Transform that was executed
            transform_result: Result from the transform execution
        """
        if self._telemetry_manager is None:
            return

        from datetime import UTC, datetime

        from elspeth.contracts import TransformCompleted
        from elspeth.contracts.enums import NodeStateStatus

        status = NodeStateStatus.COMPLETED if transform_result.status == "success" else NodeStateStatus.FAILED

        # node_id is assigned during DAG construction in from_plugin_instances()
        assert transform.node_id is not None, "node_id must be assigned by DAG construction before execution"
        self._emit_telemetry(
            TransformCompleted(
                timestamp=datetime.now(UTC),
                run_id=self._run_id,
                row_id=token.row_id,
                token_id=token.token_id,
                node_id=transform.node_id,
                plugin_name=transform.name,
                status=status,
                duration_ms=transform_result.duration_ms or 0.0,
                input_hash=transform_result.input_hash,
                output_hash=transform_result.output_hash,
            )
        )

    def _emit_gate_evaluated(
        self,
        token: TokenInfo,
        gate_name: str,
        gate_node_id: str,
        routing_mode: RoutingMode,
        destinations: tuple[str, ...],
    ) -> None:
        """Emit GateEvaluated telemetry event.

        Called AFTER Landscape recording succeeds in GateExecutor.

        Args:
            token: Token that was routed
            gate_name: Name of the gate plugin
            gate_node_id: Node ID of the gate
            routing_mode: How routing was performed (move, copy)
            destinations: Destination node/sink names
        """
        if self._telemetry_manager is None:
            return

        from datetime import UTC, datetime

        from elspeth.contracts import GateEvaluated

        self._emit_telemetry(
            GateEvaluated(
                timestamp=datetime.now(UTC),
                run_id=self._run_id,
                row_id=token.row_id,
                token_id=token.token_id,
                node_id=gate_node_id,
                plugin_name=gate_name,
                routing_mode=routing_mode,
                destinations=destinations,
            )
        )

    def _emit_token_completed(
        self,
        token: TokenInfo,
        outcome: RowOutcome,
        sink_name: str | None = None,
    ) -> None:
        """Emit TokenCompleted telemetry event.

        Called AFTER Landscape recording succeeds (record_token_outcome).

        Args:
            token: Token that reached terminal state
            outcome: Terminal outcome (completed, routed, failed, etc.)
            sink_name: Destination sink if applicable
        """
        if self._telemetry_manager is None:
            return

        from datetime import UTC, datetime

        from elspeth.contracts import TokenCompleted

        self._emit_telemetry(
            TokenCompleted(
                timestamp=datetime.now(UTC),
                run_id=self._run_id,
                row_id=token.row_id,
                token_id=token.token_id,
                outcome=outcome,
                sink_name=sink_name,
            )
        )

    def _get_gate_destinations(self, outcome: GateOutcome) -> tuple[str, ...]:
        """Extract destination names from gate outcome for telemetry.

        Args:
            outcome: The gate outcome containing routing information

        Returns:
            Tuple of destination names (sink names or path names for forks)
        """
        if outcome.sink_name is not None:
            return (outcome.sink_name,)
        elif outcome.result.action.kind == RoutingKind.FORK_TO_PATHS:
            # For forks, return the branch names of child tokens
            return tuple(child.branch_name for child in outcome.child_tokens if child.branch_name)
        elif outcome.next_node_id is not None and outcome.result.action.kind == RoutingKind.ROUTE:
            # For route-label processing branches, report the chosen route label.
            return outcome.result.action.destinations
        else:
            # Continue routing - destination is "continue"
            return ("continue",)

    # ─────────────────────────────────────────────────────────────────────────
    # Public facade for aggregation timeout checking
    # (Bug fix: P1-2026-01-22 - provides clean API for orchestrator timeout checks)
    # ─────────────────────────────────────────────────────────────────────────

    def check_aggregation_timeout(self, node_id: NodeID) -> tuple[bool, TriggerType | None]:
        """Check if an aggregation should flush due to timeout.

        This is a public facade for orchestrator to check timeout conditions
        without directly accessing private _aggregation_executor.

        Note: This method is called in the hot path (before every row is processed),
        so it uses the optimized check_flush_status() which does a single dict
        lookup instead of two separate calls.

        Args:
            node_id: The aggregation node ID to check

        Returns:
            Tuple of (should_flush, trigger_type):
            - should_flush: True if trigger condition is met
            - trigger_type: The type of trigger that fired (TIMEOUT, COUNT, etc.) or None
        """
        return self._aggregation_executor.check_flush_status(node_id)

    def get_aggregation_buffer_count(self, node_id: NodeID) -> int:
        """Get the number of rows buffered in an aggregation.

        Args:
            node_id: The aggregation node ID

        Returns:
            Number of rows currently buffered
        """
        return self._aggregation_executor.get_buffer_count(node_id)

    def get_aggregation_checkpoint_state(self) -> dict[str, Any]:
        """Get checkpoint state for all aggregation buffers.

        Returns complete state of all aggregation nodes (buffers + triggers)
        for persistence during checkpointing. This enables crash recovery
        without losing buffered rows.

        Returns:
            Checkpoint state dict suitable for passing to create_checkpoint().
            Format matches AggregationExecutor.get_checkpoint_state().
        """
        return self._aggregation_executor.get_checkpoint_state()

    def handle_timeout_flush(
        self,
        node_id: NodeID,
        transform: TransformProtocol,
        ctx: PluginContext,
        trigger_type: TriggerType,
    ) -> tuple[list[RowResult], list[_WorkItem]]:
        """Handle an aggregation flush with proper output_mode semantics.

        This method mirrors the flush handling in _process_batch_aggregation_node but
        is designed for flushes that occur outside normal row processing:
        - TIMEOUT: Triggered between row arrivals when timeout expires
        - END_OF_SOURCE: Triggered at end of source to flush remaining buffers

        Handles all output_modes correctly:
        - passthrough: Routes all buffered tokens through remaining transforms
        - transform: Creates new tokens via expand_token (N→M output)

        Args:
            node_id: The aggregation node ID
            transform: The batch-aware transform to execute
            ctx: Plugin context
            trigger_type: The trigger type (TIMEOUT or END_OF_SOURCE)

        Returns:
            Tuple of (results, work_items):
            - results: RowResults for completed tokens (terminal state)
            - work_items: _WorkItem list for tokens needing further processing
        """
        # Get aggregation settings for output_mode
        settings = self._aggregation_settings[node_id]
        output_mode = settings.output_mode

        # Execute flush with the specified trigger type
        result, buffered_tokens, _batch_id = self._aggregation_executor.execute_flush(
            node_id=node_id,
            transform=cast(BatchTransformProtocol, transform),  # Runtime guarantees batch-aware
            ctx=ctx,
            trigger_type=trigger_type,
        )

        child_items: list[_WorkItem] = []
        results: list[RowResult] = []

        if result.status != "success":
            # Flush failed - handle based on output_mode
            #
            # CRITICAL: Token outcome recording depends on output_mode:
            # - passthrough: tokens have BUFFERED (non-terminal) → record FAILED
            # - transform: tokens have CONSUMED_IN_BATCH (terminal) → cannot record FAILED
            #
            # For transform mode, the batch failure is already recorded in the
            # batches table by execute_flush(). The CONSUMED_IN_BATCH outcome remains
            # semantically correct (tokens were consumed into a batch that failed).
            # Recording FAILED would violate the unique terminal outcome constraint.
            error_msg = "Batch transform failed during timeout flush"
            error_hash = hashlib.sha256(error_msg.encode()).hexdigest()[:16]

            if output_mode == OutputMode.PASSTHROUGH:
                # Passthrough mode: tokens have BUFFERED outcome (non-terminal)
                # Record FAILED to give them a terminal outcome
                for token in buffered_tokens:
                    self._recorder.record_token_outcome(
                        run_id=self._run_id,
                        token_id=token.token_id,
                        outcome=RowOutcome.FAILED,
                        error_hash=error_hash,
                    )
                    # Emit TokenCompleted telemetry AFTER Landscape recording
                    self._emit_token_completed(token, RowOutcome.FAILED)
                    results.append(
                        RowResult(
                            token=token,
                            final_data=token.row_data,
                            outcome=RowOutcome.FAILED,
                            error=FailureInfo(
                                exception_type="TransformError",
                                message=error_msg,
                            ),
                        )
                    )
            else:
                # Single/transform mode: tokens already have CONSUMED_IN_BATCH (terminal)
                # DO NOT record FAILED - would violate unique terminal outcome constraint
                # Return FAILED results for count tracking, but no DB recording needed
                #
                # Bug P2-2026-02-01: Emit TokenCompleted for all buffered tokens.
                # TokenCompleted was deferred from buffer time to maintain ordering.
                # Even on failed flush, tokens have CONSUMED_IN_BATCH outcome (terminal).
                # Note: TransformCompleted is NOT emitted on error path (no successful processing).
                for token in buffered_tokens:
                    self._emit_token_completed(token, RowOutcome.CONSUMED_IN_BATCH)
                    results.append(
                        RowResult(
                            token=token,
                            final_data=token.row_data,
                            outcome=RowOutcome.FAILED,
                            error=FailureInfo(
                                exception_type="TransformError",
                                message=error_msg,
                            ),
                        )
                    )

            return (results, child_items)

        # SUCCESS PATH: Emit TransformCompleted telemetry for all buffered tokens
        # Each input token was processed by this aggregation transform as part of the batch.
        # Emitting per-token (rather than per-batch) maintains consistency with regular
        # transform telemetry and allows accurate token counting in observability dashboards.
        for token in buffered_tokens:
            self._emit_transform_completed(
                token=token,
                transform=transform,
                transform_result=result,
            )

        # Continue downstream only when there is a next processing node.
        has_downstream_processing = self._resolve_next_node_for_processing(node_id) is not None

        # Derive coalesce metadata from buffered tokens' branch_name
        # For timeout/end-of-source flushes, we need to preserve coalesce path
        # so tokens can still join at coalesce points after aggregation
        coalesce_node_id: NodeID | None = None
        coalesce_name: CoalesceName | None = None
        if buffered_tokens:
            branch_name = buffered_tokens[0].branch_name
            if branch_name and BranchName(branch_name) in self._branch_to_coalesce:
                coalesce_name = self._branch_to_coalesce[BranchName(branch_name)]
                coalesce_node_id = self._coalesce_node_ids[coalesce_name]

        if output_mode == OutputMode.PASSTHROUGH:
            # Passthrough: original tokens continue with enriched data
            if not result.is_multi_row:
                raise ValueError(
                    f"Passthrough mode requires multi-row result, "
                    f"but transform '{transform.name}' returned single row. "
                    f"Use TransformResult.success_multi() for passthrough."
                )

            if result.rows is None:
                raise RuntimeError("Multi-row result has rows=None")
            if len(result.rows) != len(buffered_tokens):
                raise ValueError(
                    f"Passthrough mode requires same number of output rows "
                    f"as input rows. Transform '{transform.name}' returned "
                    f"{len(result.rows)} rows but received {len(buffered_tokens)} input rows."
                )

            # Transforms return PipelineRow objects in result.rows — use directly
            pipeline_rows = list(result.rows)

            for token, enriched_data in zip(buffered_tokens, pipeline_rows, strict=True):
                # Update token with enriched data, preserving all lineage metadata
                updated_token = token.with_updated_data(enriched_data)

                # Check if token needs to go to a coalesce point
                # This must happen EVEN if no more transforms - coalesce may be last step
                needs_coalesce = coalesce_node_id is not None and coalesce_name is not None and updated_token.branch_name is not None

                if has_downstream_processing or needs_coalesce:
                    work_item_coalesce_name = coalesce_name if needs_coalesce else None
                    child_items.append(
                        self._create_continuation_work_item(
                            token=updated_token,
                            current_node_id=node_id,
                            coalesce_name=work_item_coalesce_name,
                        )
                    )
                else:
                    # No more transforms and no coalesce - return COMPLETED
                    if transform.on_success is None:
                        raise OrchestrationInvariantError(
                            f"Aggregation transform '{transform.name}' reached terminal position "
                            f"but has no on_success configured. This is a DAG validation bug."
                        )
                    results.append(
                        RowResult(
                            token=updated_token,
                            final_data=enriched_data,
                            outcome=RowOutcome.COMPLETED,
                            sink_name=transform.on_success,
                        )
                    )

        elif output_mode == OutputMode.TRANSFORM:
            # Transform mode: N input rows -> M output rows with NEW tokens
            #
            # Bug P2-2026-02-01: Emit TokenCompleted for all buffered tokens AFTER
            # TransformCompleted (emitted in the TransformCompleted block above).
            # TokenCompleted was deferred from buffer time to maintain correct ordering.
            for token in buffered_tokens:
                self._emit_token_completed(token, RowOutcome.CONSUMED_IN_BATCH)

            # Get output rows
            if result.is_multi_row:
                if result.rows is None:
                    raise RuntimeError("Multi-row result has rows=None")
                output_rows = result.rows
            else:
                # Contract: batch-aware transforms in transform mode MUST return output data
                if result.row is None:
                    raise RuntimeError(
                        f"Aggregation transform '{transform.name}' returned None for result.row "
                        f"in 'transform' mode. Batch-aware transforms must return a row via "
                        f"TransformResult.success(row) or rows via TransformResult.success_multi(rows). "
                        f"This is a plugin bug."
                    )
                output_rows = [result.row]

            # Enforce expected_output_count if configured (plugin contract validation)
            if settings.expected_output_count is not None:
                actual_count = len(output_rows)
                if actual_count != settings.expected_output_count:
                    raise RuntimeError(
                        f"Aggregation '{settings.name}' produced {actual_count} output row(s), "
                        f"but expected_output_count={settings.expected_output_count}. "
                        f"This is a plugin contract violation."
                    )

            # Create new tokens via expand_token using first buffered token as parent
            # NOTE: Don't record EXPANDED - batch parents get CONSUMED_IN_BATCH separately
            if buffered_tokens:
                # Extract contract from first output row (all rows share same contract)
                output_contract = output_rows[0].contract

                expanded_tokens, _expand_group_id = self._token_manager.expand_token(
                    parent_token=buffered_tokens[0],
                    expanded_rows=[row.to_dict() for row in output_rows],
                    output_contract=output_contract,
                    node_id=node_id,
                    run_id=self._run_id,
                    record_parent_outcome=False,
                )

                # Check if expanded tokens need to go to a coalesce point
                # This must happen EVEN if no more transforms - coalesce may be last step
                # Use first expanded token to check branch_name
                first_expanded_branch = expanded_tokens[0].branch_name if expanded_tokens else None
                needs_coalesce = coalesce_node_id is not None and coalesce_name is not None and first_expanded_branch is not None

                if has_downstream_processing or needs_coalesce:
                    work_item_coalesce_name = coalesce_name if needs_coalesce else None
                    for token in expanded_tokens:
                        child_items.append(
                            self._create_continuation_work_item(
                                token=token,
                                current_node_id=node_id,
                                coalesce_name=work_item_coalesce_name,
                            )
                        )
                else:
                    # No more transforms and no coalesce - return COMPLETED
                    if transform.on_success is None:
                        raise OrchestrationInvariantError(
                            f"Aggregation transform '{transform.name}' reached terminal position "
                            f"but has no on_success configured. This is a DAG validation bug."
                        )
                    for token in expanded_tokens:
                        results.append(
                            RowResult(
                                token=token,
                                final_data=token.row_data,
                                outcome=RowOutcome.COMPLETED,
                                sink_name=transform.on_success,
                            )
                        )

        else:
            raise ValueError(f"Unknown output_mode: {output_mode}")

        return (results, child_items)

    def _process_batch_aggregation_node(
        self,
        transform: TransformProtocol,
        current_token: TokenInfo,
        ctx: PluginContext,
        child_items: list[_WorkItem],
        coalesce_node_id: NodeID | None = None,
        coalesce_name: CoalesceName | None = None,
    ) -> tuple[RowResult | list[RowResult], list[_WorkItem]]:
        """Process a row at an aggregation node using engine buffering.

        Engine buffers rows and calls transform.process(rows: list[dict])
        when the trigger fires.

        TEMPORAL DECOUPLING (Bug P2-2026-02-01):

        For transform-mode aggregation, there is intentional temporal decoupling
        between Landscape recording and telemetry emission:

        - **Landscape (audit trail)**: Records CONSUMED_IN_BATCH at buffer time.
          This is the source of truth - the token IS terminal when buffered.

        - **Telemetry (observability)**: Emits TokenCompleted at flush time.
          Deferred to maintain ordering invariant (TransformCompleted before
          TokenCompleted for each token).

        DO NOT assume "Landscape recording and telemetry emission happen together"
        for transform-mode aggregation. These two events have different timestamps.

        This decoupling is necessary because:
        1. Tokens become terminal (CONSUMED_IN_BATCH) when buffered
        2. But TransformCompleted can only fire when the batch actually processes
        3. Telemetry ordering requires TransformCompleted before TokenCompleted
        4. Therefore TokenCompleted must be deferred to flush time

        Args:
            transform: The batch-aware transform
            current_token: Current row token
            ctx: Plugin context
            child_items: Work items to return with result
            coalesce_node_id: Node ID at which fork children should coalesce (optional)
            coalesce_name: Name of the coalesce point for merging (optional)

        Returns:
            (RowResult or list[RowResult], child_items) tuple
            - Single RowResult for transform mode (or list if N→M output)
            - List of RowResults for passthrough mode (one per buffered token)
        """
        raw_node_id = transform.node_id
        if raw_node_id is None:
            raise OrchestrationInvariantError("Node ID is None during edge resolution")
        node_id = NodeID(raw_node_id)

        # Get output_mode from aggregation settings
        # Caller guarantees node_id is in self._aggregation_settings (checked in _handle_aggregation_node)
        settings = self._aggregation_settings[node_id]
        output_mode = settings.output_mode

        # Buffer the row
        self._aggregation_executor.buffer_row(node_id, current_token)

        # Check if we should flush
        if self._aggregation_executor.should_flush(node_id):
            # Determine trigger type
            trigger_type = self._aggregation_executor.get_trigger_type(node_id)
            if trigger_type is None:
                trigger_type = TriggerType.COUNT  # Default if no evaluator

            # Execute flush with full audit recording
            result, buffered_tokens, batch_id = self._aggregation_executor.execute_flush(
                node_id=node_id,
                transform=cast(BatchTransformProtocol, transform),  # Runtime guarantees batch-aware
                ctx=ctx,
                trigger_type=trigger_type,
            )

            if result.status != "success":
                # Flush failed - handle based on output_mode
                #
                # CRITICAL: Token outcome recording depends on output_mode:
                # - passthrough: tokens have BUFFERED (non-terminal) → record FAILED
                # - transform: tokens have CONSUMED_IN_BATCH (terminal) → cannot record FAILED
                #
                # For transform mode, the batch failure is already recorded in the
                # batches table by execute_flush(). The CONSUMED_IN_BATCH outcome remains
                # semantically correct (tokens were consumed into a batch that failed).
                # Recording FAILED would violate the unique terminal outcome constraint.
                error_msg = "Batch transform failed"
                error_hash = hashlib.sha256(error_msg.encode()).hexdigest()[:16]

                results: list[RowResult] = []
                if output_mode == OutputMode.PASSTHROUGH:
                    # Passthrough mode: tokens have BUFFERED outcome (non-terminal)
                    # Record FAILED for ALL buffered tokens to give them terminal outcome
                    for token in buffered_tokens:
                        self._recorder.record_token_outcome(
                            run_id=self._run_id,
                            token_id=token.token_id,
                            outcome=RowOutcome.FAILED,
                            error_hash=error_hash,
                        )
                        # Emit TokenCompleted telemetry AFTER Landscape recording
                        self._emit_token_completed(token, RowOutcome.FAILED)
                        results.append(
                            RowResult(
                                token=token,
                                final_data=token.row_data,
                                outcome=RowOutcome.FAILED,
                                error=FailureInfo(
                                    exception_type="TransformError",
                                    message=error_msg,
                                ),
                            )
                        )
                else:
                    # Single/transform mode: PREVIOUSLY buffered tokens have CONSUMED_IN_BATCH
                    # (recorded when they were buffered via the non-flushing return path in
                    # _process_transform_with_aggregation). However, the TRIGGERING token
                    # (current_token) went straight from buffer_row() to execute_flush(),
                    # skipping the non-flushing path. It needs CONSUMED_IN_BATCH.
                    #
                    # Record CONSUMED_IN_BATCH for triggering token only.
                    # DO NOT record FAILED - would violate unique terminal outcome constraint.
                    # Return FAILED results for count tracking, but no additional DB recording
                    # needed for previously buffered tokens.
                    self._recorder.record_token_outcome(
                        run_id=self._run_id,
                        token_id=current_token.token_id,
                        outcome=RowOutcome.CONSUMED_IN_BATCH,
                        batch_id=batch_id,
                    )

                    # Bug P2-2026-02-01: Emit TokenCompleted for ALL buffered tokens.
                    # TokenCompleted was deferred from buffer time to maintain ordering.
                    # Even on failed flush, tokens have CONSUMED_IN_BATCH outcome (terminal).
                    # Note: TransformCompleted is NOT emitted on error path (no successful processing).
                    # Note: buffered_tokens includes the triggering token (buffered before flush check).
                    for token in buffered_tokens:
                        self._emit_token_completed(token, RowOutcome.CONSUMED_IN_BATCH)

                    for token in buffered_tokens:
                        results.append(
                            RowResult(
                                token=token,
                                final_data=token.row_data,
                                outcome=RowOutcome.FAILED,
                                error=FailureInfo(
                                    exception_type="TransformError",
                                    message=error_msg,
                                ),
                            )
                        )
                return (results, child_items)

            # SUCCESS PATH: Emit TransformCompleted telemetry for all buffered tokens
            # Each input token was processed by this aggregation transform as part of the batch.
            # Emitting per-token (rather than per-batch) maintains consistency with regular
            # transform telemetry and allows accurate token counting in observability dashboards.
            #
            # NOTE: For transform mode, the triggering token (current_token) also needs
            # TransformCompleted, but it's emitted in the transform-mode block below AFTER
            # its Landscape recording and BEFORE its TokenCompleted (Bug P2-2026-02-01).
            for token in buffered_tokens:
                self._emit_transform_completed(
                    token=token,
                    transform=transform,
                    transform_result=result,
                )

            # Handle output modes
            if output_mode == OutputMode.PASSTHROUGH:
                # Passthrough: original tokens continue with enriched data
                # Validate result is multi-row
                if not result.is_multi_row:
                    raise ValueError(
                        f"Passthrough mode requires multi-row result, "
                        f"but transform '{transform.name}' returned single row. "
                        f"Use TransformResult.success_multi() for passthrough."
                    )

                # Validate row count matches
                if result.rows is None:
                    raise RuntimeError("Multi-row result has rows=None")
                if len(result.rows) != len(buffered_tokens):
                    raise ValueError(
                        f"Passthrough mode requires same number of output rows "
                        f"as input rows. Transform '{transform.name}' returned "
                        f"{len(result.rows)} rows but received {len(buffered_tokens)} input rows."
                    )

                # Transforms return PipelineRow objects in result.rows — use directly
                pipeline_rows = list(result.rows)

                # Build COMPLETED results for all buffered tokens with enriched data
                # Continue downstream only when there is a next processing node.
                has_downstream_processing = self._resolve_next_node_for_processing(node_id) is not None

                # Check if tokens need to go to a coalesce point
                # This must happen EVEN if no more transforms - coalesce may be last step
                # Use first buffered token to check branch_name (all should have same branch)
                first_token_branch = buffered_tokens[0].branch_name if buffered_tokens else None
                needs_coalesce = coalesce_node_id is not None and coalesce_name is not None and first_token_branch is not None

                if has_downstream_processing or needs_coalesce:
                    work_item_coalesce_name = coalesce_name if needs_coalesce else None
                    for token, enriched_data in zip(buffered_tokens, pipeline_rows, strict=True):
                        # Update token, preserving all lineage metadata
                        updated_token = token.with_updated_data(enriched_data)
                        child_items.append(
                            self._create_continuation_work_item(
                                token=updated_token,
                                current_node_id=node_id,
                                coalesce_name=work_item_coalesce_name,
                            )
                        )
                    # Return empty list - all results will come from child items
                    return ([], child_items)
                else:
                    # No more transforms and no coalesce - return COMPLETED for all tokens
                    if transform.on_success is None:
                        raise OrchestrationInvariantError(
                            f"Aggregation transform '{transform.name}' reached terminal position "
                            f"but has no on_success configured. This is a DAG validation bug."
                        )
                    passthrough_results: list[RowResult] = []
                    for token, enriched_data in zip(buffered_tokens, pipeline_rows, strict=True):
                        # Update token, preserving all lineage metadata
                        updated_token = token.with_updated_data(enriched_data)
                        # Convert PipelineRow to dict for final_data (RowResult expects dict)
                        passthrough_results.append(
                            RowResult(
                                token=updated_token,
                                final_data=enriched_data.to_dict(),
                                outcome=RowOutcome.COMPLETED,
                                sink_name=transform.on_success,
                            )
                        )
                    return (passthrough_results, child_items)

            elif output_mode == OutputMode.TRANSFORM:
                # Transform mode: N input rows -> M output rows with NEW tokens
                # Previously-buffered tokens already returned CONSUMED_IN_BATCH
                # when they were buffered (non-flushing path at bottom of method).
                # Only the triggering token (current_token) hasn't been returned yet.
                # New tokens are created for output rows via expand_token()

                # Get output rows - can be single or multi
                if result.is_multi_row:
                    if result.rows is None:
                        raise RuntimeError("Multi-row result has rows=None")
                    output_rows = result.rows
                else:
                    # Contract: batch-aware transforms in transform mode MUST return output data
                    if result.row is None:
                        raise RuntimeError(
                            f"Aggregation transform '{transform.name}' returned None for result.row "
                            f"in 'transform' mode. Batch-aware transforms must return a row via "
                            f"TransformResult.success(row) or rows via TransformResult.success_multi(rows). "
                            f"This is a plugin bug."
                        )
                    output_rows = [result.row]

                # Enforce expected_output_count if configured (plugin contract validation)
                if settings.expected_output_count is not None:
                    actual_count = len(output_rows)
                    if actual_count != settings.expected_output_count:
                        raise RuntimeError(
                            f"Aggregation '{settings.name}' produced {actual_count} output row(s), "
                            f"but expected_output_count={settings.expected_output_count}. "
                            f"This is a plugin contract violation."
                        )

                # Create new tokens via expand_token using triggering token as parent
                # This establishes audit trail linkage
                # NOTE: Don't record EXPANDED - triggering token gets CONSUMED_IN_BATCH below

                # Extract contract from first output row (all rows share same contract)
                output_contract = output_rows[0].contract

                expanded_tokens, _expand_group_id = self._token_manager.expand_token(
                    parent_token=current_token,
                    expanded_rows=[row.to_dict() for row in output_rows],
                    output_contract=output_contract,
                    node_id=node_id,
                    run_id=self._run_id,
                    record_parent_outcome=False,
                )

                # The triggering token becomes CONSUMED_IN_BATCH
                # Note: batch_id comes from execute_flush() which captured it before reset
                self._recorder.record_token_outcome(
                    run_id=self._run_id,
                    token_id=current_token.token_id,
                    outcome=RowOutcome.CONSUMED_IN_BATCH,
                    batch_id=batch_id,
                )

                # Bug P2-2026-02-01: Emit TokenCompleted for ALL buffered tokens
                # TransformCompleted was already emitted for all tokens (including current_token)
                # in the TransformCompleted emission loop (buffered_tokens includes the triggering
                # token because buffer_row() adds it before should_flush() is checked).
                #
                # TokenCompleted was deferred from buffer time for non-triggering tokens to
                # maintain correct ordering (TransformCompleted before TokenCompleted).
                # Now emit TokenCompleted for all of them.
                for token in buffered_tokens:
                    self._emit_token_completed(token, RowOutcome.CONSUMED_IN_BATCH)

                triggering_result = RowResult(
                    token=current_token,
                    final_data=current_token.row_data,
                    outcome=RowOutcome.CONSUMED_IN_BATCH,
                )

                # Continue downstream only when there is a next processing node.
                has_downstream_processing = self._resolve_next_node_for_processing(node_id) is not None

                # Check if expanded tokens need to go to a coalesce point
                # This must happen EVEN if no more transforms - coalesce may be last step
                # Use first expanded token to check branch_name
                first_expanded_branch = expanded_tokens[0].branch_name if expanded_tokens else None
                needs_coalesce = coalesce_node_id is not None and coalesce_name is not None and first_expanded_branch is not None

                if has_downstream_processing or needs_coalesce:
                    work_item_coalesce_name = coalesce_name if needs_coalesce else None
                    for token in expanded_tokens:
                        child_items.append(
                            self._create_continuation_work_item(
                                token=token,
                                current_node_id=node_id,
                                coalesce_name=work_item_coalesce_name,
                            )
                        )
                    # Return triggering result - expanded tokens will produce results via work queue
                    return (triggering_result, child_items)
                else:
                    # No more transforms and no coalesce - return COMPLETED for expanded tokens
                    if transform.on_success is None:
                        raise OrchestrationInvariantError(
                            f"Aggregation transform '{transform.name}' reached terminal position "
                            f"but has no on_success configured. This is a DAG validation bug."
                        )
                    output_results: list[RowResult] = [triggering_result]
                    for token in expanded_tokens:
                        output_results.append(
                            RowResult(
                                token=token,
                                final_data=token.row_data,
                                outcome=RowOutcome.COMPLETED,
                                sink_name=transform.on_success,
                            )
                        )
                    # Return triggering + completed results
                    return (output_results, child_items)

            else:
                raise ValueError(f"Unknown output_mode: {output_mode}")

        # Not flushing yet - row is buffered
        # In passthrough mode: BUFFERED (non-terminal, will reappear)
        # In transform mode: CONSUMED_IN_BATCH (terminal)
        if output_mode == OutputMode.PASSTHROUGH:
            buf_batch_id = self._aggregation_executor.get_batch_id(node_id)
            self._recorder.record_token_outcome(
                run_id=self._run_id,
                token_id=current_token.token_id,
                outcome=RowOutcome.BUFFERED,
                batch_id=buf_batch_id,
            )
            return (
                RowResult(
                    token=current_token,
                    final_data=current_token.row_data,
                    outcome=RowOutcome.BUFFERED,
                ),
                child_items,
            )
        else:
            nf_batch_id = self._aggregation_executor.get_batch_id(node_id)
            self._recorder.record_token_outcome(
                run_id=self._run_id,
                token_id=current_token.token_id,
                outcome=RowOutcome.CONSUMED_IN_BATCH,
                batch_id=nf_batch_id,
            )
            # NOTE: Do NOT emit TokenCompleted telemetry here!
            # Bug P2-2026-02-01: TokenCompleted must be deferred to flush time so that
            # TransformCompleted can be emitted first. The token IS terminal in Landscape
            # (CONSUMED_IN_BATCH recorded above), but telemetry ordering requires waiting
            # until the batch actually processes at flush time.
            return (
                RowResult(
                    token=current_token,
                    final_data=current_token.row_data,
                    outcome=RowOutcome.CONSUMED_IN_BATCH,
                ),
                child_items,
            )

    def _execute_transform_with_retry(
        self,
        transform: Any,
        token: TokenInfo,
        ctx: PluginContext,
    ) -> tuple[TransformResult, TokenInfo, str | None]:
        """Execute transform with optional retry for transient failures.

        Retry behavior:
        - If retry_manager is None: single attempt, no retry
        - If retry_manager is set: retry on transient exceptions

        Each attempt is recorded separately in the audit trail with attempt number.

        Note: TransformResult.error() is NOT retried - that's a processing error,
        not a transient failure. Only exceptions trigger retry.

        Args:
            transform: Transform to execute
            token: Current token
            ctx: Plugin context

        Returns:
            Tuple of (TransformResult, updated TokenInfo, error_sink)
        """
        if self._retry_manager is None:
            # No retry configured - single attempt
            # Must still catch retryable exceptions and convert to error results
            # to keep failures row-scoped (don't abort entire run)
            try:
                return self._transform_executor.execute_transform(
                    transform=transform,
                    token=token,
                    ctx=ctx,
                    attempt=0,
                )
            except LLMClientError as e:
                if e.retryable:
                    # Retryable error but no retry manager configured - convert to error result
                    # This keeps the failure row-scoped instead of aborting the run
                    #
                    # BUG FIX (P2-2026-01-27): Must validate on_error and record transform_error
                    # for audit trail completeness (same as TransformExecutor error handling)
                    on_error = transform.on_error
                    if on_error is None:
                        raise RuntimeError(
                            f"Transform '{transform.name}' raised retryable LLMClientError but has no "
                            f"on_error configured. Either configure on_error or enable retry. "
                            f"Error: {e}"
                        ) from e

                    error_details: TransformErrorReason = {"reason": "llm_retryable_error_no_retry", "error": str(e)}
                    ctx.record_transform_error(
                        token_id=token.token_id,
                        transform_id=transform.node_id,
                        row=token.row_data,
                        error_details=error_details,
                        destination=on_error,
                    )

                    # Record DIVERT routing_event using ctx.state_id (set by
                    # TransformExecutor.execute_transform before the exception propagated).
                    if on_error != "discard":
                        try:
                            error_edge_id = self._error_edge_ids[NodeID(transform.node_id)]
                        except KeyError:
                            raise OrchestrationInvariantError(
                                f"Transform '{transform.node_id}' has on_error={on_error!r} but no DIVERT edge registered."
                            ) from e
                        assert ctx.state_id is not None, (
                            f"ctx.state_id must be set by TransformExecutor before exception propagated (transform={transform.node_id})"
                        )
                        self._recorder.record_routing_event(
                            state_id=ctx.state_id,
                            edge_id=error_edge_id,
                            mode=RoutingMode.DIVERT,
                            reason=error_details,
                        )

                    return (
                        TransformResult.error(error_details, retryable=True),
                        token,
                        on_error,
                    )
                # Non-retryable errors re-raise (already handled by transform)
                raise
            except (ConnectionError, TimeoutError, OSError) as e:
                # Other retryable errors - convert to error result
                #
                # BUG FIX (P2-2026-01-27): Must validate on_error and record transform_error
                # for audit trail completeness (same as TransformExecutor error handling)
                on_error = transform.on_error
                if on_error is None:
                    raise RuntimeError(
                        f"Transform '{transform.name}' raised retryable {type(e).__name__} but has no "
                        f"on_error configured. Either configure on_error or enable retry. "
                        f"Error: {e}"
                    ) from e

                transient_error: TransformErrorReason = {"reason": "transient_error_no_retry", "error": str(e)}
                ctx.record_transform_error(
                    token_id=token.token_id,
                    transform_id=transform.node_id,
                    row=token.row_data,
                    error_details=transient_error,
                    destination=on_error,
                )

                # Record DIVERT routing_event using ctx.state_id (set by
                # TransformExecutor.execute_transform before the exception propagated).
                if on_error != "discard":
                    try:
                        error_edge_id = self._error_edge_ids[NodeID(transform.node_id)]
                    except KeyError:
                        raise OrchestrationInvariantError(
                            f"Transform '{transform.node_id}' has on_error={on_error!r} but no DIVERT edge registered."
                        ) from e
                    assert ctx.state_id is not None, (
                        f"ctx.state_id must be set by TransformExecutor before exception propagated (transform={transform.node_id})"
                    )
                    self._recorder.record_routing_event(
                        state_id=ctx.state_id,
                        edge_id=error_edge_id,
                        mode=RoutingMode.DIVERT,
                        reason=transient_error,
                    )

                return (
                    TransformResult.error(transient_error, retryable=True),
                    token,
                    on_error,
                )

        # Track attempt number for audit
        attempt_tracker = {"current": 0}

        def execute_attempt() -> tuple[TransformResult, TokenInfo, str | None]:
            attempt = attempt_tracker["current"]
            attempt_tracker["current"] += 1
            return self._transform_executor.execute_transform(
                transform=transform,
                token=token,
                ctx=ctx,
                attempt=attempt,
            )

        def is_retryable(e: BaseException) -> bool:
            # Retry transient errors (network, timeout, rate limit)
            # Don't retry programming errors (AttributeError, TypeError, etc.)
            #
            # LLMClientError has a retryable attribute:
            # - RateLimitError, NetworkError, ServerError: retryable=True
            # - ContentPolicyError, ContextLengthError: retryable=False
            if isinstance(e, LLMClientError):
                return e.retryable
            return isinstance(e, ConnectionError | TimeoutError | OSError)

        return self._retry_manager.execute_with_retry(
            operation=execute_attempt,
            is_retryable=is_retryable,
        )

    def process_row(
        self,
        row_index: int,
        source_row: SourceRow,
        transforms: list[Any],
        ctx: PluginContext,
        *,
        coalesce_node_id: NodeID | None = None,
        coalesce_name: CoalesceName | None = None,
    ) -> list[RowResult]:
        """Process a row through all transforms.

        Uses a work queue to handle fork operations - when a fork creates
        child tokens, they are added to the queue and processed through
        the remaining transforms.

        Args:
            row_index: Position in source
            source_row: SourceRow from source (must have contract)
            transforms: List of transform plugins
            ctx: Plugin context
            coalesce_node_id: Node ID at which fork children should coalesce
            coalesce_name: Name of the coalesce point for merging

        Returns:
            List of RowResults, one per terminal token (parent + children)
        """
        # Create initial token from SourceRow
        # TokenManager.create_initial_token() expects SourceRow and converts to PipelineRow
        token = self._token_manager.create_initial_token(
            run_id=self._run_id,
            source_node_id=self._source_node_id,
            row_index=row_index,
            source_row=source_row,
        )

        # Record source node_state (step_index=0) for audit lineage.
        # Source "processing" already happened in the plugin iterator — we record
        # the result immediately as COMPLETED with duration_ms=0.
        # Valid SourceRows always have dict data (SourceRow.valid() takes dict[str, Any]).
        source_input: dict[str, Any] = source_row.row
        source_state = self._recorder.begin_node_state(
            token_id=token.token_id,
            node_id=self._source_node_id,
            run_id=self._run_id,
            step_index=0,
            input_data=source_input,
        )
        self._recorder.complete_node_state(
            state_id=source_state.state_id,
            status=NodeStateStatus.COMPLETED,
            output_data=source_input,
            duration_ms=0,
        )

        if transforms and self._first_transform_node_id is None:
            raise OrchestrationInvariantError("Traversal context is missing first_transform_node_id for non-empty transform pipeline")
        initial_node_id = self._first_transform_node_id if self._first_transform_node_id is not None else self._source_node_id
        return self._drain_work_queue(
            self._create_work_item(
                token=token,
                current_node_id=initial_node_id,
                coalesce_node_id=coalesce_node_id,
                coalesce_name=coalesce_name,
            ),
            transforms,
            ctx,
        )

    def process_existing_row(
        self,
        row_id: str,
        row_data: PipelineRow,
        transforms: list[Any],
        ctx: PluginContext,
        *,
        coalesce_node_id: NodeID | None = None,
        coalesce_name: CoalesceName | None = None,
    ) -> list[RowResult]:
        """Process an existing row (row already in database, create new token only).

        Used during resume when rows were created in the original run
        but need to be reprocessed. Unlike process_row(), this does NOT
        create a new row record - only a new token.

        Args:
            row_id: Existing row ID in the database
            row_data: Row data (retrieved from payload store)
            transforms: List of transform plugins
            ctx: Plugin context
            coalesce_node_id: Node ID at which fork children should coalesce
            coalesce_name: Name of the coalesce point for merging

        Returns:
            List of RowResults, one per terminal token (parent + children)
        """
        # Create token for existing row (NOT a new row)
        token = self._token_manager.create_token_for_existing_row(
            row_id=row_id,
            row_data=row_data,
        )

        # Record source node_state (step_index=0) for resumed token lineage.
        # The row already exists from the original run, but this new token
        # needs its own source state for complete audit lineage.
        resumed_input = row_data.to_dict()
        source_state = self._recorder.begin_node_state(
            token_id=token.token_id,
            node_id=self._source_node_id,
            run_id=self._run_id,
            step_index=0,
            input_data=resumed_input,
        )
        self._recorder.complete_node_state(
            state_id=source_state.state_id,
            status=NodeStateStatus.COMPLETED,
            output_data=resumed_input,
            duration_ms=0,
        )

        if transforms and self._first_transform_node_id is None:
            raise OrchestrationInvariantError("Traversal context is missing first_transform_node_id for non-empty transform pipeline")
        initial_node_id = self._first_transform_node_id if self._first_transform_node_id is not None else self._source_node_id
        return self._drain_work_queue(
            self._create_work_item(
                token=token,
                current_node_id=initial_node_id,
                coalesce_node_id=coalesce_node_id,
                coalesce_name=coalesce_name,
            ),
            transforms,
            ctx,
        )

    def process_token(
        self,
        token: TokenInfo,
        transforms: list[Any],
        ctx: PluginContext,
        *,
        current_node_id: NodeID,
        coalesce_node_id: NodeID | None = None,
        coalesce_name: CoalesceName | None = None,
    ) -> list[RowResult]:
        """Process an existing token through the pipeline starting at current_node_id.

        Used for mid-pipeline coalesce merges that must continue processing.
        """
        return self._drain_work_queue(
            self._create_work_item(
                token=token,
                current_node_id=current_node_id,
                coalesce_node_id=coalesce_node_id,
                coalesce_name=coalesce_name,
            ),
            transforms,
            ctx,
        )

    def _maybe_coalesce_token(
        self,
        current_token: TokenInfo,
        *,
        current_node_id: NodeID,
        coalesce_node_id: NodeID | None,
        coalesce_name: CoalesceName | None,
        child_items: list[_WorkItem],
    ) -> tuple[bool, RowResult | None]:
        if (
            self._coalesce_executor is None
            or current_token.branch_name is None
            or coalesce_name is None
            or coalesce_node_id is None
            or current_node_id != coalesce_node_id
        ):
            return False, None

        coalesce_outcome = self._coalesce_executor.accept(
            token=current_token,
            coalesce_name=coalesce_name,
        )

        if coalesce_outcome.held:
            return True, None

        if coalesce_outcome.merged_token is not None:
            if self._resolve_next_node_for_processing(coalesce_node_id) is None:
                if coalesce_name is None:
                    raise OrchestrationInvariantError("Terminal coalesce outcome missing coalesce_name")
                sink_name = self._coalesce_on_success_map[coalesce_name]
                return (
                    True,
                    RowResult(
                        token=coalesce_outcome.merged_token,
                        final_data=coalesce_outcome.merged_token.row_data,
                        outcome=RowOutcome.COALESCED,
                        sink_name=sink_name,
                    ),
                )

            coalesce_node_id = self._coalesce_node_ids[coalesce_name]
            child_items.append(
                self._create_work_item(
                    token=coalesce_outcome.merged_token,
                    current_node_id=coalesce_node_id,
                )
            )
            return True, None

        if coalesce_outcome.failure_reason:
            error_msg = coalesce_outcome.failure_reason
            error_hash = hashlib.sha256(error_msg.encode()).hexdigest()[:16]

            # Bug 9z8 fix: Only record if CoalesceExecutor didn't already record
            if not coalesce_outcome.outcomes_recorded:
                self._recorder.record_token_outcome(
                    run_id=self._run_id,
                    token_id=current_token.token_id,
                    outcome=RowOutcome.FAILED,
                    error_hash=error_hash,
                )
            # Emit TokenCompleted telemetry AFTER Landscape recording
            self._emit_token_completed(current_token, RowOutcome.FAILED)

            return (
                True,
                RowResult(
                    token=current_token,
                    final_data=current_token.row_data,
                    outcome=RowOutcome.FAILED,
                    error=FailureInfo(
                        exception_type="CoalesceFailure",
                        message=error_msg,
                    ),
                ),
            )

        raise OrchestrationInvariantError(
            f"CoalesceOutcome for token {current_token.token_id} in coalesce '{coalesce_name}' "
            f"is in invalid state: held={coalesce_outcome.held}, "
            f"merged_token={coalesce_outcome.merged_token is not None}, "
            f"failure_reason={coalesce_outcome.failure_reason!r}"
        )

    def _notify_coalesce_of_lost_branch(
        self,
        current_token: TokenInfo,
        reason: str,
        child_items: list[_WorkItem],
    ) -> list[RowResult]:
        """Notify the coalesce executor that a forked branch was diverted.

        Called when a forked token exits the pipeline early (error-routed,
        quarantined, or failed). The coalesce executor re-evaluates merge
        conditions and may trigger an immediate merge or failure for held
        sibling tokens.

        Args:
            current_token: The forked token being diverted
            reason: Machine-readable reason for the diversion
            child_items: Mutable work queue — merged tokens are appended here

        Returns:
            List of RowResults for sibling tokens that failed as a consequence
            of the branch loss, or a COALESCED RowResult if the merge triggered
            at a terminal coalesce step. Empty if no consequences yet.
        """
        if self._coalesce_executor is None or current_token.branch_name is None:
            return []

        coalesce_name = self._branch_to_coalesce.get(BranchName(current_token.branch_name))
        if coalesce_name is None:
            return []

        coalesce_node_id = self._coalesce_node_ids[coalesce_name]
        outcome = self._coalesce_executor.notify_branch_lost(
            coalesce_name=coalesce_name,
            row_id=current_token.row_id,
            lost_branch=current_token.branch_name,
            reason=reason,
        )

        if outcome is None:
            return []

        if outcome.merged_token is not None:
            if self._resolve_next_node_for_processing(coalesce_node_id) is None:
                sink_name = self._coalesce_on_success_map[coalesce_name]
                # Terminal coalesce — no downstream transforms.
                # Do NOT emit TokenCompleted here: the merged token still
                # needs to flow through the sink write for durable recording.
                # Telemetry is emitted later by accumulate_row_outcomes.
                return [
                    RowResult(
                        token=outcome.merged_token,
                        final_data=outcome.merged_token.row_data,
                        outcome=RowOutcome.COALESCED,
                        sink_name=sink_name,
                    ),
                ]
            # Non-terminal — resume merged token at coalesce step
            child_items.append(
                self._create_work_item(
                    token=outcome.merged_token,
                    current_node_id=coalesce_node_id,
                )
            )
            return []

        if outcome.failure_reason:
            # Merge failed — build RowResults for held sibling tokens.
            # DB outcomes are already recorded by the executor (outcomes_recorded=True).
            # These RowResults propagate to the orchestrator for counter accounting.
            sibling_results: list[RowResult] = []
            for consumed_token in outcome.consumed_tokens:
                self._emit_token_completed(consumed_token, RowOutcome.FAILED)
                sibling_results.append(
                    RowResult(
                        token=consumed_token,
                        final_data=consumed_token.row_data,
                        outcome=RowOutcome.FAILED,
                        error=FailureInfo(
                            exception_type="CoalesceFailure",
                            message=outcome.failure_reason,
                        ),
                    )
                )
            return sibling_results

        return []

    def _drain_work_queue(
        self,
        initial_item: _WorkItem,
        transforms: list[Any],
        ctx: PluginContext,
    ) -> list[RowResult]:
        """Drain the work queue, processing tokens until empty.

        Implements breadth-first DAG traversal. Each _process_single_token call
        may produce child work items (from forks, expansions, etc.) which are
        appended to the queue.
        """
        work_queue: deque[_WorkItem] = deque([initial_item])
        results: list[RowResult] = []
        iterations = 0

        with self._spans.row_span(initial_item.token.row_id, initial_item.token.token_id):
            while work_queue:
                iterations += 1
                if iterations > MAX_WORK_QUEUE_ITERATIONS:
                    raise RuntimeError(f"Work queue exceeded {MAX_WORK_QUEUE_ITERATIONS} iterations. Possible infinite loop in pipeline.")

                item = work_queue.popleft()
                result, child_items = self._process_single_token(
                    token=item.token,
                    transforms=transforms,
                    ctx=ctx,
                    current_node_id=item.current_node_id,
                    coalesce_node_id=item.coalesce_node_id,
                    coalesce_name=item.coalesce_name,
                    on_success_sink=item.on_success_sink,
                )

                if result is not None:
                    if isinstance(result, list):
                        results.extend(result)
                    else:
                        results.append(result)

                work_queue.extend(child_items)

        return results

    def _process_single_token(
        self,
        token: TokenInfo,
        transforms: list[Any],
        ctx: PluginContext,
        current_node_id: NodeID | None,
        coalesce_node_id: NodeID | None = None,
        coalesce_name: CoalesceName | None = None,
        on_success_sink: str | None = None,
    ) -> tuple[RowResult | list[RowResult] | None, list[_WorkItem]]:
        """Process a single token through processing nodes starting at node_id.

        Args:
            token: Token to process
            transforms: List of transform plugins
            ctx: Plugin context
            current_node_id: Node ID to start processing from. None is valid only
                for terminal work items that already have explicit sink context
                (inherited on_success_sink or branch_to_sink mapping).
            coalesce_node_id: Node ID at which fork children should coalesce
            coalesce_name: Name of the coalesce point for merging
            on_success_sink: Inherited sink from parent (e.g. terminal deagg parent's on_success)

        Returns:
            Tuple of (RowResult or list of RowResults or None if held for coalesce,
                      list of child WorkItems to queue)
            - Single RowResult for most operations
            - List of RowResults for passthrough aggregation mode
            - None for held coalesce tokens
        """
        current_token = token
        child_items: list[_WorkItem] = []

        # current_node_id=None skips traversal loop entirely, so only allow it
        # when sink routing is explicit (inherited sink or branch->sink map).
        if current_node_id is None:
            has_branch_sink = current_token.branch_name is not None and BranchName(current_token.branch_name) in self._branch_to_sink
            if on_success_sink is None and not has_branch_sink:
                raise OrchestrationInvariantError(
                    f"Token {token.token_id} has current_node_id=None without explicit terminal sink context. "
                    "Expected inherited on_success_sink or branch_to_sink mapping."
                )

        last_on_success_sink: str = on_success_sink if on_success_sink is not None else self._source_on_success
        if coalesce_name is not None and current_node_id is not None:
            coalesce_node_id_for_name = self._coalesce_node_ids[coalesce_name]
            if coalesce_node_id_for_name == current_node_id and self._resolve_next_node_for_processing(current_node_id) is None:
                last_on_success_sink = self._coalesce_on_success_map[coalesce_name]

        # Invariant: tokens with coalesce metadata must not start downstream of their coalesce point.
        # A malformed work item starting past the coalesce node would silently skip coalesce handling
        # because _maybe_coalesce_token only triggers on exact node equality.
        if (
            coalesce_node_id is not None
            and current_node_id is not None
            and coalesce_name is not None
            and current_node_id != coalesce_node_id
            and current_node_id in self._node_step_map
            and coalesce_node_id in self._node_step_map
        ):
            current_step = self._node_step_map[current_node_id]
            coalesce_step = self._node_step_map[coalesce_node_id]
            if current_step > coalesce_step:
                raise OrchestrationInvariantError(
                    f"Token {token.token_id} started at node '{current_node_id}' (step {current_step}), "
                    f"which is downstream of coalesce '{coalesce_name}' (step {coalesce_step}). "
                    f"Work items with coalesce metadata must start at or before the coalesce point."
                )

        node_id: NodeID | None = current_node_id
        max_inner_iterations = len(self._node_to_next) + 1
        inner_iterations = 0
        while node_id is not None:
            inner_iterations += 1
            if inner_iterations > max_inner_iterations:
                raise OrchestrationInvariantError(
                    f"Inner traversal exceeded {max_inner_iterations} iterations for token "
                    f"{token.token_id}. Possible cycle in node_to_next map."
                )
            handled, result = self._maybe_coalesce_token(
                current_token,
                current_node_id=node_id,
                coalesce_node_id=coalesce_node_id,
                coalesce_name=coalesce_name,
                child_items=child_items,
            )
            if handled:
                return (result, child_items)

            next_node_id = self._resolve_next_node_for_processing(node_id)
            plugin = self._resolve_plugin_for_node(node_id)
            if plugin is None:
                # Non-processing structural nodes (e.g. coalesce) are traversed but not executed.
                node_id = next_node_id
                continue

            # Type-safe plugin detection using protocols (supports protocol-only plugins)
            if isinstance(plugin, GateProtocol):
                gate_plugin = plugin
                outcome = self._gate_executor.execute_gate(
                    gate=gate_plugin,
                    token=current_token,
                    ctx=ctx,
                    token_manager=self._token_manager,
                )
                current_token = outcome.updated_token

                # Emit GateEvaluated telemetry AFTER Landscape recording succeeds
                # (Landscape recording happens inside execute_gate)
                # node_id is assigned during DAG construction in from_plugin_instances()
                assert gate_plugin.node_id is not None, "node_id must be assigned by DAG construction before execution"
                self._emit_gate_evaluated(
                    token=current_token,
                    gate_name=gate_plugin.name,
                    gate_node_id=gate_plugin.node_id,
                    routing_mode=outcome.result.action.mode,
                    destinations=self._get_gate_destinations(outcome),
                )

                # Check if gate routed to a sink (sink_name set by executor)
                if outcome.sink_name is not None:
                    # NOTE: Do NOT record ROUTED outcome here - the token hasn't been written yet.
                    # SinkExecutor.write() records the outcome AFTER sink durability is achieved.
                    # This prevents duplicate outcomes and ensures correct audit semantics:
                    # outcome is recorded at actual completion, not at routing decision time.
                    return (
                        RowResult(
                            token=current_token,
                            final_data=current_token.row_data,
                            outcome=RowOutcome.ROUTED,
                            sink_name=outcome.sink_name,
                        ),
                        child_items,
                    )
                elif outcome.result.action.kind == RoutingKind.FORK_TO_PATHS:
                    for child_token in outcome.child_tokens:
                        # Look up coalesce info for this branch
                        branch_name = child_token.branch_name
                        child_coalesce_name: CoalesceName | None = None

                        if branch_name and BranchName(branch_name) in self._branch_to_coalesce:
                            child_coalesce_name = self._branch_to_coalesce[BranchName(branch_name)]

                        # Children skip directly to coalesce node (or continue to next node).
                        child_items.append(
                            self._create_continuation_work_item(
                                token=child_token,
                                current_node_id=node_id,
                                coalesce_name=child_coalesce_name,
                            )
                        )

                    # NOTE: Parent FORKED outcome is now recorded atomically in fork_token()
                    # to eliminate crash window between child creation and outcome recording.
                    return (
                        RowResult(
                            token=current_token,
                            final_data=current_token.row_data,
                            outcome=RowOutcome.FORKED,
                        ),
                        child_items,
                    )
                elif outcome.next_node_id is not None:
                    resolved_sink = self._resolve_jump_target_on_success_sink(outcome.next_node_id)
                    if resolved_sink is not None:
                        last_on_success_sink = resolved_sink
                    node_id = outcome.next_node_id
                    continue
                else:
                    # CONTINUE: gate says "proceed to next structural node."
                    # Falls through to node_id = next_node_id below.
                    if outcome.result.action.kind != RoutingKind.CONTINUE:
                        raise OrchestrationInvariantError(
                            f"Unhandled gate routing kind {outcome.result.action.kind!r} "
                            f"for token {current_token.token_id} at node '{node_id}'. "
                            f"Expected CONTINUE when no sink_name, fork, or next_node_id is set."
                        )

            elif isinstance(plugin, TransformProtocol):
                row_transform = plugin
                # Check if this is a batch-aware transform at an aggregation node
                transform_node_id = row_transform.node_id
                if row_transform.is_batch_aware and transform_node_id is not None and transform_node_id in self._aggregation_settings:
                    # Use engine buffering for aggregation
                    return self._process_batch_aggregation_node(
                        transform=row_transform,
                        current_token=current_token,
                        ctx=ctx,
                        child_items=child_items,
                        coalesce_node_id=coalesce_node_id,
                        coalesce_name=coalesce_name,
                    )

                # Regular transform (with optional retry)
                try:
                    transform_result, current_token, error_sink = self._execute_transform_with_retry(
                        transform=row_transform,
                        token=current_token,
                        ctx=ctx,
                    )
                    # Emit TransformCompleted telemetry AFTER Landscape recording succeeds
                    # (Landscape recording happens inside _execute_transform_with_retry)
                    self._emit_transform_completed(
                        token=current_token,
                        transform=row_transform,
                        transform_result=transform_result,
                    )
                except MaxRetriesExceeded as e:
                    # All retries exhausted - return FAILED outcome
                    error_hash = hashlib.sha256(str(e).encode()).hexdigest()[:16]
                    self._recorder.record_token_outcome(
                        run_id=self._run_id,
                        token_id=current_token.token_id,
                        outcome=RowOutcome.FAILED,
                        error_hash=error_hash,
                    )
                    # Emit TokenCompleted telemetry AFTER Landscape recording
                    self._emit_token_completed(current_token, RowOutcome.FAILED)
                    # Notify coalesce if this is a forked branch
                    sibling_results = self._notify_coalesce_of_lost_branch(
                        current_token,
                        f"max_retries_exceeded:{e}",
                        child_items,
                    )
                    current_result = RowResult(
                        token=current_token,
                        final_data=current_token.row_data,
                        outcome=RowOutcome.FAILED,
                        error=FailureInfo.from_max_retries_exceeded(e),
                    )
                    if sibling_results:
                        return ([current_result, *sibling_results], child_items)
                    return (current_result, child_items)

                if transform_result.status == "error":
                    # Determine outcome based on error routing
                    if error_sink == "discard":
                        # Intentionally discarded - QUARANTINED
                        error_detail = str(transform_result.reason) if transform_result.reason else "unknown_error"
                        quarantine_error_hash = hashlib.sha256(error_detail.encode()).hexdigest()[:16]
                        self._recorder.record_token_outcome(
                            run_id=self._run_id,
                            token_id=current_token.token_id,
                            outcome=RowOutcome.QUARANTINED,
                            error_hash=quarantine_error_hash,
                        )
                        # Emit TokenCompleted telemetry AFTER Landscape recording
                        self._emit_token_completed(current_token, RowOutcome.QUARANTINED)
                        # Notify coalesce if this is a forked branch
                        sibling_results = self._notify_coalesce_of_lost_branch(
                            current_token,
                            f"quarantined:{error_detail}",
                            child_items,
                        )
                        current_result = RowResult(
                            token=current_token,
                            final_data=current_token.row_data,
                            outcome=RowOutcome.QUARANTINED,
                        )
                        if sibling_results:
                            return ([current_result, *sibling_results], child_items)
                        return (current_result, child_items)
                    else:
                        # Routed to error sink
                        # NOTE: Do NOT record ROUTED outcome here - the token hasn't been written yet.
                        # SinkExecutor.write() records the outcome AFTER sink durability is achieved.
                        # Notify coalesce if this is a forked branch
                        error_detail = str(transform_result.reason) if transform_result.reason else "unknown_error"
                        sibling_results = self._notify_coalesce_of_lost_branch(
                            current_token,
                            f"error_routed:{error_detail}",
                            child_items,
                        )
                        current_result = RowResult(
                            token=current_token,
                            final_data=current_token.row_data,
                            outcome=RowOutcome.ROUTED,
                            sink_name=error_sink,
                        )
                        if sibling_results:
                            return ([current_result, *sibling_results], child_items)
                        return (current_result, child_items)

                # Track on_success for sink routing at end of chain
                if row_transform.on_success is not None:
                    last_on_success_sink = row_transform.on_success

                # Handle multi-row output (deaggregation)
                # NOTE: This is ONLY for non-aggregation transforms. Aggregation
                # transforms route through _process_batch_aggregation_node() above.
                if transform_result.is_multi_row:
                    # Validate transform is allowed to create tokens
                    if not row_transform.creates_tokens:
                        raise RuntimeError(
                            f"Transform '{row_transform.name}' returned multi-row result "
                            f"but has creates_tokens=False. Either set creates_tokens=True "
                            f"or return single row via TransformResult.success(row). "
                            f"(Multi-row is allowed in aggregation passthrough mode.)"
                        )

                    # Deaggregation: create child tokens for each output row
                    # NOTE: Parent EXPANDED outcome is recorded atomically in expand_token()

                    # is_multi_row check above guarantees rows is not None
                    assert transform_result.rows is not None, "is_multi_row guarantees rows is not None"
                    # Contract consistency is enforced by TransformResult.success_multi()
                    output_contract = transform_result.rows[0].contract
                    child_tokens, _expand_group_id = self._token_manager.expand_token(
                        parent_token=current_token,
                        expanded_rows=[r.to_dict() for r in transform_result.rows],
                        output_contract=output_contract,
                        node_id=node_id,
                        run_id=self._run_id,
                    )

                    # Queue each child for continued processing.
                    # Pass last_on_success_sink so terminal children inherit the
                    # expanding transform's sink instead of defaulting to source_on_success.
                    for child_token in child_tokens:
                        child_coalesce_name = coalesce_name if coalesce_name is not None and child_token.branch_name is not None else None
                        child_items.append(
                            self._create_continuation_work_item(
                                token=child_token,
                                current_node_id=node_id,
                                coalesce_name=child_coalesce_name,
                                on_success_sink=last_on_success_sink,
                            )
                        )

                    # NOTE: Parent EXPANDED outcome is recorded atomically in expand_token()
                    # to eliminate crash window between child creation and outcome recording.
                    return (
                        RowResult(
                            token=current_token,
                            final_data=current_token.row_data,
                            outcome=RowOutcome.EXPANDED,
                        ),
                        child_items,
                    )

                # Single row output (existing logic - current_token already updated
                # by _execute_transform_with_retry, continues to next transform)
            elif isinstance(plugin, GateSettings):
                gate_config = plugin
                outcome = self._gate_executor.execute_config_gate(
                    gate_config=gate_config,
                    node_id=node_id,
                    token=current_token,
                    ctx=ctx,
                    token_manager=self._token_manager,
                )
                current_token = outcome.updated_token

                # Emit GateEvaluated telemetry AFTER Landscape recording succeeds
                # (Landscape recording happens inside execute_config_gate)
                self._emit_gate_evaluated(
                    token=current_token,
                    gate_name=gate_config.name,
                    gate_node_id=node_id,
                    routing_mode=outcome.result.action.mode,
                    destinations=self._get_gate_destinations(outcome),
                )

                # Check if gate routed to a sink
                if outcome.sink_name is not None:
                    # NOTE: Do NOT record ROUTED outcome here - the token hasn't been written yet.
                    # SinkExecutor.write() records the outcome AFTER sink durability is achieved.
                    return (
                        RowResult(
                            token=current_token,
                            final_data=current_token.row_data,
                            outcome=RowOutcome.ROUTED,
                            sink_name=outcome.sink_name,
                        ),
                        child_items,
                    )
                elif outcome.result.action.kind == RoutingKind.FORK_TO_PATHS:
                    for child_token in outcome.child_tokens:
                        # Look up coalesce info for this branch
                        cfg_branch_name = child_token.branch_name
                        cfg_coalesce_name: CoalesceName | None = None

                        if cfg_branch_name and BranchName(cfg_branch_name) in self._branch_to_coalesce:
                            cfg_coalesce_name = self._branch_to_coalesce[BranchName(cfg_branch_name)]

                        # Children skip directly to coalesce step (or next processing node if no coalesce)
                        child_items.append(
                            self._create_continuation_work_item(
                                token=child_token,
                                current_node_id=node_id,
                                coalesce_name=cfg_coalesce_name,
                            )
                        )

                    # NOTE: Parent FORKED outcome is now recorded atomically in fork_token()
                    # to eliminate crash window between child creation and outcome recording.
                    return (
                        RowResult(
                            token=current_token,
                            final_data=current_token.row_data,
                            outcome=RowOutcome.FORKED,
                        ),
                        child_items,
                    )
                elif outcome.next_node_id is not None:
                    resolved_sink = self._resolve_jump_target_on_success_sink(outcome.next_node_id)
                    if resolved_sink is not None:
                        last_on_success_sink = resolved_sink
                    node_id = outcome.next_node_id
                    continue
                else:
                    # CONTINUE: config gate says "proceed to next structural node."
                    # Falls through to node_id = next_node_id below.
                    if outcome.result.action.kind != RoutingKind.CONTINUE:
                        raise OrchestrationInvariantError(
                            f"Unhandled config gate routing kind {outcome.result.action.kind!r} "
                            f"for token {current_token.token_id} at node '{node_id}'. "
                            f"Expected CONTINUE when no sink_name, fork, or next_node_id is set."
                        )

            else:
                raise TypeError(f"Unknown transform type: {type(plugin).__name__}. Expected BaseTransform or BaseGate.")

            node_id = next_node_id

        # Determine sink name from explicit routing maps. Fork children
        # targeting direct sinks are resolved via _branch_to_sink (built from
        # DAG COPY edges at construction time). Non-fork tokens use the last
        # transform's on_success or the source's on_success.
        effective_sink = last_on_success_sink
        if current_token.branch_name is not None:
            branch = BranchName(current_token.branch_name)
            if branch in self._branch_to_sink:
                effective_sink = self._branch_to_sink[branch]

        if not effective_sink or not effective_sink.strip():
            raise OrchestrationInvariantError(
                f"No effective sink for token {current_token.token_id}: "
                f"last_on_success_sink={last_on_success_sink!r}, "
                f"branch_name={current_token.branch_name!r}. "
                f"This indicates a DAG construction or on_success configuration bug."
            )

        return (
            RowResult(
                token=current_token,
                final_data=current_token.row_data,
                outcome=RowOutcome.COMPLETED,
                sink_name=effective_sink,
            ),
            child_items,
        )
