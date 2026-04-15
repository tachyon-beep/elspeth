# tests/unit/contracts/test_control_flow_exceptions.py
"""Tests for control-flow exception attributes and defaults.

MaxRetriesExceeded is tested in tests/unit/engine/test_retry.py.
GracefulShutdownError is tested in tests/unit/engine/orchestrator/test_graceful_shutdown.py.

This file covers BatchPendingError attribute construction and defaults,
which were identified as untested in the code quality sweep.
"""

from __future__ import annotations

from elspeth.contracts.errors import BatchPendingError


class TestBatchPendingError:
    """BatchPendingError attributes and defaults."""

    def test_required_attributes(self) -> None:
        """batch_id and status are stored as attributes."""
        exc = BatchPendingError("batch-abc", "submitted")
        assert exc.batch_id == "batch-abc"
        assert exc.status == "submitted"

    def test_default_check_after_seconds(self) -> None:
        """Default check_after_seconds is 300 (5 minutes)."""
        exc = BatchPendingError("batch-1", "submitted")
        assert exc.check_after_seconds == 300

    def test_custom_check_after_seconds(self) -> None:
        exc = BatchPendingError("batch-1", "in_progress", check_after_seconds=60)
        assert exc.check_after_seconds == 60

    def test_default_checkpoint_is_none(self) -> None:
        exc = BatchPendingError("batch-1", "submitted")
        assert exc.checkpoint is None

    def test_default_node_id_is_none(self) -> None:
        exc = BatchPendingError("batch-1", "submitted")
        assert exc.node_id is None

    def test_checkpoint_and_node_id_stored(self) -> None:
        """When provided, checkpoint and node_id are preserved."""
        sentinel = object()
        exc = BatchPendingError(
            "batch-1",
            "submitted",
            checkpoint=sentinel,  # type: ignore[arg-type]  # deliberate: tests that arbitrary values are stored as-is
            node_id="transform-llm",
        )
        assert exc.checkpoint is sentinel
        assert exc.node_id == "transform-llm"

    def test_message_format(self) -> None:
        """Message includes batch_id, status, and check_after_seconds."""
        exc = BatchPendingError("batch-xyz", "in_progress", check_after_seconds=120)
        assert str(exc) == "Batch batch-xyz is in_progress, check after 120s"

    def test_is_exception(self) -> None:
        exc = BatchPendingError("batch-1", "submitted")
        assert isinstance(exc, Exception)
