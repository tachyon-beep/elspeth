# src/elspeth/core/landscape/_batch_recording.py
"""Batch and artifact recording methods for LandscapeRecorder."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from elspeth.contracts import (
    Artifact,
    Batch,
    BatchMember,
    BatchStatus,
    TriggerType,
)
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.core.landscape._helpers import generate_id, now
from elspeth.core.landscape.schema import (
    artifacts_table,
    batch_members_table,
    batches_table,
)

if TYPE_CHECKING:
    from elspeth.core.landscape._database_ops import DatabaseOps
    from elspeth.core.landscape.database import LandscapeDB
    from elspeth.core.landscape.repositories import (
        ArtifactRepository,
        BatchMemberRepository,
        BatchRepository,
    )


class BatchRecordingMixin:
    """Batch and artifact recording methods. Mixed into LandscapeRecorder."""

    # Shared state annotations (set by LandscapeRecorder.__init__)
    _db: LandscapeDB
    _ops: DatabaseOps
    _batch_repo: BatchRepository
    _batch_member_repo: BatchMemberRepository
    _artifact_repo: ArtifactRepository

    def create_batch(
        self,
        run_id: str,
        aggregation_node_id: str,
        *,
        batch_id: str | None = None,
        attempt: int = 0,
    ) -> Batch:
        """Create a new batch for aggregation.

        Args:
            run_id: Run this batch belongs to
            aggregation_node_id: Aggregation node collecting tokens
            batch_id: Optional batch ID (generated if not provided)
            attempt: Attempt number (0 for first attempt)

        Returns:
            Batch model with status="draft"
        """
        batch_id = batch_id or generate_id()
        timestamp = now()

        batch = Batch(
            batch_id=batch_id,
            run_id=run_id,
            aggregation_node_id=aggregation_node_id,
            attempt=attempt,
            status=BatchStatus.DRAFT,  # Strict: enum type
            created_at=timestamp,
        )

        self._ops.execute_insert(
            batches_table.insert().values(
                batch_id=batch.batch_id,
                run_id=batch.run_id,
                aggregation_node_id=batch.aggregation_node_id,
                attempt=batch.attempt,
                status=batch.status.value,  # Store string in DB
                created_at=batch.created_at,
            )
        )

        return batch

    def add_batch_member(
        self,
        batch_id: str,
        token_id: str,
        ordinal: int,
    ) -> BatchMember:
        """Add a token to a batch.

        Args:
            batch_id: Batch to add to
            token_id: Token to add
            ordinal: Order in batch

        Returns:
            BatchMember model
        """
        member = BatchMember(
            batch_id=batch_id,
            token_id=token_id,
            ordinal=ordinal,
        )

        self._ops.execute_insert(
            batch_members_table.insert().values(
                batch_id=member.batch_id,
                token_id=member.token_id,
                ordinal=member.ordinal,
            )
        )

        return member

    def update_batch_status(
        self,
        batch_id: str,
        status: BatchStatus,
        *,
        trigger_type: TriggerType | None = None,
        trigger_reason: str | None = None,
        state_id: str | None = None,
    ) -> None:
        """Update batch status.

        Args:
            batch_id: Batch to update
            status: New BatchStatus
            trigger_type: TriggerType enum value
            trigger_reason: Human-readable reason for the trigger
            state_id: Node state for the flush operation
        """
        updates: dict[str, Any] = {"status": status.value}

        if trigger_type is not None:
            updates["trigger_type"] = trigger_type.value
        if trigger_reason is not None:
            updates["trigger_reason"] = trigger_reason
        if state_id is not None:
            updates["aggregation_state_id"] = state_id
        if status in (BatchStatus.COMPLETED, BatchStatus.FAILED):
            updates["completed_at"] = now()

        self._ops.execute_update(batches_table.update().where(batches_table.c.batch_id == batch_id).values(**updates))

    def complete_batch(
        self,
        batch_id: str,
        status: BatchStatus,
        *,
        trigger_type: TriggerType | None = None,
        trigger_reason: str | None = None,
        state_id: str | None = None,
    ) -> Batch:
        """Complete a batch.

        Args:
            batch_id: Batch to complete
            status: Final BatchStatus (COMPLETED or FAILED)
            trigger_type: TriggerType enum value
            trigger_reason: Human-readable reason for the trigger
            state_id: Optional node state for the aggregation

        Returns:
            Updated Batch model
        """
        timestamp = now()

        self._ops.execute_update(
            batches_table.update()
            .where(batches_table.c.batch_id == batch_id)
            .values(
                status=status.value,
                trigger_type=trigger_type.value if trigger_type is not None else None,
                trigger_reason=trigger_reason,
                aggregation_state_id=state_id,
                completed_at=timestamp,
            )
        )

        result = self.get_batch(batch_id)
        if result is None:
            raise AuditIntegrityError(f"Batch {batch_id} not found after update - database corruption or transaction failure")
        return result

    def get_batch(self, batch_id: str) -> Batch | None:
        """Get a batch by ID.

        Args:
            batch_id: Batch ID to retrieve

        Returns:
            Batch model or None
        """
        query = select(batches_table).where(batches_table.c.batch_id == batch_id)
        row = self._ops.execute_fetchone(query)
        if row is None:
            return None
        return self._batch_repo.load(row)

    def get_batches(
        self,
        run_id: str,
        *,
        status: BatchStatus | None = None,
        node_id: str | None = None,
    ) -> list[Batch]:
        """Get batches for a run.

        Args:
            run_id: Run ID
            status: Optional BatchStatus filter
            node_id: Optional aggregation node filter

        Returns:
            List of Batch models, ordered by created_at then batch_id
            for deterministic export signatures.
        """
        query = select(batches_table).where(batches_table.c.run_id == run_id)

        if status:
            query = query.where(batches_table.c.status == status.value)
        if node_id:
            query = query.where(batches_table.c.aggregation_node_id == node_id)

        # Order for deterministic export signatures
        query = query.order_by(batches_table.c.created_at, batches_table.c.batch_id)
        rows = self._ops.execute_fetchall(query)
        return [self._batch_repo.load(row) for row in rows]

    def get_incomplete_batches(self, run_id: str) -> list[Batch]:
        """Get batches that need recovery (draft, executing, or failed).

        Used during crash recovery to find batches that were:
        - draft: Still collecting rows when crash occurred
        - executing: Mid-flush when crash occurred
        - failed: Flush failed and needs retry

        Args:
            run_id: The run to query

        Returns:
            List of Batch objects with status in (draft, executing, failed),
            ordered by created_at ascending (oldest first for deterministic recovery)
        """
        query = (
            select(batches_table)
            .where(batches_table.c.run_id == run_id)
            .where(batches_table.c.status.in_([BatchStatus.DRAFT.value, BatchStatus.EXECUTING.value, BatchStatus.FAILED.value]))
            .order_by(batches_table.c.created_at.asc())
        )
        result = self._ops.execute_fetchall(query)
        return [self._batch_repo.load(row) for row in result]

    def get_batch_members(self, batch_id: str) -> list[BatchMember]:
        """Get all members of a batch.

        Args:
            batch_id: Batch ID

        Returns:
            List of BatchMember models (ordered by ordinal)
        """
        query = select(batch_members_table).where(batch_members_table.c.batch_id == batch_id).order_by(batch_members_table.c.ordinal)
        rows = self._ops.execute_fetchall(query)
        return [self._batch_member_repo.load(row) for row in rows]

    def get_all_batch_members_for_run(self, run_id: str) -> list[BatchMember]:
        """Get all batch members for a run (batch query).

        Fetches all members for all batches in a run in one query,
        replacing per-batch get_batch_members() loops in the exporter.

        Args:
            run_id: Run ID

        Returns:
            List of BatchMember models, ordered by batch_id then ordinal
        """
        query = (
            select(batch_members_table)
            .join(batches_table, batch_members_table.c.batch_id == batches_table.c.batch_id)
            .where(batches_table.c.run_id == run_id)
            .order_by(batch_members_table.c.batch_id, batch_members_table.c.ordinal)
        )
        rows = self._ops.execute_fetchall(query)
        return [self._batch_member_repo.load(row) for row in rows]

    def retry_batch(self, batch_id: str) -> Batch:
        """Create a new batch attempt from a failed batch.

        Copies batch metadata and members to a new batch with
        incremented attempt counter and draft status.

        Args:
            batch_id: The failed batch to retry

        Returns:
            New Batch with attempt = original.attempt + 1

        Raises:
            ValueError: If original batch not found or not in failed status
        """
        original = self.get_batch(batch_id)
        if original is None:
            raise ValueError(f"Batch not found: {batch_id}")
        if original.status != BatchStatus.FAILED:
            raise ValueError(f"Can only retry failed batches, got status: {original.status}")

        # Create new batch with incremented attempt
        new_batch = self.create_batch(
            run_id=original.run_id,
            aggregation_node_id=original.aggregation_node_id,
            attempt=original.attempt + 1,
        )

        # Copy members to new batch
        original_members = self.get_batch_members(batch_id)
        for member in original_members:
            self.add_batch_member(
                batch_id=new_batch.batch_id,
                token_id=member.token_id,
                ordinal=member.ordinal,
            )

        return new_batch

    # === Artifact Registration ===

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
        """Register an artifact produced by a sink.

        Args:
            run_id: Run that produced this artifact
            state_id: Node state that produced this artifact
            sink_node_id: Sink node that wrote the artifact
            artifact_type: Type of artifact (csv, json, etc.)
            path: File path or URI
            content_hash: Hash of artifact content
            size_bytes: Size of artifact in bytes
            artifact_id: Optional artifact ID
            idempotency_key: Optional key for retry deduplication

        Returns:
            Artifact model
        """
        artifact_id = artifact_id or generate_id()
        timestamp = now()

        artifact = Artifact(
            artifact_id=artifact_id,
            run_id=run_id,
            produced_by_state_id=state_id,
            sink_node_id=sink_node_id,
            artifact_type=artifact_type,
            path_or_uri=path,
            content_hash=content_hash,
            size_bytes=size_bytes,
            created_at=timestamp,
            idempotency_key=idempotency_key,
        )

        self._ops.execute_insert(
            artifacts_table.insert().values(
                artifact_id=artifact.artifact_id,
                run_id=artifact.run_id,
                produced_by_state_id=artifact.produced_by_state_id,
                sink_node_id=artifact.sink_node_id,
                artifact_type=artifact.artifact_type,
                path_or_uri=artifact.path_or_uri,
                content_hash=artifact.content_hash,
                size_bytes=artifact.size_bytes,
                idempotency_key=artifact.idempotency_key,
                created_at=artifact.created_at,
            )
        )

        return artifact

    def get_artifacts(
        self,
        run_id: str,
        *,
        sink_node_id: str | None = None,
    ) -> list[Artifact]:
        """Get artifacts for a run.

        Args:
            run_id: Run ID
            sink_node_id: Optional filter by sink

        Returns:
            List of Artifact models
        """
        query = select(artifacts_table).where(artifacts_table.c.run_id == run_id)

        if sink_node_id:
            query = query.where(artifacts_table.c.sink_node_id == sink_node_id)

        rows = self._ops.execute_fetchall(query)
        return [self._artifact_repo.load(row) for row in rows]
