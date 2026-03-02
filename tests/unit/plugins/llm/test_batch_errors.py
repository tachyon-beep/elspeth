"""Tests for batch processing control flow errors.

BatchPendingError is NOT a failure - it's a control flow signal that tells
the engine to schedule retry checks later. These tests verify:
1. Exception construction with various parameters
2. Default values are correct
3. Message format is correct
4. Exception is catchable and carries correct state
"""

from elspeth.contracts import BatchPendingError
from elspeth.contracts.batch_checkpoint import BatchCheckpointState, RowMappingEntry


class TestBatchPendingErrorConstruction:
    """Tests for BatchPendingError constructor."""

    def test_minimal_construction(self) -> None:
        """BatchPendingError can be constructed with just batch_id and status."""
        error = BatchPendingError("batch-123", "submitted")

        assert error.batch_id == "batch-123"
        assert error.status == "submitted"
        assert error.check_after_seconds == 300  # Default
        assert error.checkpoint is None  # Default
        assert error.node_id is None  # Default

    def test_full_construction(self) -> None:
        """BatchPendingError accepts all optional parameters."""
        checkpoint_data = BatchCheckpointState(
            batch_id="batch-123",
            input_file_id="file-001",
            row_mapping={
                "r1": RowMappingEntry(index=0, variables_hash="aaa"),
                "r2": RowMappingEntry(index=1, variables_hash="bbb"),
            },
            template_errors=[],
            submitted_at="2026-01-21T12:00:00Z",
            row_count=2,
            requests={},
        )
        error = BatchPendingError(
            "batch-123",
            "in_progress",
            check_after_seconds=600,
            checkpoint=checkpoint_data,
            node_id="llm_transform",
        )

        assert error.batch_id == "batch-123"
        assert error.status == "in_progress"
        assert error.check_after_seconds == 600
        assert error.checkpoint == checkpoint_data
        assert error.node_id == "llm_transform"

    def test_custom_check_after_seconds(self) -> None:
        """check_after_seconds can be customized."""
        error = BatchPendingError("batch-123", "submitted", check_after_seconds=60)

        assert error.check_after_seconds == 60

    def test_checkpoint_carries_typed_state(self) -> None:
        """Checkpoint carries BatchCheckpointState for caller persistence."""
        checkpoint = BatchCheckpointState(
            batch_id="batch-123",
            input_file_id="file-001",
            row_mapping={
                "token_1": RowMappingEntry(index=0, variables_hash="aaa"),
                "token_2": RowMappingEntry(index=1, variables_hash="bbb"),
            },
            template_errors=[],
            submitted_at="2026-01-21T12:00:00Z",
            row_count=2,
            requests={"token_1": {"model": "gpt-4"}, "token_2": {"model": "gpt-4"}},
        )
        error = BatchPendingError("batch-123", "submitted", checkpoint=checkpoint)

        assert error.checkpoint == checkpoint
        assert error.checkpoint.row_mapping["token_1"].index == 0
        assert error.checkpoint.row_mapping["token_2"].index == 1


class TestBatchPendingErrorMessage:
    """Tests for BatchPendingError exception message."""

    def test_message_format(self) -> None:
        """Exception message follows expected format."""
        error = BatchPendingError("batch-abc", "submitted", check_after_seconds=300)

        assert str(error) == "Batch batch-abc is submitted, check after 300s"

    def test_message_includes_status(self) -> None:
        """Exception message includes the current status."""
        error = BatchPendingError("batch-xyz", "in_progress", check_after_seconds=120)

        assert "in_progress" in str(error)
        assert "batch-xyz" in str(error)
        assert "120s" in str(error)

    def test_message_with_different_statuses(self) -> None:
        """Exception message works with various status values."""
        statuses = ["submitted", "in_progress", "validating", "finalizing"]

        for status in statuses:
            error = BatchPendingError("batch-123", status)
            assert status in str(error)


class TestBatchPendingErrorInheritance:
    """Tests for BatchPendingError exception inheritance."""

    def test_inherits_from_exception(self) -> None:
        """BatchPendingError is an Exception subclass."""
        error = BatchPendingError("batch-123", "submitted")

        assert isinstance(error, Exception)

    def test_catchable_as_exception(self) -> None:
        """BatchPendingError can be caught as Exception."""
        caught = False
        try:
            raise BatchPendingError("batch-123", "submitted")
        except Exception:
            caught = True

        assert caught is True

    def test_catchable_as_batch_pending_error(self) -> None:
        """BatchPendingError can be caught specifically."""
        checkpoint = BatchCheckpointState(
            batch_id="batch-123",
            input_file_id="file-001",
            row_mapping={},
            template_errors=[],
            submitted_at="2026-01-21T12:00:00Z",
            row_count=0,
            requests={},
        )
        caught_error = None
        try:
            raise BatchPendingError(
                "batch-123",
                "in_progress",
                check_after_seconds=600,
                checkpoint=checkpoint,
                node_id="my_transform",
            )
        except BatchPendingError as e:
            caught_error = e

        assert caught_error is not None
        assert caught_error.batch_id == "batch-123"
        assert caught_error.status == "in_progress"
        assert caught_error.check_after_seconds == 600
        assert caught_error.checkpoint == checkpoint
        assert caught_error.node_id == "my_transform"


class TestBatchPendingErrorUsagePatterns:
    """Tests demonstrating typical usage patterns."""

    def test_submit_phase_pattern(self) -> None:
        """Demonstrates Phase 1: submit batch and signal pending."""
        # Simulating batch submission
        batch_id = "batch-2026-01-21-001"
        checkpoint_data = BatchCheckpointState(
            batch_id=batch_id,
            input_file_id="file-001",
            row_mapping={
                "token_a": RowMappingEntry(index=0, variables_hash="aaa"),
                "token_b": RowMappingEntry(index=1, variables_hash="bbb"),
                "token_c": RowMappingEntry(index=2, variables_hash="ccc"),
            },
            template_errors=[],
            submitted_at="2026-01-21T12:00:00Z",
            row_count=3,
            requests={},
        )

        error = BatchPendingError(
            batch_id,
            "submitted",
            check_after_seconds=300,
            checkpoint=checkpoint_data,
            node_id="sentiment_analyzer",
        )

        # Caller would persist checkpoint and schedule retry
        assert error.checkpoint is not None
        assert error.checkpoint.batch_id == batch_id
        assert len(error.checkpoint.row_mapping) == 3

    def test_check_phase_pattern_still_pending(self) -> None:
        """Demonstrates Phase 2: check and still pending."""
        # Simulating status check where batch is still running
        persisted_checkpoint = BatchCheckpointState(
            batch_id="batch-123",
            input_file_id="file-001",
            row_mapping={"t1": RowMappingEntry(index=0, variables_hash="aaa")},
            template_errors=[],
            submitted_at="2026-01-21T12:00:00Z",
            row_count=1,
            requests={},
        )

        # Check status... still in progress
        error = BatchPendingError(
            "batch-123",
            "in_progress",
            check_after_seconds=120,  # Maybe check more frequently now
            checkpoint=persisted_checkpoint,
            node_id="sentiment_analyzer",
        )

        assert error.status == "in_progress"
        assert error.check_after_seconds == 120  # Adjusted timing

    def test_node_id_for_checkpoint_keying(self) -> None:
        """node_id enables per-transform checkpoint keying."""
        # Multiple transforms might have active batches
        error1 = BatchPendingError("batch-a", "submitted", node_id="transform_1")
        error2 = BatchPendingError("batch-b", "submitted", node_id="transform_2")

        assert error1.node_id != error2.node_id
        # Caller can use node_id to key checkpoints per-transform
