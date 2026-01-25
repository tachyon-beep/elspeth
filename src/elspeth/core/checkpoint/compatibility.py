"""Checkpoint compatibility validation for resume operations.

Validates that a checkpoint can be safely resumed with the current
pipeline configuration by checking topological compatibility.
"""

import structlog

from elspeth.contracts import Checkpoint, ResumeCheck
from elspeth.core.canonical import compute_upstream_topology_hash as compute_hash
from elspeth.core.canonical import stable_hash
from elspeth.core.dag import ExecutionGraph


class CheckpointCompatibilityValidator:
    """Validates checkpoint compatibility with current execution graph.

    Separates topology validation logic from RecoveryManager's concern
    of "can this run be resumed?" (status checks, checkpoint existence).

    A checkpoint is compatible if:
    1. Checkpoint node exists in current graph
    2. Checkpoint node config hasn't changed
    3. Upstream topology (nodes + edges) is unchanged

    Changes DOWNSTREAM of the checkpoint are allowed (e.g., adding transforms
    after checkpoint, changing sink config) because they don't affect
    already-processed rows.
    """

    def __init__(self) -> None:
        """Initialize validator."""
        self._logger = structlog.get_logger(__name__)

    def validate(
        self,
        checkpoint: Checkpoint,
        current_graph: ExecutionGraph,
    ) -> ResumeCheck:
        """Validate checkpoint compatibility with current graph topology.

        Args:
            checkpoint: The checkpoint to validate
            current_graph: Current execution graph from config

        Returns:
            ResumeCheck with can_resume=True if compatible,
            or can_resume=False with specific reason if not.
        """
        # Handle legacy checkpoints (pre-topology validation)
        if checkpoint.upstream_topology_hash is None:
            return self._handle_legacy_checkpoint(checkpoint)

        # Validation 1: Checkpoint node must exist
        if not current_graph.has_node(checkpoint.node_id):
            return ResumeCheck(
                can_resume=False,
                reason=f"Checkpoint node '{checkpoint.node_id}' no longer exists in pipeline config. "
                "The transform at the checkpoint position may have been removed or its config changed.",
            )

        # Validation 2: Checkpoint node config must be unchanged
        current_node_info = current_graph.get_node_info(checkpoint.node_id)
        current_config_hash = stable_hash(current_node_info.config)

        if checkpoint.checkpoint_node_config_hash != current_config_hash:
            orig_hash = checkpoint.checkpoint_node_config_hash or "unknown"
            return ResumeCheck(
                can_resume=False,
                reason=f"Checkpoint node '{checkpoint.node_id}' configuration has changed. "
                "Resuming would process remaining rows differently than original run. "
                f"(Original config hash: {orig_hash[:8]}..., "
                f"Current: {current_config_hash[:8]}...)",
            )

        # Validation 3: Upstream topology (nodes + edges) must be unchanged
        current_topology_hash = self.compute_upstream_topology_hash(current_graph, checkpoint.node_id)

        if checkpoint.upstream_topology_hash != current_topology_hash:
            # Provide detailed diagnostic
            return self._create_topology_mismatch_error(checkpoint, current_graph, checkpoint.upstream_topology_hash, current_topology_hash)

        # All validations passed
        return ResumeCheck(can_resume=True)

    def _handle_legacy_checkpoint(self, checkpoint: Checkpoint) -> ResumeCheck:
        """Reject legacy checkpoints created before topology validation.

        Per CLAUDE.md No Legacy Code Policy: No backward compatibility modes.
        Users must re-run from beginning to create topology-aware checkpoints.
        """
        return ResumeCheck(
            can_resume=False,
            reason="Legacy checkpoint without topology validation data. "
            "Cannot verify config compatibility. "
            "Re-run from beginning to create fresh checkpoint.",
        )

    def compute_upstream_topology_hash(
        self,
        graph: ExecutionGraph,
        node_id: str,
    ) -> str:
        """Delegate to canonical.compute_upstream_topology_hash()."""
        return compute_hash(graph, node_id)

    def _create_topology_mismatch_error(
        self,
        checkpoint: Checkpoint,
        current_graph: ExecutionGraph,
        expected_hash: str,
        actual_hash: str,
    ) -> ResumeCheck:
        """Create detailed error message for topology mismatch.

        Args:
            checkpoint: The checkpoint being validated
            current_graph: Current execution graph
            expected_hash: Topology hash from checkpoint
            actual_hash: Topology hash from current graph

        Returns:
            ResumeCheck with detailed mismatch information.
        """
        # Could add more diagnostics here: which nodes changed, etc.
        # For now, provide hash comparison for audit trail
        return ResumeCheck(
            can_resume=False,
            reason=f"Pipeline structure changed upstream of checkpoint node '{checkpoint.node_id}'. "
            f"Resuming would skip transforms or produce inconsistent results. "
            f"(Expected topology hash: {expected_hash[:8]}..., Actual: {actual_hash[:8]}...)",
        )
