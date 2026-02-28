# src/elspeth/core/landscape/recorder.py
"""LandscapeRecorder: High-level API for audit recording.

This is the main interface for recording audit trail entries during
pipeline execution. It wraps the low-level database operations.

Implementation uses two patterns:

Composed repositories (owned instances, injected via __init__):
- run_lifecycle_repository.py: Run lifecycle (begin, complete, finalize, secrets, contracts)
- execution_repository.py: Node states, external calls, operations, batches, artifacts

Mixins (inherited behavior):
- _graph_recording.py: Node and edge registration/queries
- _token_recording.py: Row/token creation, fork/coalesce/expand, outcomes
- _error_recording.py: Validation and transform error recording
- _query_methods.py: Read-only entity queries, bulk retrieval, explain
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, overload

from elspeth.contracts import RunStatus

if TYPE_CHECKING:
    from elspeth.contracts import (
        Artifact,
        Batch,
        BatchMember,
        BatchStatus,
        Call,
        CallStatus,
        CallType,
        CoalesceFailureReason,
        ExportStatus,
        NodeState,
        NodeStateCompleted,
        NodeStateFailed,
        NodeStateOpen,
        NodeStatePending,
        NodeStateStatus,
        Operation,
        RoutingEvent,
        RoutingMode,
        RoutingReason,
        RoutingSpec,
        Run,
        SecretResolution,
        SecretResolutionInput,
        TriggerType,
    )
    from elspeth.contracts.call_data import CallPayload
    from elspeth.contracts.errors import ExecutionError, TransformErrorReason, TransformSuccessReason
    from elspeth.contracts.node_state_context import NodeStateContext
    from elspeth.contracts.payload_store import PayloadStore
    from elspeth.contracts.schema_contract import SchemaContract
    from elspeth.core.landscape.reproducibility import ReproducibilityGrade

from elspeth.core.landscape._database_ops import DatabaseOps
from elspeth.core.landscape._error_recording import ErrorRecordingMixin
from elspeth.core.landscape._graph_recording import GraphRecordingMixin
from elspeth.core.landscape._query_methods import QueryMethodsMixin
from elspeth.core.landscape._token_recording import TokenRecordingMixin
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.execution_repository import ExecutionRepository
from elspeth.core.landscape.model_loaders import (
    ArtifactLoader,
    BatchLoader,
    BatchMemberLoader,
    CallLoader,
    EdgeLoader,
    NodeLoader,
    NodeStateLoader,
    OperationLoader,
    RoutingEventLoader,
    RowLoader,
    RunLoader,
    TokenLoader,
    TokenOutcomeLoader,
    TokenParentLoader,
    TransformErrorLoader,
    ValidationErrorLoader,
)
from elspeth.core.landscape.run_lifecycle_repository import RunLifecycleRepository


class LandscapeRecorder(
    GraphRecordingMixin,
    TokenRecordingMixin,
    ErrorRecordingMixin,
    QueryMethodsMixin,
):
    """High-level API for recording audit trail entries.

    This class provides methods to record:
    - Runs and their configuration
    - Nodes (plugin instances) and edges
    - Rows and tokens (data flow)
    - Node states (processing records)
    - Routing events, batches, artifacts

    Example:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(config={"source": "data.csv"})
        # ... execute pipeline ...
        recorder.complete_run(run.run_id, status=RunStatus.COMPLETED)
    """

    def __init__(self, db: LandscapeDB, *, payload_store: PayloadStore | None = None) -> None:
        """Initialize recorder with database connection.

        Args:
            db: LandscapeDB instance for audit storage
            payload_store: Optional payload store for retrieving row data
        """
        self._db = db
        self._payload_store = payload_store

        # Database operations helper for reduced boilerplate
        self._ops = DatabaseOps(db)

        # Loader instances for row-to-object conversions
        self._run_loader = RunLoader()
        self._node_loader = NodeLoader()
        self._edge_loader = EdgeLoader()
        self._row_loader = RowLoader()
        self._token_loader = TokenLoader()
        self._token_parent_loader = TokenParentLoader()
        self._call_loader = CallLoader()
        self._operation_loader = OperationLoader()
        self._routing_event_loader = RoutingEventLoader()
        self._batch_loader = BatchLoader()
        self._node_state_loader = NodeStateLoader()
        self._validation_error_loader = ValidationErrorLoader()
        self._transform_error_loader = TransformErrorLoader()
        self._token_outcome_loader = TokenOutcomeLoader()
        self._artifact_loader = ArtifactLoader()
        self._batch_member_loader = BatchMemberLoader()

        # Composed repository for run lifecycle (extracted from mixin in T19)
        self._run_lifecycle = RunLifecycleRepository(db, self._ops, self._run_loader)

        # Composed repository for execution recording (extracted from 3 mixins in T19)
        self._execution = ExecutionRepository(
            db,
            self._ops,
            node_state_loader=self._node_state_loader,
            routing_event_loader=self._routing_event_loader,
            call_loader=self._call_loader,
            operation_loader=self._operation_loader,
            batch_loader=self._batch_loader,
            batch_member_loader=self._batch_member_loader,
            artifact_loader=self._artifact_loader,
            payload_store=payload_store,
        )

    # ── Run lifecycle delegation (RunLifecycleRepository) ──────────────

    def begin_run(
        self,
        config: dict[str, Any],
        canonical_version: str,
        *,
        run_id: str | None = None,
        reproducibility_grade: ReproducibilityGrade | None = None,
        status: RunStatus = RunStatus.RUNNING,
        source_schema_json: str | None = None,
        schema_contract: SchemaContract | None = None,
    ) -> Run:
        """Begin a new pipeline run. Delegates to RunLifecycleRepository."""
        return self._run_lifecycle.begin_run(
            config,
            canonical_version,
            run_id=run_id,
            reproducibility_grade=reproducibility_grade,
            status=status,
            source_schema_json=source_schema_json,
            schema_contract=schema_contract,
        )

    def complete_run(
        self,
        run_id: str,
        status: RunStatus,
        *,
        reproducibility_grade: ReproducibilityGrade | None = None,
    ) -> Run:
        """Complete a pipeline run. Delegates to RunLifecycleRepository."""
        return self._run_lifecycle.complete_run(
            run_id,
            status,
            reproducibility_grade=reproducibility_grade,
        )

    def get_run(self, run_id: str) -> Run | None:
        """Get a run by ID. Delegates to RunLifecycleRepository."""
        return self._run_lifecycle.get_run(run_id)

    def get_source_schema(self, run_id: str) -> str:
        """Get source schema JSON for a run. Delegates to RunLifecycleRepository."""
        return self._run_lifecycle.get_source_schema(run_id)

    def record_source_field_resolution(
        self,
        run_id: str,
        resolution_mapping: dict[str, str],
        normalization_version: str | None,
    ) -> None:
        """Record field resolution mapping. Delegates to RunLifecycleRepository."""
        self._run_lifecycle.record_source_field_resolution(
            run_id,
            resolution_mapping,
            normalization_version,
        )

    def get_source_field_resolution(self, run_id: str) -> dict[str, str] | None:
        """Get source field resolution mapping. Delegates to RunLifecycleRepository."""
        return self._run_lifecycle.get_source_field_resolution(run_id)

    def update_run_status(self, run_id: str, status: RunStatus) -> None:
        """Update run status. Delegates to RunLifecycleRepository."""
        self._run_lifecycle.update_run_status(run_id, status)

    def update_run_contract(self, run_id: str, contract: SchemaContract) -> None:
        """Update run with schema contract. Delegates to RunLifecycleRepository."""
        self._run_lifecycle.update_run_contract(run_id, contract)

    def get_run_contract(self, run_id: str) -> SchemaContract | None:
        """Get schema contract for a run. Delegates to RunLifecycleRepository."""
        return self._run_lifecycle.get_run_contract(run_id)

    def record_secret_resolutions(
        self,
        run_id: str,
        resolutions: list[SecretResolutionInput],
    ) -> None:
        """Record secret resolution events. Delegates to RunLifecycleRepository."""
        self._run_lifecycle.record_secret_resolutions(run_id, resolutions)

    def get_secret_resolutions_for_run(self, run_id: str) -> list[SecretResolution]:
        """Get secret resolutions for a run. Delegates to RunLifecycleRepository."""
        return self._run_lifecycle.get_secret_resolutions_for_run(run_id)

    def list_runs(self, *, status: RunStatus | None = None) -> list[Run]:
        """List all runs. Delegates to RunLifecycleRepository."""
        return self._run_lifecycle.list_runs(status=status)

    def set_export_status(
        self,
        run_id: str,
        status: ExportStatus,
        *,
        error: str | None = None,
        export_format: str | None = None,
        export_sink: str | None = None,
    ) -> None:
        """Set export status for a run. Delegates to RunLifecycleRepository."""
        self._run_lifecycle.set_export_status(
            run_id,
            status,
            error=error,
            export_format=export_format,
            export_sink=export_sink,
        )

    def finalize_run(self, run_id: str, status: RunStatus) -> Run:
        """Finalize a run. Delegates to RunLifecycleRepository."""
        return self._run_lifecycle.finalize_run(run_id, status)

    def compute_reproducibility_grade(self, run_id: str) -> ReproducibilityGrade:
        """Compute reproducibility grade. Delegates to RunLifecycleRepository."""
        return self._run_lifecycle.compute_reproducibility_grade(run_id)

    # ── Execution delegation (ExecutionRepository) ─────────────────────

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
        quarantined: bool = False,
    ) -> NodeStateOpen:
        """Begin recording a node state. Delegates to ExecutionRepository."""
        return self._execution.begin_node_state(
            token_id,
            node_id,
            run_id,
            step_index,
            input_data,
            state_id=state_id,
            attempt=attempt,
            quarantined=quarantined,
        )

    @overload
    def complete_node_state(
        self,
        state_id: str,
        status: Literal[NodeStateStatus.PENDING],
        *,
        output_data: dict[str, Any] | list[dict[str, Any]] | None = None,
        duration_ms: float | None = None,
        error: ExecutionError | TransformErrorReason | CoalesceFailureReason | None = None,
        context_after: NodeStateContext | None = None,
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
        context_after: NodeStateContext | None = None,
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
        context_after: NodeStateContext | None = None,
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
        context_after: NodeStateContext | None = None,
    ) -> NodeStatePending | NodeStateCompleted | NodeStateFailed:
        """Complete a node state. Delegates to ExecutionRepository."""
        return self._execution.complete_node_state(  # type: ignore[call-overload,no-any-return,misc]
            state_id,
            status,
            output_data=output_data,
            duration_ms=duration_ms,
            error=error,
            success_reason=success_reason,
            context_after=context_after,
        )

    def get_node_state(self, state_id: str) -> NodeState | None:
        """Get a node state by ID. Delegates to ExecutionRepository."""
        return self._execution.get_node_state(state_id)

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
        """Record a single routing event. Delegates to ExecutionRepository."""
        return self._execution.record_routing_event(
            state_id,
            edge_id,
            mode,
            reason,
            event_id=event_id,
            routing_group_id=routing_group_id,
            ordinal=ordinal,
            reason_ref=reason_ref,
        )

    def record_routing_events(
        self,
        state_id: str,
        routes: list[RoutingSpec],
        reason: RoutingReason | None = None,
    ) -> list[RoutingEvent]:
        """Record multiple routing events. Delegates to ExecutionRepository."""
        return self._execution.record_routing_events(state_id, routes, reason)

    def allocate_call_index(self, state_id: str) -> int:
        """Allocate next call index for a state_id. Delegates to ExecutionRepository."""
        return self._execution.allocate_call_index(state_id)

    def record_call(
        self,
        state_id: str,
        call_index: int,
        call_type: CallType,
        status: CallStatus,
        request_data: CallPayload,
        response_data: CallPayload | None = None,
        error: CallPayload | None = None,
        latency_ms: float | None = None,
        *,
        request_ref: str | None = None,
        response_ref: str | None = None,
    ) -> Call:
        """Record an external call for a node state. Delegates to ExecutionRepository."""
        return self._execution.record_call(
            state_id,
            call_index,
            call_type,
            status,
            request_data,
            response_data,
            error,
            latency_ms,
            request_ref=request_ref,
            response_ref=response_ref,
        )

    def begin_operation(
        self,
        run_id: str,
        node_id: str,
        operation_type: Literal["source_load", "sink_write"],
        *,
        input_data: dict[str, Any] | None = None,
    ) -> Operation:
        """Begin an operation for source/sink I/O. Delegates to ExecutionRepository."""
        return self._execution.begin_operation(
            run_id,
            node_id,
            operation_type,
            input_data=input_data,
        )

    def complete_operation(
        self,
        operation_id: str,
        status: Literal["completed", "failed", "pending"],
        *,
        output_data: dict[str, Any] | None = None,
        error: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Complete an operation. Delegates to ExecutionRepository."""
        self._execution.complete_operation(
            operation_id,
            status,
            output_data=output_data,
            error=error,
            duration_ms=duration_ms,
        )

    def allocate_operation_call_index(self, operation_id: str) -> int:
        """Allocate next call index for an operation. Delegates to ExecutionRepository."""
        return self._execution.allocate_operation_call_index(operation_id)

    def record_operation_call(
        self,
        operation_id: str,
        call_type: CallType,
        status: CallStatus,
        request_data: CallPayload,
        response_data: CallPayload | None = None,
        error: CallPayload | None = None,
        latency_ms: float | None = None,
        *,
        request_ref: str | None = None,
        response_ref: str | None = None,
        provider: str | None = None,
    ) -> Call:
        """Record an external call for an operation. Delegates to ExecutionRepository."""
        return self._execution.record_operation_call(
            operation_id,
            call_type,
            status,
            request_data,
            response_data,
            error,
            latency_ms,
            request_ref=request_ref,
            response_ref=response_ref,
            provider=provider,
        )

    def get_operation(self, operation_id: str) -> Operation | None:
        """Get an operation by ID. Delegates to ExecutionRepository."""
        return self._execution.get_operation(operation_id)

    def get_operation_calls(self, operation_id: str) -> list[Call]:
        """Get external calls for an operation. Delegates to ExecutionRepository."""
        return self._execution.get_operation_calls(operation_id)

    def get_operations_for_run(self, run_id: str) -> list[Operation]:
        """Get all operations for a run. Delegates to ExecutionRepository."""
        return self._execution.get_operations_for_run(run_id)

    def get_all_operation_calls_for_run(self, run_id: str) -> list[Call]:
        """Get all operation-parented calls for a run. Delegates to ExecutionRepository."""
        return self._execution.get_all_operation_calls_for_run(run_id)

    def find_call_by_request_hash(
        self,
        run_id: str,
        call_type: str,
        request_hash: str,
        *,
        sequence_index: int = 0,
    ) -> Call | None:
        """Find a call by its request hash. Delegates to ExecutionRepository."""
        return self._execution.find_call_by_request_hash(
            run_id,
            call_type,
            request_hash,
            sequence_index=sequence_index,
        )

    def get_call_response_data(self, call_id: str) -> dict[str, Any] | None:
        """Get response data for a call. Delegates to ExecutionRepository."""
        return self._execution.get_call_response_data(call_id)

    def create_batch(
        self,
        run_id: str,
        aggregation_node_id: str,
        *,
        batch_id: str | None = None,
        attempt: int = 0,
    ) -> Batch:
        """Create a new batch for aggregation. Delegates to ExecutionRepository."""
        return self._execution.create_batch(
            run_id,
            aggregation_node_id,
            batch_id=batch_id,
            attempt=attempt,
        )

    def add_batch_member(
        self,
        batch_id: str,
        token_id: str,
        ordinal: int,
    ) -> BatchMember:
        """Add a token to a batch. Delegates to ExecutionRepository."""
        return self._execution.add_batch_member(batch_id, token_id, ordinal)

    def update_batch_status(
        self,
        batch_id: str,
        status: BatchStatus,
        *,
        trigger_type: TriggerType | None = None,
        trigger_reason: str | None = None,
        state_id: str | None = None,
    ) -> None:
        """Update batch status. Delegates to ExecutionRepository."""
        self._execution.update_batch_status(
            batch_id,
            status,
            trigger_type=trigger_type,
            trigger_reason=trigger_reason,
            state_id=state_id,
        )

    def complete_batch(
        self,
        batch_id: str,
        status: BatchStatus,
        *,
        trigger_type: TriggerType | None = None,
        trigger_reason: str | None = None,
        state_id: str | None = None,
    ) -> Batch:
        """Complete a batch. Delegates to ExecutionRepository."""
        return self._execution.complete_batch(
            batch_id,
            status,
            trigger_type=trigger_type,
            trigger_reason=trigger_reason,
            state_id=state_id,
        )

    def get_batch(self, batch_id: str) -> Batch | None:
        """Get a batch by ID. Delegates to ExecutionRepository."""
        return self._execution.get_batch(batch_id)

    def get_batches(
        self,
        run_id: str,
        *,
        status: BatchStatus | None = None,
        node_id: str | None = None,
    ) -> list[Batch]:
        """Get batches for a run. Delegates to ExecutionRepository."""
        return self._execution.get_batches(run_id, status=status, node_id=node_id)

    def get_incomplete_batches(self, run_id: str) -> list[Batch]:
        """Get batches that need recovery. Delegates to ExecutionRepository."""
        return self._execution.get_incomplete_batches(run_id)

    def get_batch_members(self, batch_id: str) -> list[BatchMember]:
        """Get all members of a batch. Delegates to ExecutionRepository."""
        return self._execution.get_batch_members(batch_id)

    def get_all_batch_members_for_run(self, run_id: str) -> list[BatchMember]:
        """Get all batch members for a run. Delegates to ExecutionRepository."""
        return self._execution.get_all_batch_members_for_run(run_id)

    def retry_batch(self, batch_id: str) -> Batch:
        """Retry a failed batch. Delegates to ExecutionRepository."""
        return self._execution.retry_batch(batch_id)

    def register_artifact(
        self,
        run_id: str,
        state_id: str,
        sink_node_id: str,
        artifact_type: str,
        path: str,
        content_hash: str,
        size_bytes: int,
        *,
        artifact_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Artifact:
        """Register an artifact produced by a sink. Delegates to ExecutionRepository."""
        return self._execution.register_artifact(
            run_id,
            state_id,
            sink_node_id,
            artifact_type,
            path,
            content_hash,
            size_bytes,
            artifact_id=artifact_id,
            idempotency_key=idempotency_key,
        )

    def get_artifacts(
        self,
        run_id: str,
        *,
        sink_node_id: str | None = None,
    ) -> list[Artifact]:
        """Get artifacts for a run. Delegates to ExecutionRepository."""
        return self._execution.get_artifacts(run_id, sink_node_id=sink_node_id)
