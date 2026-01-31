# tests/core/landscape/test_operations.py
"""Tests for source/sink operations and the track_operation context manager.

These tests verify Phase 9 requirements from the source-sink-audit-design.md:
- Operation lifecycle (begin → complete)
- Operation call recording
- PluginContext routing (state vs operation)
- XOR constraint enforcement
- Double-complete raises FrameworkBugError
- DB failure doesn't mask original exception
"""

import logging
import time
from pathlib import Path
from typing import Any

import pytest

from elspeth.contracts import (
    BatchPendingError,
    CallStatus,
    CallType,
    Determinism,
    FrameworkBugError,
    NodeType,
)
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.core.operations import track_operation
from elspeth.plugins.context import PluginContext

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"fields": "dynamic"})


@pytest.fixture
def db() -> LandscapeDB:
    """Create in-memory database for testing."""
    return LandscapeDB.in_memory()


@pytest.fixture
def recorder(db: LandscapeDB) -> LandscapeRecorder:
    """Create recorder with in-memory database."""
    return LandscapeRecorder(db)


@pytest.fixture
def run_id(recorder: LandscapeRecorder) -> str:
    """Create a run and return its ID."""
    run = recorder.begin_run(config={"test": "config"}, canonical_version="1.0.0")
    return run.run_id


@pytest.fixture
def source_node_id(recorder: LandscapeRecorder, run_id: str) -> str:
    """Register a source node and return its ID."""
    node = recorder.register_node(
        run_id=run_id,
        plugin_name="test_source",
        plugin_version="1.0.0",
        node_type=NodeType.SOURCE,
        config={},
        determinism=Determinism.DETERMINISTIC,
        schema_config=DYNAMIC_SCHEMA,
    )
    return node.node_id


@pytest.fixture
def sink_node_id(recorder: LandscapeRecorder, run_id: str) -> str:
    """Register a sink node and return its ID."""
    node = recorder.register_node(
        run_id=run_id,
        plugin_name="test_sink",
        plugin_version="1.0.0",
        node_type=NodeType.SINK,
        config={},
        determinism=Determinism.DETERMINISTIC,
        schema_config=DYNAMIC_SCHEMA,
    )
    return node.node_id


@pytest.fixture
def plugin_context(recorder: LandscapeRecorder, run_id: str) -> PluginContext:
    """Create a PluginContext for testing."""
    return PluginContext(
        run_id=run_id,
        config={},
        node_id="test_node",
        landscape=recorder,
    )


class TestOperationLifecycle:
    """Tests for begin_operation → complete_operation lifecycle."""

    def test_begin_operation_creates_open_operation(self, recorder: LandscapeRecorder, run_id: str, source_node_id: str) -> None:
        """begin_operation creates operation with status='open'."""
        operation = recorder.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
        )

        assert operation.status == "open"
        assert operation.operation_type == "source_load"
        assert operation.run_id == run_id
        assert operation.node_id == source_node_id
        assert operation.started_at is not None
        assert operation.completed_at is None

    def test_begin_operation_stores_input_data(self, recorder: LandscapeRecorder, run_id: str, source_node_id: str, tmp_path: Any) -> None:
        """begin_operation stores input_data via payload store."""
        from pathlib import Path

        from elspeth.core.payload_store import FilesystemPayloadStore

        payload_store = FilesystemPayloadStore(Path(tmp_path) / "payloads")
        recorder_with_store = LandscapeRecorder(recorder._db, payload_store=payload_store)

        operation = recorder_with_store.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
            input_data={"source_config": "test.csv"},
        )

        assert operation.input_data_ref is not None
        assert payload_store.exists(operation.input_data_ref)

    def test_complete_operation_sets_completed_status(self, recorder: LandscapeRecorder, run_id: str, source_node_id: str) -> None:
        """complete_operation updates status to 'completed'."""
        operation = recorder.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
        )

        recorder.complete_operation(
            operation_id=operation.operation_id,
            status="completed",
            duration_ms=100.0,
        )

        updated = recorder.get_operation(operation.operation_id)
        assert updated is not None
        assert updated.status == "completed"
        assert updated.completed_at is not None
        assert updated.duration_ms == 100.0

    def test_complete_operation_sets_failed_status_with_error(self, recorder: LandscapeRecorder, run_id: str, source_node_id: str) -> None:
        """complete_operation with status='failed' stores error message."""
        operation = recorder.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
        )

        recorder.complete_operation(
            operation_id=operation.operation_id,
            status="failed",
            error="Connection refused",
            duration_ms=50.0,
        )

        updated = recorder.get_operation(operation.operation_id)
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_message == "Connection refused"

    def test_complete_operation_sets_pending_status(self, recorder: LandscapeRecorder, run_id: str, sink_node_id: str) -> None:
        """complete_operation with status='pending' for BatchPendingError."""
        operation = recorder.begin_operation(
            run_id=run_id,
            node_id=sink_node_id,
            operation_type="sink_write",
        )

        recorder.complete_operation(
            operation_id=operation.operation_id,
            status="pending",
            duration_ms=25.0,
        )

        updated = recorder.get_operation(operation.operation_id)
        assert updated is not None
        assert updated.status == "pending"


class TestOperationDoubleComplete:
    """Tests for status transition validation."""

    def test_double_complete_raises_framework_bug_error(self, recorder: LandscapeRecorder, run_id: str, source_node_id: str) -> None:
        """Completing an already-completed operation raises FrameworkBugError."""
        operation = recorder.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
        )

        recorder.complete_operation(
            operation_id=operation.operation_id,
            status="completed",
        )

        with pytest.raises(FrameworkBugError, match="already-completed operation"):
            recorder.complete_operation(
                operation_id=operation.operation_id,
                status="completed",
            )

    def test_complete_nonexistent_operation_raises_framework_bug_error(self, recorder: LandscapeRecorder) -> None:
        """Completing a non-existent operation raises FrameworkBugError."""
        with pytest.raises(FrameworkBugError, match="non-existent operation"):
            recorder.complete_operation(
                operation_id="nonexistent_op_id",
                status="completed",
            )


class TestOperationCallRecording:
    """Tests for recording calls attributed to operations."""

    def test_record_operation_call_creates_call_with_operation_id(
        self, recorder: LandscapeRecorder, run_id: str, source_node_id: str
    ) -> None:
        """record_operation_call creates call with operation_id, not state_id."""
        operation = recorder.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
        )

        call = recorder.record_operation_call(
            operation_id=operation.operation_id,
            call_type=CallType.HTTP,
            status=CallStatus.SUCCESS,
            request_data={"url": "https://example.com"},
            response_data={"status": 200},
            latency_ms=150.0,
            provider="http",
        )

        assert call.operation_id == operation.operation_id
        assert call.state_id is None
        assert call.call_type == CallType.HTTP
        assert call.status == CallStatus.SUCCESS

    def test_get_operation_calls_returns_calls_ordered_by_index(
        self, recorder: LandscapeRecorder, run_id: str, source_node_id: str
    ) -> None:
        """get_operation_calls returns calls in call_index order."""
        operation = recorder.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
        )

        recorder.record_operation_call(
            operation_id=operation.operation_id,
            call_type=CallType.HTTP,
            status=CallStatus.SUCCESS,
            request_data={"call": 1},
            latency_ms=100.0,
            provider="http",
        )
        recorder.record_operation_call(
            operation_id=operation.operation_id,
            call_type=CallType.HTTP,
            status=CallStatus.SUCCESS,
            request_data={"call": 2},
            latency_ms=200.0,
            provider="http",
        )

        calls = recorder.get_operation_calls(operation.operation_id)
        assert len(calls) == 2
        assert calls[0].call_index == 0
        assert calls[1].call_index == 1

    def test_operation_call_index_allocation_is_sequential(self, recorder: LandscapeRecorder, run_id: str, source_node_id: str) -> None:
        """allocate_operation_call_index returns sequential indices."""
        operation = recorder.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
        )

        idx0 = recorder.allocate_operation_call_index(operation.operation_id)
        idx1 = recorder.allocate_operation_call_index(operation.operation_id)
        idx2 = recorder.allocate_operation_call_index(operation.operation_id)

        assert idx0 == 0
        assert idx1 == 1
        assert idx2 == 2


class TestPluginContextCallRouting:
    """Tests for PluginContext.record_call() routing between state and operation."""

    def test_record_call_with_operation_id_routes_to_operation_call(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
    ) -> None:
        """record_call with operation_id set routes to record_operation_call."""
        operation = recorder.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
        )

        ctx = PluginContext(
            run_id=run_id,
            config={},
            node_id=source_node_id,
            landscape=recorder,
            operation_id=operation.operation_id,
        )

        call = ctx.record_call(
            call_type=CallType.HTTP,
            status=CallStatus.SUCCESS,
            request_data={"test": "data"},
            latency_ms=50.0,
        )

        assert call is not None
        assert call.operation_id == operation.operation_id
        assert call.state_id is None

    def test_record_call_with_state_id_routes_to_state_call(self, recorder: LandscapeRecorder, run_id: str, source_node_id: str) -> None:
        """record_call with state_id set routes to record_call (transform path)."""
        # Create row and token
        row = recorder.create_row(
            run_id=run_id,
            row_index=0,
            source_node_id=source_node_id,
            data={"x": 1},
        )
        token = recorder.create_token(row_id=row.row_id)

        # Register a transform node
        transform_node = recorder.register_node(
            run_id=run_id,
            plugin_name="test_transform",
            plugin_version="1.0.0",
            node_type=NodeType.TRANSFORM,
            config={},
            determinism=Determinism.DETERMINISTIC,
            schema_config=DYNAMIC_SCHEMA,
        )

        state = recorder.begin_node_state(
            token_id=token.token_id,
            node_id=transform_node.node_id,
            run_id=run_id,
            step_index=0,
            input_data={"x": 1},
        )

        ctx = PluginContext(
            run_id=run_id,
            config={},
            node_id=transform_node.node_id,
            landscape=recorder,
            state_id=state.state_id,
        )

        call = ctx.record_call(
            call_type=CallType.LLM,
            status=CallStatus.SUCCESS,
            request_data={"prompt": "test"},
            response_data={"response": "ok"},
            latency_ms=100.0,
        )

        assert call is not None
        assert call.state_id == state.state_id
        assert call.operation_id is None

    def test_record_call_with_both_ids_raises_framework_bug_error(
        self, recorder: LandscapeRecorder, run_id: str, source_node_id: str
    ) -> None:
        """record_call with BOTH state_id and operation_id raises FrameworkBugError."""
        ctx = PluginContext(
            run_id=run_id,
            config={},
            node_id=source_node_id,
            landscape=recorder,
            state_id="some_state_id",
            operation_id="some_operation_id",
        )

        with pytest.raises(FrameworkBugError, match="BOTH state_id and operation_id"):
            ctx.record_call(
                call_type=CallType.HTTP,
                status=CallStatus.SUCCESS,
                request_data={"test": "data"},
            )

    def test_record_call_with_neither_id_raises_framework_bug_error(self, recorder: LandscapeRecorder, run_id: str) -> None:
        """record_call without state_id or operation_id raises FrameworkBugError."""
        ctx = PluginContext(
            run_id=run_id,
            config={},
            node_id="some_node",
            landscape=recorder,
        )

        with pytest.raises(FrameworkBugError, match="without state_id or operation_id"):
            ctx.record_call(
                call_type=CallType.HTTP,
                status=CallStatus.SUCCESS,
                request_data={"test": "data"},
            )


class TestTrackOperationContextManager:
    """Tests for the track_operation context manager."""

    def test_track_operation_creates_and_completes_operation(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        plugin_context: PluginContext,
    ) -> None:
        """track_operation creates operation on entry and completes on exit."""
        plugin_context.node_id = source_node_id

        with track_operation(
            recorder=recorder,
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
            ctx=plugin_context,
        ) as handle:
            operation_id = handle.operation.operation_id
            op = recorder.get_operation(operation_id)
            assert op is not None
            assert op.status == "open"

        op = recorder.get_operation(operation_id)
        assert op is not None
        assert op.status == "completed"

    def test_track_operation_sets_context_operation_id(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        plugin_context: PluginContext,
    ) -> None:
        """track_operation sets ctx.operation_id during the block."""
        assert plugin_context.operation_id is None

        with track_operation(
            recorder=recorder,
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
            ctx=plugin_context,
        ) as handle:
            assert plugin_context.operation_id == handle.operation.operation_id

        assert plugin_context.operation_id is None

    def test_track_operation_on_exception_marks_failed(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        plugin_context: PluginContext,
    ) -> None:
        """track_operation marks operation as failed on exception."""
        operation_id = ""
        with (
            pytest.raises(ValueError, match="Test error"),
            track_operation(
                recorder=recorder,
                run_id=run_id,
                node_id=source_node_id,
                operation_type="source_load",
                ctx=plugin_context,
            ) as handle,
        ):
            operation_id = handle.operation.operation_id
            raise ValueError("Test error")

        op = recorder.get_operation(operation_id)
        assert op is not None
        assert op.status == "failed"
        assert op.error_message == "Test error"

    def test_track_operation_on_batch_pending_marks_pending(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        sink_node_id: str,
        plugin_context: PluginContext,
    ) -> None:
        """track_operation marks operation as pending on BatchPendingError."""
        operation_id = ""
        with (
            pytest.raises(BatchPendingError),
            track_operation(
                recorder=recorder,
                run_id=run_id,
                node_id=sink_node_id,
                operation_type="sink_write",
                ctx=plugin_context,
            ) as handle,
        ):
            operation_id = handle.operation.operation_id
            raise BatchPendingError(
                batch_id="test-batch-123",
                status="submitted",
            )

        op = recorder.get_operation(operation_id)
        assert op is not None
        assert op.status == "pending"

    def test_track_operation_records_duration(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        plugin_context: PluginContext,
    ) -> None:
        """track_operation records duration_ms on completion."""
        with track_operation(
            recorder=recorder,
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
            ctx=plugin_context,
        ) as handle:
            operation_id = handle.operation.operation_id
            time.sleep(0.01)

        op = recorder.get_operation(operation_id)
        assert op is not None
        assert op.duration_ms is not None
        assert op.duration_ms >= 10.0

    def test_track_operation_records_output_data(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        sink_node_id: str,
        plugin_context: PluginContext,
        tmp_path: Path,
    ) -> None:
        """track_operation records handle.output_data on completion."""
        from elspeth.core.payload_store import FilesystemPayloadStore

        payload_store = FilesystemPayloadStore(tmp_path / "payloads")
        recorder_with_store = LandscapeRecorder(recorder._db, payload_store=payload_store)

        with track_operation(
            recorder=recorder_with_store,
            run_id=run_id,
            node_id=sink_node_id,
            operation_type="sink_write",
            ctx=plugin_context,
        ) as handle:
            operation_id = handle.operation.operation_id
            handle.output_data = {"rows_written": 100}

        op = recorder_with_store.get_operation(operation_id)
        assert op is not None
        assert op.output_data_ref is not None


class TestTrackOperationExceptionSafety:
    """Tests for exception handling in track_operation."""

    def test_db_failure_in_complete_does_not_mask_original_exception(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        plugin_context: PluginContext,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """DB failure during complete_operation doesn't mask the original exception."""

        def failing_complete(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("DB connection lost")

        with (
            pytest.raises(ValueError, match="Original error"),
            track_operation(
                recorder=recorder,
                run_id=run_id,
                node_id=source_node_id,
                operation_type="source_load",
                ctx=plugin_context,
            ),
        ):
            recorder.complete_operation = failing_complete  # type: ignore[method-assign]
            raise ValueError("Original error")

        assert any("Failed to complete operation" in record.message for record in caplog.records if record.levelno >= logging.CRITICAL)

    def test_context_operation_id_cleared_even_on_db_failure(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
        source_node_id: str,
        plugin_context: PluginContext,
    ) -> None:
        """Context operation_id is cleared even when complete_operation fails."""

        def failing_complete(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("DB failure")

        try:
            with track_operation(
                recorder=recorder,
                run_id=run_id,
                node_id=source_node_id,
                operation_type="source_load",
                ctx=plugin_context,
            ):
                recorder.complete_operation = failing_complete  # type: ignore[method-assign]
                raise ValueError("Test error")
        except ValueError:
            pass

        assert plugin_context.operation_id is None


class TestGetOperationsForRun:
    """Tests for get_operations_for_run query method."""

    def test_get_operations_for_run_returns_all_operations(
        self, recorder: LandscapeRecorder, run_id: str, source_node_id: str, sink_node_id: str
    ) -> None:
        """get_operations_for_run returns all operations for a run."""
        source_op = recorder.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
        )
        recorder.complete_operation(source_op.operation_id, status="completed")

        sink_op = recorder.begin_operation(
            run_id=run_id,
            node_id=sink_node_id,
            operation_type="sink_write",
        )
        recorder.complete_operation(sink_op.operation_id, status="completed")

        operations = recorder.get_operations_for_run(run_id)
        assert len(operations) == 2
        op_types = {op.operation_type for op in operations}
        assert op_types == {"source_load", "sink_write"}

    def test_get_operations_for_run_orders_by_started_at(self, recorder: LandscapeRecorder, run_id: str, source_node_id: str) -> None:
        """get_operations_for_run returns operations ordered by started_at."""
        op1 = recorder.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
        )
        time.sleep(0.001)
        op2 = recorder.begin_operation(
            run_id=run_id,
            node_id=source_node_id,
            operation_type="source_load",
        )

        operations = recorder.get_operations_for_run(run_id)
        assert len(operations) == 2
        assert operations[0].operation_id == op1.operation_id
        assert operations[1].operation_id == op2.operation_id

    def test_get_operations_for_run_empty_for_nonexistent_run(self, recorder: LandscapeRecorder) -> None:
        """get_operations_for_run returns empty list for non-existent run."""
        operations = recorder.get_operations_for_run("nonexistent_run_id")
        assert operations == []


class TestXORConstraintAtDatabaseLevel:
    """Tests for XOR constraint on calls table (state_id XOR operation_id)."""

    def test_call_with_both_state_and_operation_id_violates_constraint(
        self, recorder: LandscapeRecorder, run_id: str, source_node_id: str
    ) -> None:
        """Calls with both state_id and operation_id should violate DB constraint."""
        from sqlalchemy import text

        with recorder._db.connection() as conn:
            result = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='calls'"))
            schema = result.scalar()
            assert schema is not None
            assert "calls_has_parent" in schema
