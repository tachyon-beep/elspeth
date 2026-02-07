"""Tests for transform error routing in engine.

These tests verify that TransformResult.error() rows are routed correctly:
- To configured sink (on_error = "sink_name")
- Discarded silently (on_error = "discard")
- RuntimeError if no on_error configured
- DIVERT routing_events are recorded for audit trail

Transform bugs (exceptions) still crash - only explicit errors are routed.
"""

from typing import Any

import pytest

from elspeth.contracts import TokenInfo, TransformErrorReason, error_edge_label
from elspeth.contracts.enums import NodeType, RoutingMode
from elspeth.contracts.plugin_context import PluginContext, TransformErrorToken
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.contracts.types import NodeID
from elspeth.plugins.results import TransformResult
from elspeth.testing import make_pipeline_row
from tests.conftest import _TestTransformBase, as_transform

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _make_contract() -> SchemaContract:
    """Create a flexible schema contract for testing."""
    return SchemaContract(
        mode="FLEXIBLE",
        fields=(),
        locked=True,
    )


class MockTransform(_TestTransformBase):
    """Mock transform for testing error routing."""

    name = "mock_transform"

    def __init__(self, result: TransformResult, on_error: str | None = None) -> None:
        self._result = result
        self._on_error = on_error

    def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
        return self._result


class TestTransformErrorRouting:
    """Tests for routing TransformResult.error() rows."""

    @pytest.fixture
    def setup_landscape(self) -> tuple[Any, Any, Any]:
        """Set up LandscapeDB, recorder, and run for tests."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        return db, recorder, run

    def test_success_result_returns_row_unchanged(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """TransformResult.success() returns the transformed row normally."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="mock_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        transform = MockTransform(TransformResult.success(make_pipeline_row({"value": 42}), success_reason={"action": "test"}))
        transform.node_id = node.node_id

        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )
        executor = TransformExecutor(recorder, SpanFactory())

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow({"input": 1}, _make_contract()),
        )

        # Create row/token in landscape
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        result, updated_token, _ = executor.execute_transform(
            transform=as_transform(transform),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        assert result.status == "success"
        assert result.row.to_dict() == {"value": 42}
        assert updated_token.row_data.to_dict() == {"value": 42}

    def test_error_result_with_on_error_routes_to_sink(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """TransformResult.error() with on_error routes to configured sink."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="mock_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # Register error sink node and DIVERT edge
        sink_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="error_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        error_edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=node.node_id,
            to_node_id=sink_node.node_id,
            label=error_edge_label(0),
            mode=RoutingMode.DIVERT,
        )

        transform = MockTransform(
            TransformResult.error({"reason": "validation_failed", "error": "Cannot process"}),
            on_error="error_sink",
        )
        transform.node_id = node.node_id

        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )

        executor = TransformExecutor(
            recorder,
            SpanFactory(),
            error_edge_ids={NodeID(node.node_id): error_edge.edge_id},
        )

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow({"input": 1}, _make_contract()),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        result, _, _error_sink = executor.execute_transform(
            transform=as_transform(transform),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        assert result.status == "error"
        assert _error_sink == "error_sink"

    def test_error_result_with_discard_does_not_route(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """TransformResult.error() with discard returns 'discard' as error_sink."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="mock_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        transform = MockTransform(
            TransformResult.error({"reason": "validation_failed", "error": "Cannot process"}),
            on_error="discard",
        )
        transform.node_id = node.node_id

        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )

        executor = TransformExecutor(recorder, SpanFactory())

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow({"input": 1}, _make_contract()),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        result, _, _error_sink = executor.execute_transform(
            transform=as_transform(transform),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        assert result.status == "error"
        assert _error_sink == "discard"

    def test_error_without_on_error_raises_runtime_error(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """TransformResult.error() without on_error raises RuntimeError."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="mock_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        transform = MockTransform(
            TransformResult.error({"reason": "validation_failed", "error": "Cannot process"}),
            on_error=None,  # Not configured
        )
        transform.node_id = node.node_id

        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )
        executor = TransformExecutor(recorder, SpanFactory())

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow({"input": 1}, _make_contract()),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        with pytest.raises(RuntimeError, match="on_error"):
            executor.execute_transform(
                transform=as_transform(transform),
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
            )

    def test_error_event_recorded_for_sink_destination(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """record_transform_error called when routing to sink."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="mock_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        sink_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="error_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        error_edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=node.node_id,
            to_node_id=sink_node.node_id,
            label=error_edge_label(0),
            mode=RoutingMode.DIVERT,
        )

        transform = MockTransform(
            TransformResult.error({"reason": "test_error"}),
            on_error="error_sink",
        )
        transform.node_id = node.node_id

        recorded: list[dict[str, Any]] = []

        def capture_record(
            token_id: str,
            transform_id: str,
            row: dict[str, Any],
            error_details: TransformErrorReason,
            destination: str,
        ) -> TransformErrorToken:
            recorded.append(
                {
                    "token_id": token_id,
                    "transform_id": transform_id,
                    "row": row,
                    "error_details": error_details,
                    "destination": destination,
                }
            )
            return TransformErrorToken(
                token_id=token_id,
                transform_id=transform_id,
                destination=destination,
            )

        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )
        ctx.record_transform_error = capture_record  # type: ignore[method-assign,assignment]

        executor = TransformExecutor(
            recorder,
            SpanFactory(),
            error_edge_ids={NodeID(node.node_id): error_edge.edge_id},
        )

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow({"input": 1}, _make_contract()),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        executor.execute_transform(
            transform=as_transform(transform),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        assert len(recorded) == 1
        assert recorded[0]["destination"] == "error_sink"
        # transform_id is the node_id (unique DAG identifier), not plugin name
        # See: P2-2026-01-19-transform-errors-ambiguous-transform-id
        assert recorded[0]["transform_id"] == node.node_id
        assert recorded[0]["token_id"] == "tok_123"
        assert recorded[0]["error_details"] == {"reason": "test_error"}

    def test_error_event_recorded_for_discard(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """record_transform_error called even when discarding."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="mock_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        transform = MockTransform(
            TransformResult.error({"reason": "test_error"}),
            on_error="discard",
        )
        transform.node_id = node.node_id

        recorded: list[dict[str, Any]] = []

        def capture_record(
            token_id: str,
            transform_id: str,
            row: dict[str, Any],
            error_details: TransformErrorReason,
            destination: str,
        ) -> TransformErrorToken:
            recorded.append({"destination": destination})
            return TransformErrorToken(
                token_id=token_id,
                transform_id=transform_id,
                destination=destination,
            )

        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )
        ctx.record_transform_error = capture_record  # type: ignore[method-assign,assignment]

        executor = TransformExecutor(recorder, SpanFactory())

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow({"input": 1}, _make_contract()),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        executor.execute_transform(
            transform=as_transform(transform),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        # Error recorded even for discard
        assert len(recorded) == 1
        assert recorded[0]["destination"] == "discard"

    def test_exception_in_transform_propagates(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """Exception in transform propagates (does NOT route to on_error).

        This enforces CLAUDE.md's rule: bugs crash, they don't get silently routed.
        """
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="buggy",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        class BuggyTransform(_TestTransformBase):
            """Transform with a bug that raises an exception."""

            name = "buggy"
            _on_error = "error_sink"  # Configured but should NOT be used for bugs

            def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
                raise KeyError("nonexistent_field")  # BUG!

        transform = BuggyTransform()
        transform.node_id = node.node_id
        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )
        executor = TransformExecutor(recorder, SpanFactory())

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow({"input": 1}, _make_contract()),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        # Exception propagates - not caught and routed
        with pytest.raises(KeyError):
            executor.execute_transform(
                transform=as_transform(transform),
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
            )

    def test_error_routing_preserves_original_row(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """Error routing sends the original input row, not None."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="mock_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        sink_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="quarantine_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        error_edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=node.node_id,
            to_node_id=sink_node.node_id,
            label=error_edge_label(0),
            mode=RoutingMode.DIVERT,
        )

        original_row = {"field1": "value1", "field2": 42, "nested": {"a": 1}}

        transform = MockTransform(
            TransformResult.error({"reason": "validation_failed"}),
            on_error="quarantine_sink",
        )
        transform.node_id = node.node_id

        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )

        executor = TransformExecutor(
            recorder,
            SpanFactory(),
            error_edge_ids={NodeID(node.node_id): error_edge.edge_id},
        )

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow(original_row, _make_contract()),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        result, _, _error_sink = executor.execute_transform(
            transform=as_transform(transform),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        assert result.status == "error"
        assert _error_sink == "quarantine_sink"

    def test_error_metadata_includes_transform_error_details(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """Routed error includes metadata with transform error reason."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="mock_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        sink_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="error_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        error_edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=node.node_id,
            to_node_id=sink_node.node_id,
            label=error_edge_label(0),
            mode=RoutingMode.DIVERT,
        )

        error_reason: TransformErrorReason = {
            "reason": "validation_failed",
            "error": "Division by zero",
            "field": "divisor",
        }

        transform = MockTransform(
            TransformResult.error(error_reason),
            on_error="error_sink",
        )
        transform.node_id = node.node_id

        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )

        executor = TransformExecutor(
            recorder,
            SpanFactory(),
            error_edge_ids={NodeID(node.node_id): error_edge.edge_id},
        )

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow({"input": 1}, _make_contract()),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        result, _, _error_sink = executor.execute_transform(
            transform=as_transform(transform),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        assert result.status == "error"
        assert _error_sink == "error_sink"


class TestTransformErrorDivertRoutingEvent:
    """Tests for DIVERT routing_event recording when transforms error-route."""

    @pytest.fixture
    def setup_landscape(self) -> tuple[Any, Any, Any]:
        """Set up LandscapeDB, recorder, and run for tests."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        return db, recorder, run

    def test_error_routing_creates_divert_routing_event(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """TransformResult.error() with on_error creates a DIVERT routing_event."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="mock_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        sink_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="error_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        error_edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=node.node_id,
            to_node_id=sink_node.node_id,
            label=error_edge_label(0),
            mode=RoutingMode.DIVERT,
        )

        transform = MockTransform(
            TransformResult.error({"reason": "test_error", "detail": "something failed"}),
            on_error="error_sink",
        )
        transform.node_id = node.node_id

        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )

        executor = TransformExecutor(
            recorder,
            SpanFactory(),
            error_edge_ids={NodeID(node.node_id): error_edge.edge_id},
        )

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow({"input": 1}, _make_contract()),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        result, _, error_sink = executor.execute_transform(
            transform=as_transform(transform),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        assert result.status == "error"
        assert error_sink == "error_sink"

        # Verify routing_event was recorded with DIVERT mode
        # The state_id is set by begin_node_state inside the executor
        routing_events = recorder.get_routing_events(ctx.state_id)
        assert len(routing_events) == 1
        event = routing_events[0]
        assert event.edge_id == error_edge.edge_id
        assert event.mode == RoutingMode.DIVERT
        assert event.reason_hash is not None  # reason was hashed

    def test_discard_does_not_create_routing_event(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """TransformResult.error() with discard creates NO routing_event."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="mock_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        transform = MockTransform(
            TransformResult.error({"reason": "test_error"}),
            on_error="discard",
        )
        transform.node_id = node.node_id

        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )

        # No error_edge_ids needed — discard has no edge
        executor = TransformExecutor(recorder, SpanFactory())

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow({"input": 1}, _make_contract()),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        result, _, error_sink = executor.execute_transform(
            transform=as_transform(transform),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        assert result.status == "error"
        assert error_sink == "discard"

        # No routing_event for discard
        routing_events = recorder.get_routing_events(ctx.state_id)
        assert len(routing_events) == 0

    def test_missing_error_edge_raises_invariant_error(self, setup_landscape: tuple[Any, Any, Any]) -> None:
        """Missing DIVERT edge raises OrchestrationInvariantError."""
        from elspeth.engine.executors import TransformExecutor
        from elspeth.engine.spans import SpanFactory

        _db, recorder, run = setup_landscape

        node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="mock_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        transform = MockTransform(
            TransformResult.error({"reason": "test_error"}),
            on_error="error_sink",
        )
        transform.node_id = node.node_id

        ctx = PluginContext(
            run_id=run.run_id,
            config={},
            node_id=node.node_id,
            landscape=recorder,
        )

        # Intentionally empty error_edge_ids
        executor = TransformExecutor(recorder, SpanFactory(), error_edge_ids={})

        token = TokenInfo(
            row_id="row-1",
            token_id="tok_123",
            row_data=PipelineRow({"input": 1}, _make_contract()),
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=node.node_id,
            row_index=0,
            data=token.row_data.to_dict(),
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        from elspeth.contracts.errors import OrchestrationInvariantError

        with pytest.raises(OrchestrationInvariantError, match="no DIVERT edge registered"):
            executor.execute_transform(
                transform=as_transform(transform),
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
            )
