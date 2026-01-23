# tests/engine/test_aggregation_audit.py
"""Tests for aggregation batch flush audit trail functionality.

These tests verify that the execute_flush() method correctly:
- Records audit trail (node_state)
- Transitions batch status lifecycle
- Records trigger reason
- Handles failures properly
"""

from typing import Any

import pytest

from elspeth.contracts import TokenInfo
from elspeth.contracts.enums import BatchStatus, NodeStateStatus, TriggerType
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.config import AggregationSettings, TriggerConfig
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
from elspeth.engine.executors import AggregationExecutor
from elspeth.engine.spans import SpanFactory
from elspeth.plugins.context import PluginContext
from elspeth.plugins.llm.batch_errors import BatchPendingError
from elspeth.plugins.results import TransformResult
from tests.conftest import _TestTransformBase, as_transform

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"fields": "dynamic"})


# === Mock Transforms ===
# These are simple test doubles that satisfy the minimum requirements
# for TransformProtocol without needing full PluginSchema types.


class MockBatchTransform(_TestTransformBase):
    """Mock batch-aware transform that sums values for testing."""

    name = "mock_batch_transform"

    def process(
        self,
        row: dict[str, Any] | list[dict[str, Any]],
        ctx: PluginContext,
    ) -> TransformResult:
        """Process a single row or batch of rows."""
        if isinstance(row, list):
            # Batch mode: sum all 'x' values
            total = sum(r.get("x", 0) for r in row)
            return TransformResult.success({"sum": total, "count": len(row)})
        # Single row mode
        return TransformResult.success(row)


class FailingBatchTransform(_TestTransformBase):
    """Mock batch-aware transform that always raises an exception."""

    name = "failing_batch_transform"

    def process(
        self,
        row: dict[str, Any] | list[dict[str, Any]],
        ctx: PluginContext,
    ) -> TransformResult:
        """Always raises RuntimeError."""
        raise RuntimeError("intentional failure")


class ErrorResultTransform(_TestTransformBase):
    """Mock batch-aware transform that returns an error result (doesn't raise)."""

    name = "error_result_transform"

    def process(
        self,
        row: dict[str, Any] | list[dict[str, Any]],
        ctx: PluginContext,
    ) -> TransformResult:
        """Returns an error result instead of raising."""
        return TransformResult.error({"message": "batch processing failed", "code": "BATCH_ERROR"})


class BatchPendingTransform(_TestTransformBase):
    """Mock batch-aware transform that raises BatchPendingError (async batch submission)."""

    name = "batch_pending_transform"

    def process(
        self,
        row: dict[str, Any] | list[dict[str, Any]],
        ctx: PluginContext,
    ) -> TransformResult:
        """Raises BatchPendingError to simulate async batch submission."""
        raise BatchPendingError(
            batch_id="test-batch-123",
            status="submitted",
            check_after_seconds=300,
            checkpoint={"batch_id": "test-batch-123", "rows": len(row) if isinstance(row, list) else 1},
            node_id=self.node_id,
        )


# === Fixtures ===


@pytest.fixture
def landscape_db() -> LandscapeDB:
    """Create a temporary in-memory Landscape database."""
    return LandscapeDB.in_memory()


@pytest.fixture
def recorder(landscape_db: LandscapeDB) -> LandscapeRecorder:
    """Create a LandscapeRecorder instance."""
    return LandscapeRecorder(landscape_db)


@pytest.fixture
def run_id(recorder: LandscapeRecorder) -> str:
    """Create a run and return its ID."""
    run = recorder.begin_run(config={}, canonical_version="v1")
    return run.run_id


@pytest.fixture
def aggregation_node_id(recorder: LandscapeRecorder, run_id: str) -> str:
    """Register an aggregation node and return its ID."""
    node = recorder.register_node(
        run_id=run_id,
        plugin_name="mock_batch_transform",
        node_type="aggregation",
        plugin_version="1.0.0",
        config={},
        schema_config=DYNAMIC_SCHEMA,
    )
    return node.node_id


@pytest.fixture
def source_node_id(recorder: LandscapeRecorder, run_id: str) -> str:
    """Register a source node and return its ID."""
    node = recorder.register_node(
        run_id=run_id,
        plugin_name="test_source",
        node_type="source",
        plugin_version="1.0.0",
        config={},
        schema_config=DYNAMIC_SCHEMA,
    )
    return node.node_id


@pytest.fixture
def ctx(run_id: str) -> PluginContext:
    """Create a PluginContext."""
    return PluginContext(run_id=run_id, config={})


@pytest.fixture
def aggregation_settings(aggregation_node_id: str) -> dict[str, AggregationSettings]:
    """Create aggregation settings with a count trigger."""
    settings = AggregationSettings(
        name="test_aggregation",
        plugin="mock_batch_transform",
        trigger=TriggerConfig(count=3),  # Trigger after 3 rows
    )
    return {aggregation_node_id: settings}


@pytest.fixture
def aggregation_executor(
    recorder: LandscapeRecorder,
    run_id: str,
    aggregation_settings: dict[str, AggregationSettings],
) -> AggregationExecutor:
    """Create an AggregationExecutor instance."""
    return AggregationExecutor(
        recorder=recorder,
        span_factory=SpanFactory(),
        run_id=run_id,
        aggregation_settings=aggregation_settings,
    )


def create_token(
    recorder: LandscapeRecorder,
    run_id: str,
    source_node_id: str,
    row_index: int,
    row_data: dict[str, Any],
) -> TokenInfo:
    """Helper to create a token with proper audit trail."""
    row_id = f"row-{row_index}"
    token_id = f"token-{row_index}"

    row = recorder.create_row(
        run_id=run_id,
        source_node_id=source_node_id,
        row_index=row_index,
        data=row_data,
        row_id=row_id,
    )
    recorder.create_token(row_id=row.row_id, token_id=token_id)

    return TokenInfo(
        row_id=row_id,
        token_id=token_id,
        row_data=row_data,
    )


# === Test Cases ===


class TestAggregationFlushAuditTrail:
    """Tests for aggregation batch flush audit trail functionality."""

    def test_flush_creates_node_state(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        aggregation_node_id: str,
        aggregation_executor: AggregationExecutor,
        ctx: PluginContext,
    ) -> None:
        """Flushing a batch should create a node_state record."""
        # Create and buffer tokens
        token1 = create_token(recorder, run_id, source_node_id, 0, {"x": 10})
        token2 = create_token(recorder, run_id, source_node_id, 1, {"x": 20})

        aggregation_executor.buffer_row(aggregation_node_id, token1)
        aggregation_executor.buffer_row(aggregation_node_id, token2)

        # Create transform with node_id set
        transform = MockBatchTransform()
        transform.node_id = aggregation_node_id

        # Execute flush
        result, _consumed_tokens = aggregation_executor.execute_flush(
            node_id=aggregation_node_id,
            transform=as_transform(transform),
            ctx=ctx,
            step_in_pipeline=1,
            trigger_type=TriggerType.COUNT,
        )

        # Verify result
        assert result.status == "success"
        assert result.row == {"sum": 30, "count": 2}

        # Verify node_state was created
        # The node_state is created using the first token's ID
        states = recorder.get_node_states_for_token(token1.token_id)
        assert len(states) >= 1

        # Find the state for our aggregation node
        agg_state = next((s for s in states if s.node_id == aggregation_node_id), None)
        assert agg_state is not None
        assert agg_state.status == "completed"

    def test_flush_transitions_batch_status(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        aggregation_node_id: str,
        aggregation_executor: AggregationExecutor,
        ctx: PluginContext,
    ) -> None:
        """Flushing should transition batch from draft -> executing -> completed."""
        # Create and buffer token
        token = create_token(recorder, run_id, source_node_id, 0, {"x": 10})
        aggregation_executor.buffer_row(aggregation_node_id, token)

        # Get batch_id before flush
        batch_id = aggregation_executor.get_batch_id(aggregation_node_id)
        assert batch_id is not None

        # Verify initial batch status is "draft"
        batch = recorder.get_batch(batch_id)
        assert batch is not None
        assert batch.status == BatchStatus.DRAFT.value

        # Create transform and execute flush
        transform = MockBatchTransform()
        transform.node_id = aggregation_node_id

        aggregation_executor.execute_flush(
            node_id=aggregation_node_id,
            transform=as_transform(transform),
            ctx=ctx,
            step_in_pipeline=1,
            trigger_type=TriggerType.COUNT,
        )

        # Verify final batch status is "completed"
        batch = recorder.get_batch(batch_id)
        assert batch is not None
        assert batch.status == BatchStatus.COMPLETED.value

    def test_failed_flush_marks_batch_failed(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        aggregation_node_id: str,
        aggregation_executor: AggregationExecutor,
        ctx: PluginContext,
    ) -> None:
        """Exception during flush should mark batch as failed."""
        # Create and buffer token
        token = create_token(recorder, run_id, source_node_id, 0, {"x": 10})
        aggregation_executor.buffer_row(aggregation_node_id, token)

        # Get batch_id before flush
        batch_id = aggregation_executor.get_batch_id(aggregation_node_id)
        assert batch_id is not None

        # Create failing transform and attempt flush
        transform = FailingBatchTransform()
        transform.node_id = aggregation_node_id

        with pytest.raises(RuntimeError, match="intentional failure"):
            aggregation_executor.execute_flush(
                node_id=aggregation_node_id,
                transform=as_transform(transform),
                ctx=ctx,
                step_in_pipeline=1,
                trigger_type=TriggerType.COUNT,
            )

        # Verify batch status is "failed"
        batch = recorder.get_batch(batch_id)
        assert batch is not None
        assert batch.status == BatchStatus.FAILED.value

        # Verify node_state was also marked as failed
        states = recorder.get_node_states_for_token(token.token_id)
        agg_state = next((s for s in states if s.node_id == aggregation_node_id), None)
        assert agg_state is not None
        assert agg_state.status == "failed"

    def test_error_result_marks_batch_failed(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        aggregation_node_id: str,
        aggregation_executor: AggregationExecutor,
        ctx: PluginContext,
    ) -> None:
        """Transform returning error result (not exception) should mark batch failed."""
        # Create and buffer token
        token = create_token(recorder, run_id, source_node_id, 0, {"x": 10})
        aggregation_executor.buffer_row(aggregation_node_id, token)

        # Get batch_id before flush
        batch_id = aggregation_executor.get_batch_id(aggregation_node_id)
        assert batch_id is not None

        # Create error-returning transform and execute flush
        transform = ErrorResultTransform()
        transform.node_id = aggregation_node_id

        result, _consumed_tokens = aggregation_executor.execute_flush(
            node_id=aggregation_node_id,
            transform=as_transform(transform),
            ctx=ctx,
            step_in_pipeline=1,
            trigger_type=TriggerType.COUNT,
        )

        # Verify result is error
        assert result.status == "error"
        assert result.reason == {
            "message": "batch processing failed",
            "code": "BATCH_ERROR",
        }

        # Verify batch status is "failed"
        batch = recorder.get_batch(batch_id)
        assert batch is not None
        assert batch.status == BatchStatus.FAILED.value

        # Verify node_state was also marked as failed
        states = recorder.get_node_states_for_token(token.token_id)
        agg_state = next((s for s in states if s.node_id == aggregation_node_id), None)
        assert agg_state is not None
        assert agg_state.status == "failed"

    def test_end_of_source_trigger_recorded(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        aggregation_node_id: str,
        aggregation_executor: AggregationExecutor,
        ctx: PluginContext,
    ) -> None:
        """END_OF_SOURCE trigger reason should be recorded in batch."""
        # Create and buffer token
        token = create_token(recorder, run_id, source_node_id, 0, {"x": 10})
        aggregation_executor.buffer_row(aggregation_node_id, token)

        # Get batch_id before flush
        batch_id = aggregation_executor.get_batch_id(aggregation_node_id)
        assert batch_id is not None

        # Create transform and execute flush with END_OF_SOURCE trigger
        transform = MockBatchTransform()
        transform.node_id = aggregation_node_id

        aggregation_executor.execute_flush(
            node_id=aggregation_node_id,
            transform=as_transform(transform),
            ctx=ctx,
            step_in_pipeline=1,
            trigger_type=TriggerType.END_OF_SOURCE,
        )

        # Verify trigger type was recorded
        batch = recorder.get_batch(batch_id)
        assert batch is not None
        assert batch.trigger_type == TriggerType.END_OF_SOURCE.value

    def test_flush_clears_buffers(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        aggregation_node_id: str,
        aggregation_executor: AggregationExecutor,
        ctx: PluginContext,
    ) -> None:
        """After flush, buffers should be cleared for next batch."""
        # Create and buffer tokens
        token1 = create_token(recorder, run_id, source_node_id, 0, {"x": 10})
        token2 = create_token(recorder, run_id, source_node_id, 1, {"x": 20})

        aggregation_executor.buffer_row(aggregation_node_id, token1)
        aggregation_executor.buffer_row(aggregation_node_id, token2)

        # Verify buffer has rows
        assert aggregation_executor.get_buffer_count(aggregation_node_id) == 2
        assert len(aggregation_executor.get_buffered_rows(aggregation_node_id)) == 2
        assert len(aggregation_executor.get_buffered_tokens(aggregation_node_id)) == 2

        # Create transform and execute flush
        transform = MockBatchTransform()
        transform.node_id = aggregation_node_id

        aggregation_executor.execute_flush(
            node_id=aggregation_node_id,
            transform=as_transform(transform),
            ctx=ctx,
            step_in_pipeline=1,
            trigger_type=TriggerType.COUNT,
        )

        # Verify buffers are cleared
        assert aggregation_executor.get_buffer_count(aggregation_node_id) == 0
        assert len(aggregation_executor.get_buffered_rows(aggregation_node_id)) == 0
        assert len(aggregation_executor.get_buffered_tokens(aggregation_node_id)) == 0

        # Verify batch_id is reset (ready for next batch)
        assert aggregation_executor.get_batch_id(aggregation_node_id) is None

    def test_flush_returns_consumed_tokens(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        aggregation_node_id: str,
        aggregation_executor: AggregationExecutor,
        ctx: PluginContext,
    ) -> None:
        """Flush should return list of all consumed tokens."""
        # Create and buffer tokens
        token1 = create_token(recorder, run_id, source_node_id, 0, {"x": 10})
        token2 = create_token(recorder, run_id, source_node_id, 1, {"x": 20})
        token3 = create_token(recorder, run_id, source_node_id, 2, {"x": 30})

        aggregation_executor.buffer_row(aggregation_node_id, token1)
        aggregation_executor.buffer_row(aggregation_node_id, token2)
        aggregation_executor.buffer_row(aggregation_node_id, token3)

        # Create transform and execute flush
        transform = MockBatchTransform()
        transform.node_id = aggregation_node_id

        _result, consumed_tokens = aggregation_executor.execute_flush(
            node_id=aggregation_node_id,
            transform=as_transform(transform),
            ctx=ctx,
            step_in_pipeline=1,
            trigger_type=TriggerType.COUNT,
        )

        # Verify consumed tokens
        assert len(consumed_tokens) == 3
        token_ids = {t.token_id for t in consumed_tokens}
        assert token_ids == {token1.token_id, token2.token_id, token3.token_id}

        # Verify row_data is preserved in tokens
        row_data_list = [t.row_data for t in consumed_tokens]
        assert {"x": 10} in row_data_list
        assert {"x": 20} in row_data_list
        assert {"x": 30} in row_data_list

    def test_batch_pending_error_closes_node_state_and_links_batch(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        ctx: PluginContext,
    ) -> None:
        """BatchPendingError must close node_state and link batch to prevent orphaned states.

        This test verifies the fix for P1-2026-01-21-aggregation-batch-pending-open-node-state.md:
        - BatchPendingError should complete the node_state (not leave it OPEN)
        - Batch must have aggregation_state_id set to link to the flush attempt
        - No orphaned OPEN states should remain in audit trail
        """
        # Setup aggregation executor with batch-pending transform
        transform = as_transform(BatchPendingTransform())
        transform.node_id = "batch_pending_node"

        aggregation_settings = AggregationSettings(
            name="batch_pending_aggregation",
            plugin="batch_pending_transform",
            trigger=TriggerConfig(count=2),
            output_mode="single",
        )

        # Register node in landscape first to get node_id
        node = recorder.register_node(
            run_id=run_id,
            plugin_name="batch_pending_transform",
            plugin_version="1.0.0",
            node_type="aggregation",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        node_id = node.node_id
        transform.node_id = node_id

        executor = AggregationExecutor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run_id,
            aggregation_settings={node_id: aggregation_settings},
        )

        # Create tokens in landscape using helper
        token1 = create_token(
            recorder=recorder,
            run_id=run_id,
            source_node_id=source_node_id,
            row_index=0,
            row_data={"x": 10},
        )
        token2 = create_token(
            recorder=recorder,
            run_id=run_id,
            source_node_id=source_node_id,
            row_index=1,
            row_data={"x": 20},
        )

        executor.buffer_row(node_id, token1)
        executor.buffer_row(node_id, token2)

        # Execute flush - should raise BatchPendingError
        with pytest.raises(BatchPendingError) as exc_info:
            executor.execute_flush(
                node_id=node_id,
                transform=transform,
                ctx=ctx,
                step_in_pipeline=1,
                trigger_type=TriggerType.COUNT,
            )

        # Verify BatchPendingError was raised with correct attributes
        assert exc_info.value.batch_id == "test-batch-123"
        assert exc_info.value.status == "submitted"

        # === CRITICAL ASSERTIONS (Bug Fix Verification) ===

        # 1. No OPEN node_states should remain
        with recorder._db.connection() as conn:
            from sqlalchemy import select

            from elspeth.core.landscape.schema import node_states_table

            open_states = conn.execute(select(node_states_table).where(node_states_table.c.status == NodeStateStatus.OPEN.value)).fetchall()

            assert len(open_states) == 0, (
                f"Found {len(open_states)} OPEN node_states after BatchPendingError. "
                "BatchPendingError must complete node_state before re-raising."
            )

        # 2. Node_state must exist and be completed
        with recorder._db.connection() as conn:
            all_states = conn.execute(select(node_states_table).where(node_states_table.c.node_id == node_id)).fetchall()

            assert len(all_states) == 1, f"Expected exactly 1 node_state, found {len(all_states)}"
            state = all_states[0]

            # State must be PENDING (batch submitted, result not available)
            assert state.status == NodeStateStatus.PENDING.value, (
                f"Node state has status '{state.status}' but should be 'pending' "
                f"(batch submitted successfully but result not available yet)"
            )

            # State must have completed_at timestamp (submission completed)
            assert state.completed_at is not None, "Node state must have completed_at timestamp set"

            # State must NOT have output_hash (batch result not available yet)
            assert state.output_hash is None, "PENDING state should not have output_hash (result not available)"

        # 3. Batch must be linked to the node_state
        with recorder._db.connection() as conn:
            from elspeth.core.landscape.schema import batches_table

            batches = conn.execute(select(batches_table).where(batches_table.c.aggregation_node_id == node_id)).fetchall()

            assert len(batches) == 1, f"Expected exactly 1 batch, found {len(batches)}"
            batch = batches[0]

            # Batch must have aggregation_state_id set
            assert batch.aggregation_state_id is not None, (
                "Batch must have aggregation_state_id linking it to the flush node_state. "
                "This enables tracing batch execution in the audit trail."
            )

            # aggregation_state_id must match the node_state we created
            assert batch.aggregation_state_id == state.state_id, (
                f"Batch aggregation_state_id ({batch.aggregation_state_id}) does not match node_state state_id ({state.state_id})"
            )

            # Batch status should still be "executing" (not completed/failed)
            # because BatchPendingError indicates work is in progress
            assert batch.status == "executing", (
                f"Batch status is '{batch.status}' but should be 'executing' after BatchPendingError (work is pending, not complete)"
            )
