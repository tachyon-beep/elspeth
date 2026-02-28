# src/elspeth/core/landscape/recorder.py
"""LandscapeRecorder: High-level API for audit recording.

This is the main interface for recording audit trail entries during
pipeline execution. It wraps the low-level database operations.

Implementation is split across mixins for maintainability:
- run_lifecycle_repository.py: Run lifecycle (begin, complete, finalize, secrets, contracts) [composed repository]
- _graph_recording.py: Node and edge registration/queries
- _node_state_recording.py: Node state recording and routing events
- _token_recording.py: Row/token creation, fork/coalesce/expand, outcomes
- _call_recording.py: External call recording, operations, replay lookup
- _batch_recording.py: Batch management and artifact registration
- _error_recording.py: Validation and transform error recording
- _query_methods.py: Read-only entity queries, bulk retrieval, explain
"""

from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING, Any

from elspeth.contracts import RunStatus

if TYPE_CHECKING:
    from elspeth.contracts import ExportStatus, Run, SecretResolution
    from elspeth.contracts.payload_store import PayloadStore
    from elspeth.contracts.schema_contract import SchemaContract
    from elspeth.core.landscape.reproducibility import ReproducibilityGrade

from elspeth.core.landscape._batch_recording import BatchRecordingMixin
from elspeth.core.landscape._call_recording import CallRecordingMixin
from elspeth.core.landscape._database_ops import DatabaseOps
from elspeth.core.landscape._error_recording import ErrorRecordingMixin
from elspeth.core.landscape._graph_recording import GraphRecordingMixin
from elspeth.core.landscape._node_state_recording import NodeStateRecordingMixin
from elspeth.core.landscape._query_methods import QueryMethodsMixin
from elspeth.core.landscape._token_recording import TokenRecordingMixin
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.model_loaders import (
    ArtifactLoader,
    BatchLoader,
    BatchMemberLoader,
    CallLoader,
    EdgeLoader,
    NodeLoader,
    NodeStateLoader,
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
    NodeStateRecordingMixin,
    TokenRecordingMixin,
    CallRecordingMixin,
    BatchRecordingMixin,
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

        # Per-state_id call index allocation
        # Ensures UNIQUE(state_id, call_index) across all client types and retries
        self._call_indices: dict[str, int] = {}  # state_id → next_index
        self._call_index_lock: Lock = Lock()

        # Per-operation_id call index allocation (parallel to state call indices)
        # Operations (source/sink I/O) need their own call numbering
        self._operation_call_indices: dict[str, int] = {}  # operation_id → next_index

        # Database operations helper for reduced boilerplate
        self._ops = DatabaseOps(db)

        # Loader instances for row-to-object conversions
        self._run_loader = RunLoader()

        # Composed repositories (replacing mixins)
        self._run_lifecycle = RunLifecycleRepository(db, self._ops, self._run_loader)
        self._node_loader = NodeLoader()
        self._edge_loader = EdgeLoader()
        self._row_loader = RowLoader()
        self._token_loader = TokenLoader()
        self._token_parent_loader = TokenParentLoader()
        self._call_loader = CallLoader()
        self._routing_event_loader = RoutingEventLoader()
        self._batch_loader = BatchLoader()
        self._node_state_loader = NodeStateLoader()
        self._validation_error_loader = ValidationErrorLoader()
        self._transform_error_loader = TransformErrorLoader()
        self._token_outcome_loader = TokenOutcomeLoader()
        self._artifact_loader = ArtifactLoader()
        self._batch_member_loader = BatchMemberLoader()

    # ── Run lifecycle delegation (RunLifecycleRepository) ──────────────

    def begin_run(
        self,
        config: dict[str, Any],
        canonical_version: str,
        *,
        run_id: str | None = None,
        reproducibility_grade: str | None = None,
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
        reproducibility_grade: str | None = None,
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
        resolutions: list[dict[str, Any]],
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
