"""CheckpointManager for creating and loading checkpoints."""

import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import asc, delete, desc, select

from elspeth.contracts import Checkpoint
from elspeth.core.canonical import compute_upstream_topology_hash, stable_hash
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.schema import checkpoints_table

if TYPE_CHECKING:
    from elspeth.core.dag import ExecutionGraph


class IncompatibleCheckpointError(Exception):
    """Raised when attempting to load a checkpoint from an incompatible version."""

    pass


class CheckpointManager:
    """Manages checkpoint creation and retrieval.

    Checkpoints capture run progress at row boundaries, enabling
    resume after crash. Each checkpoint records:
    - Which token was being processed
    - Which node it was at
    - A monotonic sequence number for ordering
    - Optional aggregation state for stateful plugins
    """

    def __init__(self, db: LandscapeDB) -> None:
        """Initialize with Landscape database.

        Args:
            db: LandscapeDB instance for storage
        """
        self._db = db

    def create_checkpoint(
        self,
        run_id: str,
        token_id: str,
        node_id: str,
        sequence_number: int,
        graph: "ExecutionGraph",
        aggregation_state: dict[str, Any] | None = None,
    ) -> Checkpoint:
        """Create a checkpoint at current progress point.

        Args:
            run_id: The run being checkpointed
            token_id: Current token being processed
            node_id: Current node in the pipeline
            sequence_number: Monotonic progress marker
            graph: Execution graph for topology validation (REQUIRED)
            aggregation_state: Optional serializable aggregation buffers

        Returns:
            The created Checkpoint

        Raises:
            ValueError: If graph is None or node_id not in graph
        """
        # Validate parameters (Bug #9 - early validation)
        if graph is None:
            raise ValueError("graph parameter is required for checkpoint creation")
        if not graph.has_node(node_id):
            raise ValueError(f"node_id '{node_id}' does not exist in graph")

        # All checkpoint data generation happens INSIDE transaction for atomicity
        with self._db.engine.begin() as conn:
            # Generate IDs and timestamps within transaction boundary
            checkpoint_id = f"cp-{uuid.uuid4().hex[:12]}"
            created_at = datetime.now(UTC)

            # Prepare aggregation state JSON
            agg_json = json.dumps(aggregation_state) if aggregation_state is not None else None

            # Compute topology hashes INSIDE transaction (Bug #1 fix)
            # This ensures hash matches graph state at exact moment of checkpoint creation
            upstream_topology_hash = compute_upstream_topology_hash(graph, node_id)
            node_info = graph.get_node_info(node_id)
            checkpoint_node_config_hash = stable_hash(node_info.config)

            conn.execute(
                checkpoints_table.insert().values(
                    checkpoint_id=checkpoint_id,
                    run_id=run_id,
                    token_id=token_id,
                    node_id=node_id,
                    sequence_number=sequence_number,
                    aggregation_state_json=agg_json,
                    created_at=created_at,
                    upstream_topology_hash=upstream_topology_hash,
                    checkpoint_node_config_hash=checkpoint_node_config_hash,
                )
            )
            # begin() auto-commits on clean exit, auto-rollbacks on exception

        return Checkpoint(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            token_id=token_id,
            node_id=node_id,
            sequence_number=sequence_number,
            created_at=created_at,
            upstream_topology_hash=upstream_topology_hash,
            checkpoint_node_config_hash=checkpoint_node_config_hash,
            aggregation_state_json=agg_json,
        )

    def get_latest_checkpoint(self, run_id: str) -> Checkpoint | None:
        """Get the most recent checkpoint for a run.

        Args:
            run_id: The run to get checkpoint for

        Returns:
            Latest Checkpoint or None if no checkpoints exist

        Raises:
            IncompatibleCheckpointError: If checkpoint predates deterministic node IDs
        """
        with self._db.engine.connect() as conn:
            result = conn.execute(
                select(checkpoints_table)
                .where(checkpoints_table.c.run_id == run_id)
                .order_by(desc(checkpoints_table.c.sequence_number))
                .limit(1)
            ).fetchone()

        if result is None:
            return None

        checkpoint = Checkpoint(
            checkpoint_id=result.checkpoint_id,
            run_id=result.run_id,
            token_id=result.token_id,
            node_id=result.node_id,
            sequence_number=result.sequence_number,
            created_at=result.created_at,
            upstream_topology_hash=result.upstream_topology_hash,
            checkpoint_node_config_hash=result.checkpoint_node_config_hash,
            aggregation_state_json=result.aggregation_state_json,
        )

        # Validate checkpoint compatibility before returning
        self._validate_checkpoint_compatibility(checkpoint)

        return checkpoint

    def get_checkpoints(self, run_id: str) -> list[Checkpoint]:
        """Get all checkpoints for a run, ordered by sequence.

        Args:
            run_id: The run to get checkpoints for

        Returns:
            List of Checkpoints ordered by sequence_number
        """
        with self._db.engine.connect() as conn:
            results = conn.execute(
                select(checkpoints_table).where(checkpoints_table.c.run_id == run_id).order_by(asc(checkpoints_table.c.sequence_number))
            ).fetchall()

        return [
            Checkpoint(
                checkpoint_id=r.checkpoint_id,
                run_id=r.run_id,
                token_id=r.token_id,
                node_id=r.node_id,
                sequence_number=r.sequence_number,
                created_at=r.created_at,
                upstream_topology_hash=r.upstream_topology_hash,
                checkpoint_node_config_hash=r.checkpoint_node_config_hash,
                aggregation_state_json=r.aggregation_state_json,
            )
            for r in results
        ]

    def delete_checkpoints(self, run_id: str) -> int:
        """Delete all checkpoints for a completed run.

        Called after successful run completion to clean up.

        Args:
            run_id: The run to clean up

        Returns:
            Number of checkpoints deleted
        """
        with self._db.engine.begin() as conn:
            result = conn.execute(delete(checkpoints_table).where(checkpoints_table.c.run_id == run_id))
            # begin() auto-commits on clean exit, auto-rollbacks on exception
            return result.rowcount

    def _validate_checkpoint_compatibility(self, checkpoint: Checkpoint) -> None:
        """Verify checkpoint was created with compatible node ID generation.

        CRITICAL: Node IDs changed from random UUID to deterministic hash-based
        in 2026-01-24. Old checkpoints cannot be resumed because node IDs will
        not match between checkpoint and current graph.

        Args:
            checkpoint: Checkpoint to validate

        Raises:
            IncompatibleCheckpointError: If checkpoint predates deterministic node IDs
        """
        # Check if checkpoint has deterministic node IDs
        # Old checkpoints: created_at before 2026-01-24
        # New checkpoints: created_at on or after 2026-01-24

        # Simple heuristic: if created_at before 2026-01-24, warn about incompatibility
        cutoff_date = datetime(2026, 1, 24, tzinfo=UTC)

        # Handle timezone-naive datetimes from SQLite (assume UTC if naive)
        checkpoint_created_at = checkpoint.created_at
        if checkpoint_created_at.tzinfo is None:
            checkpoint_created_at = checkpoint_created_at.replace(tzinfo=UTC)

        if checkpoint_created_at < cutoff_date:
            raise IncompatibleCheckpointError(
                f"Checkpoint '{checkpoint.checkpoint_id}' created before deterministic node IDs "
                f"(created: {checkpoint_created_at.isoformat()}, cutoff: {cutoff_date.isoformat()}). "
                "Resume not supported across this upgrade. "
                "Please restart pipeline from beginning."
            )
