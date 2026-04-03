"""LandscapeRecorder: pure facade for audit trail recording.

Delegates to 4 composed domain repositories:
- RunLifecycleRepository: run lifecycle, graph registration, export
- ExecutionRepository: node states, external calls, batch management
- DataFlowRepository: rows, tokens, errors
- QueryRepository: read-only queries, bulk retrieval, lineage

All public methods delegate directly to the appropriate repository.
No logic in this file.

Repository split rationale (domain cohesion, not CQRS):
    The 4 repositories are split by pipeline-phase domain, not by
    read/write separation. Pure-query methods like get_artifacts() and
    get_batches() live in ExecutionRepository (not QueryRepository)
    because they belong to the execution domain. QueryRepository holds
    only cross-cutting read methods used by external consumers (MCP,
    exporter, TUI).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Literal, overload

from elspeth.contracts import CallType, Determinism, RunStatus
from elspeth.contracts.audit import TokenRef
from elspeth.contracts.errors import FrameworkBugError
from elspeth.core.dependency_config import PreflightResult

if TYPE_CHECKING:
    from elspeth.contracts import (
        Artifact,
        Batch,
        BatchMember,
        BatchStatus,
        Call,
        CallStatus,
        CoalesceFailureReason,
        Edge,
        ExportStatus,
        Node,
        NodeState,
        NodeStateCompleted,
        NodeStateFailed,
        NodeStateOpen,
        NodeStatePending,
        NodeStateStatus,
        NodeType,
        Operation,
        ReproducibilityGrade,
        RoutingEvent,
        RoutingMode,
        RoutingReason,
        RoutingSpec,
        Row,
        RowLineage,
        RowOutcome,
        Run,
        SecretResolution,
        SecretResolutionInput,
        Token,
        TokenOutcome,
        TokenParent,
        TransformErrorRecord,
        TriggerType,
        ValidationErrorRecord,
    )
    from elspeth.contracts.call_data import CallPayload
    from elspeth.contracts.errors import ContractViolation, ExecutionError, TransformErrorReason, TransformSuccessReason
    from elspeth.contracts.node_state_context import NodeStateContext
    from elspeth.contracts.payload_store import PayloadStore
    from elspeth.contracts.schema import SchemaConfig
    from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
    from elspeth.core.landscape.row_data import CallDataResult, RowDataResult

from elspeth.core.landscape._database_ops import DatabaseOps
from elspeth.core.landscape.data_flow_repository import DataFlowRepository
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
from elspeth.core.landscape.query_repository import QueryRepository
from elspeth.core.landscape.run_lifecycle_repository import RunLifecycleRepository


class LandscapeRecorder:
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

        # Composed repository for run lifecycle
        self._run_lifecycle = RunLifecycleRepository(db, self._ops, self._run_loader)

        # Composed repository for execution recording
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

        # Composed repository for data flow recording
        self._data_flow = DataFlowRepository(
            db,
            self._ops,
            token_outcome_loader=self._token_outcome_loader,
            node_loader=self._node_loader,
            edge_loader=self._edge_loader,
            validation_error_loader=self._validation_error_loader,
            transform_error_loader=self._transform_error_loader,
            payload_store=payload_store,
        )

        # Composed repository for read-only queries
        self._query = QueryRepository(
            self._ops,
            row_loader=self._row_loader,
            token_loader=self._token_loader,
            token_parent_loader=self._token_parent_loader,
            node_state_loader=self._node_state_loader,
            routing_event_loader=self._routing_event_loader,
            call_loader=self._call_loader,
            token_outcome_loader=self._token_outcome_loader,
            payload_store=payload_store,
        )

    # ── Run lifecycle delegation (RunLifecycleRepository) ──────────────

    def begin_run(
        self,
        config: Mapping[str, Any],
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
        resolution_mapping: Mapping[str, str],
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

    def record_preflight_results(
        self,
        run_id: str,
        preflight: PreflightResult,
    ) -> None:
        """Record pre-flight dependency and gate results. Delegates to RunLifecycleRepository."""
        self._run_lifecycle.record_preflight_results(run_id, preflight)

    def record_readiness_check(
        self,
        run_id: str,
        *,
        name: str,
        collection: str,
        reachable: bool,
        count: int | None,
        message: str,
    ) -> None:
        """Record a readiness check result. Delegates to RunLifecycleRepository."""
        self._run_lifecycle.record_readiness_check(
            run_id,
            name=name,
            collection=collection,
            reachable=reachable,
            count=count,
            message=message,
        )

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
        input_data: Mapping[str, object],
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
        output_data: Mapping[str, object] | list[Mapping[str, object]] | None = None,
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
        output_data: Mapping[str, object] | list[Mapping[str, object]] | None = None,
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
        output_data: Mapping[str, object] | list[Mapping[str, object]] | None = None,
        duration_ms: float | None = None,
        error: ExecutionError | TransformErrorReason | CoalesceFailureReason | None = None,
        context_after: NodeStateContext | None = None,
    ) -> NodeStateFailed: ...

    def complete_node_state(
        self,
        state_id: str,
        status: NodeStateStatus,
        *,
        output_data: Mapping[str, object] | list[Mapping[str, object]] | None = None,
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

    def store_payload(self, content: bytes, *, purpose: str) -> str:
        """Store a transform-produced artifact in the payload store.

        For blobs that have no corresponding external call record — e.g.,
        post-extraction processed content. The purpose label is a code-level
        documentation convention — it is not persisted or emitted to telemetry.
        It exists solely to force callers to name what they're storing at the
        call site, making the intent visible in code review.

        Args:
            content: Raw bytes to store.
            purpose: Semantic label (e.g., "processed_content", "extracted_markdown").
                Not persisted — call-site documentation only.

        Returns:
            SHA-256 hex digest of stored content.

        Raises:
            FrameworkBugError: If recorder was constructed without a payload_store.
        """
        if self._payload_store is None:
            raise FrameworkBugError(
                f"store_payload(purpose={purpose!r}) called but recorder has no "
                f"payload_store. Orchestrator must configure LandscapeRecorder with "
                f"a payload_store when transforms that produce processed content "
                f"blobs are in the pipeline."
            )
        return self._payload_store.store(content)

    def begin_operation(
        self,
        run_id: str,
        node_id: str,
        operation_type: Literal["source_load", "sink_write"],
        *,
        input_data: Mapping[str, object] | None = None,
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
        output_data: Mapping[str, object] | None = None,
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
        call_type: CallType,
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

    def get_call_response_data(self, call_id: str) -> CallDataResult:
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

    # ── Data flow delegation (DataFlowRepository) ────────────────────────

    # Token recording

    def create_row(
        self,
        run_id: str,
        source_node_id: str,
        row_index: int,
        data: Mapping[str, object],
        *,
        row_id: str | None = None,
        quarantined: bool = False,
    ) -> Row:
        """Create a source row record. Delegates to DataFlowRepository."""
        return self._data_flow.create_row(
            run_id,
            source_node_id,
            row_index,
            data,
            row_id=row_id,
            quarantined=quarantined,
        )

    def create_token(
        self,
        row_id: str,
        *,
        token_id: str | None = None,
        branch_name: str | None = None,
        fork_group_id: str | None = None,
        join_group_id: str | None = None,
    ) -> Token:
        """Create a token. Delegates to DataFlowRepository."""
        return self._data_flow.create_token(
            row_id,
            token_id=token_id,
            branch_name=branch_name,
            fork_group_id=fork_group_id,
            join_group_id=join_group_id,
        )

    def fork_token(
        self,
        parent_ref: TokenRef,
        row_id: str,
        branches: list[str],
        *,
        step_in_pipeline: int | None = None,
    ) -> tuple[list[Token], str]:
        """Fork a token to multiple branches. Delegates to DataFlowRepository."""
        return self._data_flow.fork_token(
            parent_ref,
            row_id,
            branches,
            step_in_pipeline=step_in_pipeline,
        )

    def coalesce_tokens(
        self,
        parent_token_ids: list[str],
        row_id: str,
        *,
        step_in_pipeline: int | None = None,
    ) -> Token:
        """Coalesce multiple tokens. Delegates to DataFlowRepository."""
        return self._data_flow.coalesce_tokens(
            parent_token_ids,
            row_id,
            step_in_pipeline=step_in_pipeline,
        )

    def expand_token(
        self,
        parent_ref: TokenRef,
        row_id: str,
        count: int,
        *,
        step_in_pipeline: int | None = None,
        record_parent_outcome: bool = True,
    ) -> tuple[list[Token], str]:
        """Expand a token into multiple children. Delegates to DataFlowRepository."""
        return self._data_flow.expand_token(
            parent_ref,
            row_id,
            count,
            step_in_pipeline=step_in_pipeline,
            record_parent_outcome=record_parent_outcome,
        )

    def record_token_outcome(
        self,
        ref: TokenRef,
        outcome: RowOutcome,
        *,
        sink_name: str | None = None,
        batch_id: str | None = None,
        fork_group_id: str | None = None,
        join_group_id: str | None = None,
        expand_group_id: str | None = None,
        error_hash: str | None = None,
        context: Mapping[str, object] | None = None,
    ) -> str:
        """Record a token outcome. Delegates to DataFlowRepository."""
        return self._data_flow.record_token_outcome(
            ref,
            outcome,
            sink_name=sink_name,
            batch_id=batch_id,
            fork_group_id=fork_group_id,
            join_group_id=join_group_id,
            expand_group_id=expand_group_id,
            error_hash=error_hash,
            context=context,
        )

    def get_token_outcome(self, token_id: str) -> TokenOutcome | None:
        """Get terminal outcome for a token. Delegates to DataFlowRepository."""
        return self._data_flow.get_token_outcome(token_id)

    def get_token_outcomes_for_row(self, run_id: str, row_id: str) -> list[TokenOutcome]:
        """Get all token outcomes for a row. Delegates to DataFlowRepository."""
        return self._data_flow.get_token_outcomes_for_row(run_id, row_id)

    # Graph recording

    def register_node(
        self,
        run_id: str,
        plugin_name: str,
        node_type: NodeType,
        plugin_version: str,
        config: Mapping[str, object],
        *,
        node_id: str | None = None,
        sequence: int | None = None,
        schema_hash: str | None = None,
        determinism: Determinism = Determinism.DETERMINISTIC,
        schema_config: SchemaConfig,
        input_contract: SchemaContract | None = None,
        output_contract: SchemaContract | None = None,
    ) -> Node:
        """Register a plugin node. Delegates to DataFlowRepository."""
        return self._data_flow.register_node(
            run_id,
            plugin_name,
            node_type,
            plugin_version,
            config,
            node_id=node_id,
            sequence=sequence,
            schema_hash=schema_hash,
            determinism=determinism,
            schema_config=schema_config,
            input_contract=input_contract,
            output_contract=output_contract,
        )

    def register_edge(
        self,
        run_id: str,
        from_node_id: str,
        to_node_id: str,
        label: str,
        mode: RoutingMode,
        *,
        edge_id: str | None = None,
    ) -> Edge:
        """Register an edge. Delegates to DataFlowRepository."""
        return self._data_flow.register_edge(
            run_id,
            from_node_id,
            to_node_id,
            label,
            mode,
            edge_id=edge_id,
        )

    def get_node(self, node_id: str, run_id: str) -> Node | None:
        """Get a node by composite PK. Delegates to DataFlowRepository."""
        return self._data_flow.get_node(node_id, run_id)

    def get_nodes(self, run_id: str) -> list[Node]:
        """Get all nodes for a run. Delegates to DataFlowRepository."""
        return self._data_flow.get_nodes(run_id)

    def get_node_contracts(
        self, run_id: str, node_id: str, *, allow_missing: bool = False
    ) -> tuple[SchemaContract | None, SchemaContract | None]:
        """Get node contracts. Delegates to DataFlowRepository."""
        return self._data_flow.get_node_contracts(run_id, node_id, allow_missing=allow_missing)

    def get_edges(self, run_id: str) -> list[Edge]:
        """Get all edges for a run. Delegates to DataFlowRepository."""
        return self._data_flow.get_edges(run_id)

    def get_edge(self, edge_id: str) -> Edge:
        """Get an edge by ID. Delegates to DataFlowRepository."""
        return self._data_flow.get_edge(edge_id)

    def get_edge_map(self, run_id: str) -> dict[tuple[str, str], str]:
        """Get edge mapping for a run. Delegates to DataFlowRepository."""
        return self._data_flow.get_edge_map(run_id)

    def update_node_output_contract(
        self,
        run_id: str,
        node_id: str,
        contract: SchemaContract,
    ) -> None:
        """Update node output contract. Delegates to DataFlowRepository."""
        self._data_flow.update_node_output_contract(run_id, node_id, contract)

    # Error recording

    def record_validation_error(
        self,
        run_id: str,
        node_id: str | None,
        row_data: Any,
        error: str,
        schema_mode: str,
        destination: str,
        *,
        contract_violation: ContractViolation | None = None,
    ) -> str:
        """Record a validation error. Delegates to DataFlowRepository."""
        return self._data_flow.record_validation_error(
            run_id,
            node_id,
            row_data,
            error,
            schema_mode,
            destination,
            contract_violation=contract_violation,
        )

    def record_transform_error(
        self,
        ref: TokenRef,
        transform_id: str,
        row_data: Mapping[str, object] | PipelineRow,
        error_details: TransformErrorReason,
        destination: str,
    ) -> str:
        """Record a transform error. Delegates to DataFlowRepository."""
        return self._data_flow.record_transform_error(
            ref,
            transform_id,
            row_data,
            error_details,
            destination,
        )

    def get_validation_errors_for_row(self, run_id: str, row_hash: str) -> list[ValidationErrorRecord]:
        """Get validation errors for a row. Delegates to DataFlowRepository."""
        return self._data_flow.get_validation_errors_for_row(run_id, row_hash)

    def get_validation_errors_for_run(self, run_id: str) -> list[ValidationErrorRecord]:
        """Get all validation errors for a run. Delegates to DataFlowRepository."""
        return self._data_flow.get_validation_errors_for_run(run_id)

    def get_transform_errors_for_token(self, token_id: str) -> list[TransformErrorRecord]:
        """Get transform errors for a token. Delegates to DataFlowRepository."""
        return self._data_flow.get_transform_errors_for_token(token_id)

    def get_transform_errors_for_run(self, run_id: str) -> list[TransformErrorRecord]:
        """Get all transform errors for a run. Delegates to DataFlowRepository."""
        return self._data_flow.get_transform_errors_for_run(run_id)

    # ── Query delegation (QueryRepository) ─────────────────────────────

    def get_rows(self, run_id: str) -> list[Row]:
        """Get all rows for a run. Delegates to QueryRepository."""
        return self._query.get_rows(run_id)

    def get_tokens(self, row_id: str) -> list[Token]:
        """Get all tokens for a row. Delegates to QueryRepository."""
        return self._query.get_tokens(row_id)

    def get_node_states_for_token(self, token_id: str) -> list[NodeState]:
        """Get all node states for a token. Delegates to QueryRepository."""
        return self._query.get_node_states_for_token(token_id)

    def get_row(self, row_id: str) -> Row | None:
        """Get a row by ID. Delegates to QueryRepository."""
        return self._query.get_row(row_id)

    def get_row_data(self, row_id: str) -> RowDataResult:
        """Get payload data for a row. Delegates to QueryRepository."""
        return self._query.get_row_data(row_id)

    def get_token(self, token_id: str) -> Token | None:
        """Get a token by ID. Delegates to QueryRepository."""
        return self._query.get_token(token_id)

    def get_token_parents(self, token_id: str) -> list[TokenParent]:
        """Get parent relationships for a token. Delegates to QueryRepository."""
        return self._query.get_token_parents(token_id)

    def get_routing_events(self, state_id: str) -> list[RoutingEvent]:
        """Get routing events for a node state. Delegates to QueryRepository."""
        return self._query.get_routing_events(state_id)

    def get_calls(self, state_id: str) -> list[Call]:
        """Get external calls for a node state. Delegates to QueryRepository."""
        return self._query.get_calls(state_id)

    def get_routing_events_for_states(self, state_ids: list[str]) -> list[RoutingEvent]:
        """Get routing events for multiple states. Delegates to QueryRepository."""
        return self._query.get_routing_events_for_states(state_ids)

    def get_calls_for_states(self, state_ids: list[str]) -> list[Call]:
        """Get external calls for multiple states. Delegates to QueryRepository."""
        return self._query.get_calls_for_states(state_ids)

    def get_all_tokens_for_run(self, run_id: str) -> list[Token]:
        """Get all tokens for a run. Delegates to QueryRepository."""
        return self._query.get_all_tokens_for_run(run_id)

    def get_all_node_states_for_run(self, run_id: str) -> list[NodeState]:
        """Get all node states for a run. Delegates to QueryRepository."""
        return self._query.get_all_node_states_for_run(run_id)

    def get_all_routing_events_for_run(self, run_id: str) -> list[RoutingEvent]:
        """Get all routing events for a run. Delegates to QueryRepository."""
        return self._query.get_all_routing_events_for_run(run_id)

    def get_all_calls_for_run(self, run_id: str) -> list[Call]:
        """Get all state-parented calls for a run. Delegates to QueryRepository."""
        return self._query.get_all_calls_for_run(run_id)

    def get_all_token_parents_for_run(self, run_id: str) -> list[TokenParent]:
        """Get all token parent relationships for a run. Delegates to QueryRepository."""
        return self._query.get_all_token_parents_for_run(run_id)

    def get_all_token_outcomes_for_run(self, run_id: str) -> list[TokenOutcome]:
        """Get all token outcomes for a run. Delegates to QueryRepository."""
        return self._query.get_all_token_outcomes_for_run(run_id)

    def explain_row(self, run_id: str, row_id: str) -> RowLineage | None:
        """Get lineage for a row. Delegates to QueryRepository."""
        return self._query.explain_row(run_id, row_id)
