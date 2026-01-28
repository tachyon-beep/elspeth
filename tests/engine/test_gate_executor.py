"""Tests for gate executor."""

from typing import Any

import pytest

from elspeth.contracts import NodeID, RoutingMode
from elspeth.contracts.audit import NodeStateFailed
from elspeth.contracts.enums import NodeStateStatus, NodeType
from elspeth.contracts.schema import SchemaConfig
from tests.conftest import as_gate

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"fields": "dynamic"})


class TestGateExecutor:
    """Gate execution with audit and routing."""

    def test_execute_gate_continue(self) -> None:
        """Gate returns continue action - routing event recorded for audit (AUD-002)."""
        from elspeth.contracts import TokenInfo
        from elspeth.contracts.enums import RoutingMode
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext
        from elspeth.plugins.results import GateResult, RoutingAction

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="pass_through",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        # Register a "next node" for continue edge
        next_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="output",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        # Register continue edge from gate to next node
        continue_edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=next_node.node_id,
            label="continue",
            mode=RoutingMode.MOVE,
        )
        edge_map: dict[tuple[NodeID, str], str] = {(NodeID(gate_node.node_id), "continue"): continue_edge.edge_id}

        # Mock gate that continues
        class PassThroughGate:
            name = "pass_through"
            node_id = gate_node.node_id

            def evaluate(self, row: dict[str, Any], ctx: PluginContext) -> GateResult:
                return GateResult(
                    row=row,
                    action=RoutingAction.continue_(),
                )

        gate = PassThroughGate()
        ctx = PluginContext(run_id=run.run_id, config={})
        executor = GateExecutor(recorder, SpanFactory(), edge_map=edge_map)

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": 42},
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        outcome = executor.execute_gate(
            gate=as_gate(gate),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        # Verify outcome
        assert outcome.result.action.kind == "continue"
        assert outcome.sink_name is None
        assert outcome.child_tokens == []
        assert outcome.updated_token.row_data == {"value": 42}

        # Verify audit fields populated
        assert outcome.result.input_hash is not None
        assert outcome.result.output_hash is not None
        assert outcome.result.duration_ms is not None

        # Verify node state recorded as completed
        states = recorder.get_node_states_for_token(token.token_id)
        assert len(states) == 1
        assert states[0].status == NodeStateStatus.COMPLETED

        # Verify routing event recorded for continue (AUD-002)
        events = recorder.get_routing_events(states[0].state_id)
        assert len(events) == 1
        assert events[0].edge_id == continue_edge.edge_id
        assert events[0].mode == RoutingMode.MOVE

    def test_execute_gate_route(self) -> None:
        """Gate routes to sink via route label - routing event recorded."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext
        from elspeth.plugins.results import GateResult, RoutingAction

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        # Register gate and sink nodes
        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="threshold_gate",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={"threshold": 100},
            schema_config=DYNAMIC_SCHEMA,
        )
        sink_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="high_values",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # Register edge from gate to sink using route label
        edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=sink_node.node_id,
            label="above",  # Route label, not sink name
            mode=RoutingMode.MOVE,
        )

        # Mock gate that routes high values using route label
        class ThresholdGate:
            name = "threshold_gate"
            node_id = gate_node.node_id

            def evaluate(self, row: dict[str, Any], ctx: PluginContext) -> GateResult:
                if row.get("value", 0) > 100:
                    return GateResult(
                        row=row,
                        action=RoutingAction.route(
                            "above",  # Route label
                            reason={"threshold_exceeded": True, "value": row["value"]},
                        ),
                    )
                return GateResult(row=row, action=RoutingAction.continue_())

        gate = ThresholdGate()
        ctx = PluginContext(run_id=run.run_id, config={})

        # Edge map: (node_id, label) -> edge_id
        edge_map: dict[tuple[NodeID, str], str] = {(NodeID(gate_node.node_id), "above"): edge.edge_id}
        # Route resolution map: (node_id, label) -> sink_name
        route_resolution_map: dict[tuple[NodeID, str], str] = {(NodeID(gate_node.node_id), "above"): "high_values"}
        executor = GateExecutor(recorder, SpanFactory(), edge_map, route_resolution_map)

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": 150},  # Above threshold
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        outcome = executor.execute_gate(
            gate=as_gate(gate),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        # Verify outcome
        assert outcome.result.action.kind == "route"
        assert outcome.sink_name == "high_values"
        assert outcome.child_tokens == []

        # Verify node state recorded as completed (terminal state derived from events)
        states = recorder.get_node_states_for_token(token.token_id)
        assert len(states) == 1
        assert states[0].status == NodeStateStatus.COMPLETED

        # Verify routing event recorded
        events = recorder.get_routing_events(states[0].state_id)
        assert len(events) == 1
        assert events[0].edge_id == edge.edge_id
        assert events[0].mode == RoutingMode.MOVE

    def test_missing_edge_raises_error(self) -> None:
        """Gate routing to unregistered route label raises MissingEdgeError."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor, MissingEdgeError
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext
        from elspeth.plugins.results import GateResult, RoutingAction

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="broken_gate",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # Mock gate that routes to a label that has no route resolution
        class BrokenGate:
            name = "broken_gate"
            node_id = gate_node.node_id

            def evaluate(self, row: dict[str, Any], ctx: PluginContext) -> GateResult:
                return GateResult(
                    row=row,
                    action=RoutingAction.route("nonexistent_label"),
                )

        gate = BrokenGate()
        ctx = PluginContext(run_id=run.run_id, config={})

        # Empty route resolution map - label not configured
        executor = GateExecutor(recorder, SpanFactory(), edge_map={}, route_resolution_map={})

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": 42},
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        with pytest.raises(MissingEdgeError) as exc_info:
            executor.execute_gate(
                gate=as_gate(gate),
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
            )

        # Verify error details
        assert exc_info.value.node_id == gate_node.node_id
        assert exc_info.value.label == "nonexistent_label"
        assert "Audit trail would be incomplete" in str(exc_info.value)

        # Verify node_state was completed with FAILED status (not left OPEN)
        states = recorder.get_node_states_for_token(token.token_id)
        assert len(states) == 1
        assert states[0].status == NodeStateStatus.FAILED

        # Verify audit fields are populated (P3 fix completeness)
        state = states[0]
        assert state.duration_ms is not None, "duration_ms must be recorded on failed state"
        assert state.duration_ms >= 0, "duration_ms must be non-negative"
        # Error details are stored in the database - verify via raw query
        # (NodeState model may not expose error fields directly)

    def test_execute_gate_fork(self) -> None:
        """Gate forks to multiple paths - routing events and child tokens created."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.engine.tokens import TokenManager
        from elspeth.plugins.context import PluginContext
        from elspeth.plugins.results import GateResult, RoutingAction

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        # Register gate and path nodes
        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="splitter",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        path_a_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="path_a",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        path_b_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="path_b",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # Register edges
        edge_a = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=path_a_node.node_id,
            label="path_a",
            mode=RoutingMode.COPY,
        )
        edge_b = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=path_b_node.node_id,
            label="path_b",
            mode=RoutingMode.COPY,
        )

        # Mock gate that forks to both paths
        class SplitterGate:
            name = "splitter"
            node_id = gate_node.node_id

            def evaluate(self, row: dict[str, Any], ctx: PluginContext) -> GateResult:
                return GateResult(
                    row=row,
                    action=RoutingAction.fork_to_paths(
                        ["path_a", "path_b"],
                        reason={"split_reason": "parallel processing"},
                    ),
                )

        gate = SplitterGate()
        ctx = PluginContext(run_id=run.run_id, config={})

        edge_map: dict[tuple[NodeID, str], str] = {
            (NodeID(gate_node.node_id), "path_a"): edge_a.edge_id,
            (NodeID(gate_node.node_id), "path_b"): edge_b.edge_id,
        }
        executor = GateExecutor(recorder, SpanFactory(), edge_map)
        token_manager = TokenManager(recorder)

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": 42},
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        outcome = executor.execute_gate(
            gate=as_gate(gate),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
            token_manager=token_manager,
        )

        # Verify outcome
        assert outcome.result.action.kind == "fork_to_paths"
        assert outcome.sink_name is None
        assert len(outcome.child_tokens) == 2

        # Verify child tokens have correct branch names
        branch_names = {t.branch_name for t in outcome.child_tokens}
        assert branch_names == {"path_a", "path_b"}

        # Verify all child tokens share the same row_id
        for child in outcome.child_tokens:
            assert child.row_id == token.row_id
            assert child.row_data == {"value": 42}

        # Verify routing events recorded
        states = recorder.get_node_states_for_token(token.token_id)
        events = recorder.get_routing_events(states[0].state_id)
        assert len(events) == 2

        # All events should share the same routing_group_id (fork group)
        group_ids = {e.routing_group_id for e in events}
        assert len(group_ids) == 1

    def test_fork_without_token_manager_raises_error(self) -> None:
        """Gate fork without token_manager raises RuntimeError for audit integrity."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext
        from elspeth.plugins.results import GateResult, RoutingAction

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        # Register gate and path nodes
        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="splitter",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        path_a_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="path_a",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        path_b_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="path_b",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # Register edges
        edge_a = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=path_a_node.node_id,
            label="path_a",
            mode=RoutingMode.COPY,
        )
        edge_b = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=path_b_node.node_id,
            label="path_b",
            mode=RoutingMode.COPY,
        )

        # Mock gate that forks to multiple paths
        class SplitterGate:
            name = "splitter"
            node_id = gate_node.node_id

            def evaluate(self, row: dict[str, Any], ctx: PluginContext) -> GateResult:
                return GateResult(
                    row=row,
                    action=RoutingAction.fork_to_paths(["path_a", "path_b"]),
                )

        gate = SplitterGate()
        ctx = PluginContext(run_id=run.run_id, config={})

        edge_map: dict[tuple[NodeID, str], str] = {
            (NodeID(gate_node.node_id), "path_a"): edge_a.edge_id,
            (NodeID(gate_node.node_id), "path_b"): edge_b.edge_id,
        }
        executor = GateExecutor(recorder, SpanFactory(), edge_map)

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": 42},
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        # Call without token_manager - should raise RuntimeError
        with pytest.raises(RuntimeError, match="audit integrity would be compromised"):
            executor.execute_gate(
                gate=as_gate(gate),
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
                token_manager=None,  # Explicitly None
            )

        # Verify node_state was completed with FAILED status (not left OPEN)
        states = recorder.get_node_states_for_token(token.token_id)
        assert len(states) == 1
        assert states[0].status == NodeStateStatus.FAILED

        # Verify audit fields are populated (P3 fix completeness)
        state = states[0]
        assert state.duration_ms is not None, "duration_ms must be recorded on failed state"
        assert state.duration_ms >= 0, "duration_ms must be non-negative"

    def test_execute_gate_exception_records_failure(self) -> None:
        """Gate raising exception still records audit state."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext
        from elspeth.plugins.results import GateResult

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="exploding_gate",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        class ExplodingGate:
            name = "exploding_gate"
            node_id = gate_node.node_id

            def evaluate(self, row: dict[str, Any], ctx: PluginContext) -> GateResult:
                raise RuntimeError("gate evaluation failed!")

        gate = ExplodingGate()
        ctx = PluginContext(run_id=run.run_id, config={})
        executor = GateExecutor(recorder, SpanFactory())

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": 42},
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        with pytest.raises(RuntimeError, match="gate evaluation failed"):
            executor.execute_gate(
                gate=as_gate(gate),
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
            )

        # Verify failure was recorded in landscape
        states = recorder.get_node_states_for_token(token.token_id)
        assert len(states) == 1
        state = states[0]
        assert state.status == NodeStateStatus.FAILED
        # NodeStateFailed has duration_ms - narrow type before accessing
        assert isinstance(state, NodeStateFailed)
        assert state.duration_ms is not None

    def test_gate_context_has_state_id_for_call_recording(self) -> None:
        """BUG-RECORDER-01: Gate execution sets state_id on context for external call recording."""
        from elspeth.contracts import CallStatus, CallType, RoutingMode, TokenInfo
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext
        from elspeth.plugins.results import GateResult, RoutingAction

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="api_gate",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        # Register next node and continue edge
        next_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="output",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        continue_edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=next_node.node_id,
            label="continue",
            mode=RoutingMode.MOVE,
        )
        edge_map: dict[tuple[NodeID, str], str] = {(NodeID(gate_node.node_id), "continue"): continue_edge.edge_id}

        # Mock gate that makes external call during evaluation
        class APIGate:
            name = "api_gate"
            node_id = gate_node.node_id

            def evaluate(self, row: dict[str, Any], ctx: PluginContext) -> GateResult:
                # Gate makes external API call to decide routing
                ctx.record_call(
                    call_type=CallType.HTTP,
                    status=CallStatus.SUCCESS,
                    request_data={"url": "https://api.example.com/check", "value": row["value"]},
                    response_data={"decision": "continue"},
                    latency_ms=50.0,
                )
                return GateResult(row=row, action=RoutingAction.continue_())

        gate = APIGate()
        ctx = PluginContext(run_id=run.run_id, config={}, landscape=recorder)
        executor = GateExecutor(recorder, SpanFactory(), edge_map=edge_map)

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": 42},
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        outcome = executor.execute_gate(
            gate=as_gate(gate),
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        # Verify gate succeeded
        assert outcome.result.action.kind == "continue"

        # Verify external call was recorded
        states = recorder.get_node_states_for_token(token.token_id)
        assert len(states) == 1
        state = states[0]

        calls = recorder.get_calls(state.state_id)
        assert len(calls) == 1
        assert calls[0].call_type == CallType.HTTP
        assert calls[0].status == CallStatus.SUCCESS
        assert calls[0].latency_ms == 50.0


class TestConfigGateExecutor:
    """Config-driven gate execution with ExpressionParser."""

    def test_execute_config_gate_continue(self) -> None:
        """Config gate returns continue destination - routing event recorded for audit (AUD-002)."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.config import GateSettings
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")
        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="quality_check",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        # Register next node in pipeline for continue edge
        next_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="next_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # Register continue edge from gate to next node (AUD-002)
        continue_edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=next_node.node_id,
            label="continue",
            mode=RoutingMode.MOVE,
        )
        edge_map: dict[tuple[NodeID, str], str] = {(NodeID(gate_node.node_id), "continue"): continue_edge.edge_id}

        # Config-driven gate that checks confidence
        gate_config = GateSettings(
            name="quality_check",
            condition="row['confidence'] >= 0.85",
            routes={"true": "continue", "false": "review_sink"},
        )

        ctx = PluginContext(run_id=run.run_id, config={})
        executor = GateExecutor(recorder, SpanFactory(), edge_map=edge_map)

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"confidence": 0.95},  # Above threshold
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        outcome = executor.execute_config_gate(
            gate_config=gate_config,
            node_id=gate_node.node_id,
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        # Verify outcome
        assert outcome.result.action.kind == "continue"
        assert outcome.sink_name is None
        assert outcome.child_tokens == []
        assert outcome.updated_token.row_data == {"confidence": 0.95}

        # Verify audit fields populated
        assert outcome.result.input_hash is not None
        assert outcome.result.output_hash is not None
        assert outcome.result.duration_ms is not None

        # Verify node state recorded as completed
        states = recorder.get_node_states_for_token(token.token_id)
        assert len(states) == 1
        assert states[0].status == NodeStateStatus.COMPLETED

        # Verify routing event recorded for continue (AUD-002)
        events = recorder.get_routing_events(states[0].state_id)
        assert len(events) == 1
        assert events[0].edge_id == continue_edge.edge_id

    def test_execute_config_gate_route_to_sink(self) -> None:
        """Config gate routes to sink when condition evaluates to route label."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.config import GateSettings
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="quality_check",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        sink_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="review_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # Register edge for "false" route label
        edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=sink_node.node_id,
            label="false",
            mode=RoutingMode.MOVE,
        )

        gate_config = GateSettings(
            name="quality_check",
            condition="row['confidence'] >= 0.85",
            routes={"true": "continue", "false": "review_sink"},
        )

        edge_map: dict[tuple[NodeID, str], str] = {(NodeID(gate_node.node_id), "false"): edge.edge_id}
        ctx = PluginContext(run_id=run.run_id, config={})
        executor = GateExecutor(recorder, SpanFactory(), edge_map)

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"confidence": 0.5},  # Below threshold
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        outcome = executor.execute_config_gate(
            gate_config=gate_config,
            node_id=gate_node.node_id,
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        # Verify routing to sink
        assert outcome.result.action.kind == "route"
        assert outcome.sink_name == "review_sink"
        assert outcome.child_tokens == []

        # Verify routing event recorded
        states = recorder.get_node_states_for_token(token.token_id)
        events = recorder.get_routing_events(states[0].state_id)
        assert len(events) == 1
        assert events[0].edge_id == edge.edge_id

    def test_execute_config_gate_string_result(self) -> None:
        """Config gate using ternary expression that returns string route labels."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.config import GateSettings
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="priority_router",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        high_sink = recorder.register_node(
            run_id=run.run_id,
            plugin_name="high_priority_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=high_sink.node_id,
            label="high",
            mode=RoutingMode.MOVE,
        )

        # Ternary expression returning string route labels
        gate_config = GateSettings(
            name="priority_router",
            condition="'high' if row['priority'] > 5 else 'low'",
            routes={"high": "high_priority_sink", "low": "continue"},
        )

        edge_map: dict[tuple[NodeID, str], str] = {(NodeID(gate_node.node_id), "high"): edge.edge_id}
        ctx = PluginContext(run_id=run.run_id, config={})
        executor = GateExecutor(recorder, SpanFactory(), edge_map)

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"priority": 8},  # High priority
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        outcome = executor.execute_config_gate(
            gate_config=gate_config,
            node_id=gate_node.node_id,
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        assert outcome.result.action.kind == "route"
        assert outcome.sink_name == "high_priority_sink"

    def test_execute_config_gate_fork(self) -> None:
        """Config gate forks to multiple paths."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.config import GateSettings
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.engine.tokens import TokenManager
        from elspeth.plugins.context import PluginContext

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="parallel_analysis",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        path_a = recorder.register_node(
            run_id=run.run_id,
            plugin_name="path_a",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        path_b = recorder.register_node(
            run_id=run.run_id,
            plugin_name="path_b",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        edge_a = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=path_a.node_id,
            label="path_a",
            mode=RoutingMode.COPY,
        )
        edge_b = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=path_b.node_id,
            label="path_b",
            mode=RoutingMode.COPY,
        )

        gate_config = GateSettings(
            name="parallel_analysis",
            condition="True",  # Always fork
            routes={"true": "fork", "false": "continue"},
            fork_to=["path_a", "path_b"],
        )

        edge_map: dict[tuple[NodeID, str], str] = {
            (NodeID(gate_node.node_id), "path_a"): edge_a.edge_id,
            (NodeID(gate_node.node_id), "path_b"): edge_b.edge_id,
        }
        ctx = PluginContext(run_id=run.run_id, config={})
        executor = GateExecutor(recorder, SpanFactory(), edge_map)
        token_manager = TokenManager(recorder)

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": 42},
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        outcome = executor.execute_config_gate(
            gate_config=gate_config,
            node_id=gate_node.node_id,
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
            token_manager=token_manager,
        )

        # Verify fork
        assert outcome.result.action.kind == "fork_to_paths"
        assert outcome.sink_name is None
        assert len(outcome.child_tokens) == 2

        # Verify child tokens have correct branch names
        branch_names = {t.branch_name for t in outcome.child_tokens}
        assert branch_names == {"path_a", "path_b"}

        # Verify routing events
        states = recorder.get_node_states_for_token(token.token_id)
        events = recorder.get_routing_events(states[0].state_id)
        assert len(events) == 2

    def test_execute_config_gate_fork_without_token_manager_raises_error(self) -> None:
        """Config gate fork without token_manager raises RuntimeError."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.config import GateSettings
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="fork_gate",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        gate_config = GateSettings(
            name="fork_gate",
            condition="True",
            routes={"true": "fork", "false": "continue"},
            fork_to=["path_a", "path_b"],
        )

        ctx = PluginContext(run_id=run.run_id, config={})
        executor = GateExecutor(recorder, SpanFactory())

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": 42},
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        with pytest.raises(RuntimeError, match="audit integrity would be compromised"):
            executor.execute_config_gate(
                gate_config=gate_config,
                node_id=gate_node.node_id,
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
                token_manager=None,
            )

    def test_execute_config_gate_missing_route_label_raises_error(self) -> None:
        """Config gate condition returning unlisted label raises ValueError."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.config import GateSettings
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="broken_gate",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # Gate returns "maybe" but routes only define "true"/"false"
        gate_config = GateSettings(
            name="broken_gate",
            condition="'maybe'",  # Returns string not in routes
            routes={"true": "continue", "false": "error_sink"},
        )

        ctx = PluginContext(run_id=run.run_id, config={})
        executor = GateExecutor(recorder, SpanFactory())

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": 42},
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        with pytest.raises(ValueError, match="which is not in routes"):
            executor.execute_config_gate(
                gate_config=gate_config,
                node_id=gate_node.node_id,
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
            )

        # Verify failure was recorded
        states = recorder.get_node_states_for_token(token.token_id)
        assert len(states) == 1
        assert states[0].status == NodeStateStatus.FAILED

    def test_execute_config_gate_expression_error_records_failure(self) -> None:
        """Config gate expression failure records audit state."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.config import GateSettings
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="error_gate",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # Expression accesses missing field
        gate_config = GateSettings(
            name="error_gate",
            condition="row['nonexistent'] > 0",
            routes={"true": "continue", "false": "continue"},
        )

        ctx = PluginContext(run_id=run.run_id, config={})
        executor = GateExecutor(recorder, SpanFactory())

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": 42},  # No 'nonexistent' field
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        with pytest.raises(KeyError):
            executor.execute_config_gate(
                gate_config=gate_config,
                node_id=gate_node.node_id,
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
            )

        # Verify failure was recorded
        states = recorder.get_node_states_for_token(token.token_id)
        assert len(states) == 1
        assert states[0].status == NodeStateStatus.FAILED

    def test_execute_config_gate_missing_edge_raises_error(self) -> None:
        """Config gate routing to unregistered edge raises MissingEdgeError."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.config import GateSettings
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor, MissingEdgeError
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="routing_gate",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        gate_config = GateSettings(
            name="routing_gate",
            condition="row['value'] < 0",
            routes={"true": "error_sink", "false": "continue"},
        )

        # No edge registered for "true" route
        ctx = PluginContext(run_id=run.run_id, config={})
        executor = GateExecutor(recorder, SpanFactory(), edge_map={})

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"value": -5},  # Will trigger route to error_sink
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        with pytest.raises(MissingEdgeError) as exc_info:
            executor.execute_config_gate(
                gate_config=gate_config,
                node_id=gate_node.node_id,
                token=token,
                ctx=ctx,
                step_in_pipeline=1,
            )

        assert exc_info.value.node_id == gate_node.node_id
        assert exc_info.value.label == "true"

    def test_execute_config_gate_reason_includes_condition(self) -> None:
        """Config gate routing action reason includes condition and result."""
        from elspeth.contracts import TokenInfo
        from elspeth.core.config import GateSettings
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.executors import GateExecutor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.context import PluginContext

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        gate_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="audit_gate",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        # Register next node for continue edge (AUD-002)
        next_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="next_transform",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        continue_edge = recorder.register_edge(
            run_id=run.run_id,
            from_node_id=gate_node.node_id,
            to_node_id=next_node.node_id,
            label="continue",
            mode=RoutingMode.MOVE,
        )
        edge_map: dict[tuple[NodeID, str], str] = {(NodeID(gate_node.node_id), "continue"): continue_edge.edge_id}

        gate_config = GateSettings(
            name="audit_gate",
            condition="row['score'] > 100",
            routes={"true": "continue", "false": "continue"},
        )

        ctx = PluginContext(run_id=run.run_id, config={})
        executor = GateExecutor(recorder, SpanFactory(), edge_map=edge_map)

        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data={"score": 150},
        )
        row = recorder.create_row(
            run_id=run.run_id,
            source_node_id=gate_node.node_id,
            row_index=0,
            data=token.row_data,
            row_id=token.row_id,
        )
        recorder.create_token(row_id=row.row_id, token_id=token.token_id)

        outcome = executor.execute_config_gate(
            gate_config=gate_config,
            node_id=gate_node.node_id,
            token=token,
            ctx=ctx,
            step_in_pipeline=1,
        )

        # Verify reason is recorded for audit trail
        reason = dict(outcome.result.action.reason)
        assert reason["condition"] == "row['score'] > 100"
        assert reason["result"] == "true"
