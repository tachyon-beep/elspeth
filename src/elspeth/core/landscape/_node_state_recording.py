# src/elspeth/core/landscape/_node_state_recording.py
"""Node state recording and routing event methods for LandscapeRecorder."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, overload

from sqlalchemy import select

from elspeth.contracts import (
    CoalesceFailureReason,
    NodeState,
    NodeStateCompleted,
    NodeStateFailed,
    NodeStateOpen,
    NodeStatePending,
    NodeStateStatus,
    RoutingEvent,
    RoutingMode,
    RoutingReason,
    RoutingSpec,
)
from elspeth.contracts.errors import AuditIntegrityError, ExecutionError, TransformErrorReason
from elspeth.core.canonical import canonical_json, stable_hash
from elspeth.core.landscape._helpers import generate_id, now
from elspeth.core.landscape.schema import (
    node_states_table,
    routing_events_table,
)

if TYPE_CHECKING:
    from elspeth.contracts.errors import TransformSuccessReason
    from elspeth.contracts.payload_store import PayloadStore
    from elspeth.core.landscape._database_ops import DatabaseOps
    from elspeth.core.landscape.database import LandscapeDB
    from elspeth.core.landscape.repositories import NodeStateRepository, RoutingEventRepository


class NodeStateRecordingMixin:
    """Node state and routing event methods. Mixed into LandscapeRecorder."""

    # Shared state annotations (set by LandscapeRecorder.__init__)
    _db: LandscapeDB
    _ops: DatabaseOps
    _node_state_repo: NodeStateRepository
    _routing_event_repo: RoutingEventRepository
    _payload_store: PayloadStore | None

    def begin_node_state(
        self,
        token_id: str,
        node_id: str,
        run_id: str,
        step_index: int,
        input_data: dict[str, Any],
        *,
        state_id: str | None = None,
        attempt: int = 0,
        context_before: dict[str, Any] | None = None,
    ) -> NodeStateOpen:
        """Begin recording a node state (token visiting a node).

        Args:
            token_id: Token being processed
            node_id: Node processing the token
            run_id: Run ID for composite FK to nodes table
            step_index: Position in token's execution path
            input_data: Input data for hashing
            state_id: Optional state ID (generated if not provided)
            attempt: Attempt number (0 for first attempt)
            context_before: Optional context snapshot before processing

        Returns:
            NodeStateOpen model with status=OPEN
        """
        state_id = state_id or generate_id()
        input_hash = stable_hash(input_data)
        timestamp = now()

        context_json = canonical_json(context_before) if context_before is not None else None

        state = NodeStateOpen(
            state_id=state_id,
            token_id=token_id,
            node_id=node_id,
            step_index=step_index,
            attempt=attempt,
            status=NodeStateStatus.OPEN,
            input_hash=input_hash,
            context_before_json=context_json,
            started_at=timestamp,
        )

        self._ops.execute_insert(
            node_states_table.insert().values(
                state_id=state.state_id,
                token_id=state.token_id,
                node_id=state.node_id,
                run_id=run_id,  # Added for composite FK to nodes
                step_index=state.step_index,
                attempt=state.attempt,
                status=state.status.value,
                input_hash=state.input_hash,
                context_before_json=state.context_before_json,
                started_at=state.started_at,
            )
        )

        return state

    @overload
    def complete_node_state(
        self,
        state_id: str,
        status: Literal[NodeStateStatus.PENDING],
        *,
        output_data: dict[str, Any] | list[dict[str, Any]] | None = None,
        duration_ms: float | None = None,
        error: ExecutionError | TransformErrorReason | CoalesceFailureReason | None = None,
        context_after: dict[str, Any] | None = None,
    ) -> NodeStatePending: ...

    @overload
    def complete_node_state(
        self,
        state_id: str,
        status: Literal[NodeStateStatus.COMPLETED],
        *,
        output_data: dict[str, Any] | list[dict[str, Any]] | None = None,
        duration_ms: float | None = None,
        error: ExecutionError | TransformErrorReason | CoalesceFailureReason | None = None,
        success_reason: TransformSuccessReason | None = None,
        context_after: dict[str, Any] | None = None,
    ) -> NodeStateCompleted: ...

    @overload
    def complete_node_state(
        self,
        state_id: str,
        status: Literal[NodeStateStatus.FAILED],
        *,
        output_data: dict[str, Any] | list[dict[str, Any]] | None = None,
        duration_ms: float | None = None,
        error: ExecutionError | TransformErrorReason | CoalesceFailureReason | None = None,
        context_after: dict[str, Any] | None = None,
    ) -> NodeStateFailed: ...

    def complete_node_state(
        self,
        state_id: str,
        status: NodeStateStatus,
        *,
        output_data: dict[str, Any] | list[dict[str, Any]] | None = None,
        duration_ms: float | None = None,
        error: ExecutionError | TransformErrorReason | CoalesceFailureReason | None = None,
        success_reason: TransformSuccessReason | None = None,
        context_after: dict[str, Any] | None = None,
    ) -> NodeStatePending | NodeStateCompleted | NodeStateFailed:
        """Complete a node state.

        Args:
            state_id: State to complete
            status: NodeStateStatus (PENDING, COMPLETED, or FAILED)
            output_data: Output data for hashing (if success)
            duration_ms: Processing duration (required)
            error: Error details (if failed)
            context_after: Optional context snapshot after processing

        Returns:
            NodeStatePending if status is pending, NodeStateCompleted if completed, NodeStateFailed if failed

        Raises:
            ValueError: If status is OPEN (not a valid terminal status)
            ValueError: If duration_ms is not provided
        """
        if status == NodeStateStatus.OPEN:
            raise ValueError("Cannot complete a node state with status OPEN")

        if duration_ms is None:
            raise ValueError("duration_ms is required when completing a node state")

        timestamp = now()
        output_hash = stable_hash(output_data) if output_data is not None else None
        error_json = canonical_json(error) if error is not None else None
        context_json = canonical_json(context_after) if context_after is not None else None
        # Serialize success reason if provided (use canonical_json for audit consistency)
        success_reason_json = canonical_json(success_reason) if success_reason is not None else None

        self._ops.execute_update(
            node_states_table.update()
            .where(node_states_table.c.state_id == state_id)
            .values(
                status=status.value,
                output_hash=output_hash,
                duration_ms=duration_ms,
                error_json=error_json,
                success_reason_json=success_reason_json,
                context_after_json=context_json,
                completed_at=timestamp,
            )
        )

        result = self.get_node_state(state_id)
        if result is None:
            raise AuditIntegrityError(f"NodeState {state_id} not found after update - database corruption or transaction failure")
        # Type narrowing: result is guaranteed to be terminal (PENDING/COMPLETED/FAILED)
        if isinstance(result, NodeStateOpen):
            raise AuditIntegrityError(f"NodeState {state_id} should be terminal after completion but has status OPEN")
        return result

    def get_node_state(self, state_id: str) -> NodeState | None:
        """Get a node state by ID.

        Args:
            state_id: State ID to retrieve

        Returns:
            NodeState (union of Open, Completed, or Failed) or None
        """
        query = select(node_states_table).where(node_states_table.c.state_id == state_id)
        row = self._ops.execute_fetchone(query)
        if row is None:
            return None
        return self._node_state_repo.load(row)

    def record_routing_event(
        self,
        state_id: str,
        edge_id: str,
        mode: RoutingMode,
        reason: RoutingReason | None = None,
        *,
        event_id: str | None = None,
        routing_group_id: str | None = None,
        ordinal: int = 0,
        reason_ref: str | None = None,
    ) -> RoutingEvent:
        """Record a single routing event.

        Args:
            state_id: Node state that made the routing decision
            edge_id: Edge that was taken
            mode: RoutingMode enum (MOVE or COPY)
            reason: Reason for this routing decision
            event_id: Optional event ID
            routing_group_id: Group ID (for multi-destination routing)
            ordinal: Position in routing group
            reason_ref: Optional payload store reference

        Returns:
            RoutingEvent model
        """
        event_id = event_id or generate_id()
        routing_group_id = routing_group_id or generate_id()
        reason_hash = stable_hash(reason) if reason else None
        timestamp = now()

        # Auto-persist reason to payload store if available and ref not provided
        # This enables exported audit trails to explain routing decisions
        if reason is not None and reason_ref is None and self._payload_store is not None:
            reason_bytes = canonical_json(reason).encode("utf-8")
            reason_ref = self._payload_store.store(reason_bytes)

        event = RoutingEvent(
            event_id=event_id,
            state_id=state_id,
            edge_id=edge_id,
            routing_group_id=routing_group_id,
            ordinal=ordinal,
            mode=mode,
            reason_hash=reason_hash,
            reason_ref=reason_ref,
            created_at=timestamp,
        )

        self._ops.execute_insert(
            routing_events_table.insert().values(
                event_id=event.event_id,
                state_id=event.state_id,
                edge_id=event.edge_id,
                routing_group_id=event.routing_group_id,
                ordinal=event.ordinal,
                mode=event.mode.value,  # Store string in DB
                reason_hash=event.reason_hash,
                reason_ref=event.reason_ref,
                created_at=event.created_at,
            )
        )

        return event

    def record_routing_events(
        self,
        state_id: str,
        routes: list[RoutingSpec],
        reason: RoutingReason | None = None,
    ) -> list[RoutingEvent]:
        """Record multiple routing events (fork/multi-destination).

        All events share the same routing_group_id.

        Args:
            state_id: Node state that made the routing decision
            routes: List of RoutingSpec objects specifying edge_id and mode
            reason: Shared reason for all routes

        Returns:
            List of RoutingEvent models
        """
        routing_group_id = generate_id()
        reason_hash = stable_hash(reason) if reason else None
        timestamp = now()
        events = []

        # Auto-persist shared reason to payload store if available
        # All events in the fork will reference the same reason payload
        reason_ref = None
        if reason is not None and self._payload_store is not None:
            reason_bytes = canonical_json(reason).encode("utf-8")
            reason_ref = self._payload_store.store(reason_bytes)

        with self._db.connection() as conn:
            for ordinal, route in enumerate(routes):
                event_id = generate_id()
                event = RoutingEvent(
                    event_id=event_id,
                    state_id=state_id,
                    edge_id=route.edge_id,
                    routing_group_id=routing_group_id,
                    ordinal=ordinal,
                    mode=route.mode,  # Already RoutingMode enum from RoutingSpec
                    reason_hash=reason_hash,
                    reason_ref=reason_ref,
                    created_at=timestamp,
                )

                conn.execute(
                    routing_events_table.insert().values(
                        event_id=event.event_id,
                        state_id=event.state_id,
                        edge_id=event.edge_id,
                        routing_group_id=event.routing_group_id,
                        ordinal=event.ordinal,
                        mode=event.mode.value,  # Store string in DB
                        reason_hash=event.reason_hash,
                        reason_ref=event.reason_ref,
                        created_at=event.created_at,
                    )
                )

                events.append(event)

        return events
