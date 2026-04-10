# tests/core/landscape/test_recorder_routing_events.py
"""Tests for RecorderFactory routing event operations."""

from __future__ import annotations

import tempfile
from pathlib import Path

from elspeth.contracts import NodeType, RoutingMode, RoutingSpec
from elspeth.contracts.errors import ConfigGateReason
from elspeth.contracts.schema import SchemaConfig

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


class TestRecorderFactoryRouting:
    """Routing event recording (gate decisions)."""

    def test_record_routing_event(self) -> None:
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.factory import RecorderFactory

        db = LandscapeDB.in_memory()
        factory = RecorderFactory(db)
        run = factory.run_lifecycle.begin_run(config={}, canonical_version="v1")

        source = factory.data_flow.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        gate = factory.data_flow.register_node(
            run_id=run.run_id,
            plugin_name="gate",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        sink = factory.data_flow.register_node(
            run_id=run.run_id,
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        edge = factory.data_flow.register_edge(
            run_id=run.run_id,
            from_node_id=gate.node_id,
            to_node_id=sink.node_id,
            label="high_value",
            mode=RoutingMode.MOVE,
        )

        row = factory.data_flow.create_row(
            run_id=run.run_id,
            source_node_id=source.node_id,
            row_index=0,
            data={},
        )
        token = factory.data_flow.create_token(row_id=row.row_id)
        state = factory.execution.begin_node_state(
            token_id=token.token_id,
            node_id=gate.node_id,
            run_id=run.run_id,
            step_index=0,
            input_data={},
        )

        event = factory.execution.record_routing_event(
            state_id=state.state_id,
            edge_id=edge.edge_id,
            mode=RoutingMode.MOVE,
            reason={"condition": "value > 1000", "result": "true"},
        )

        assert event.event_id is not None
        assert event.routing_group_id is not None  # Auto-generated
        assert event.edge_id == edge.edge_id
        assert event.mode == "move"

    def test_record_multiple_routing_events(self) -> None:
        """Test recording fork to multiple destinations."""
        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.factory import RecorderFactory

        db = LandscapeDB.in_memory()
        factory = RecorderFactory(db)
        run = factory.run_lifecycle.begin_run(config={}, canonical_version="v1")

        gate = factory.data_flow.register_node(
            run_id=run.run_id,
            plugin_name="gate",
            node_type=NodeType.GATE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        sink_a = factory.data_flow.register_node(
            run_id=run.run_id,
            plugin_name="sink_a",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        sink_b = factory.data_flow.register_node(
            run_id=run.run_id,
            plugin_name="sink_b",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        edge_a = factory.data_flow.register_edge(
            run_id=run.run_id,
            from_node_id=gate.node_id,
            to_node_id=sink_a.node_id,
            label="path_a",
            mode=RoutingMode.COPY,
        )
        edge_b = factory.data_flow.register_edge(
            run_id=run.run_id,
            from_node_id=gate.node_id,
            to_node_id=sink_b.node_id,
            label="path_b",
            mode=RoutingMode.COPY,
        )

        row = factory.data_flow.create_row(
            run_id=run.run_id,
            source_node_id=gate.node_id,
            row_index=0,
            data={},
        )
        token = factory.data_flow.create_token(row_id=row.row_id)
        state = factory.execution.begin_node_state(
            token_id=token.token_id,
            node_id=gate.node_id,
            run_id=run.run_id,
            step_index=0,
            input_data={},
        )

        # Fork to both paths using batch method
        events = factory.execution.record_routing_events(
            state_id=state.state_id,
            routes=[
                RoutingSpec(edge_id=edge_a.edge_id, mode=RoutingMode.COPY),
                RoutingSpec(edge_id=edge_b.edge_id, mode=RoutingMode.COPY),
            ],
            reason={"condition": "fork_to_paths", "result": "path_a,path_b"},
        )

        assert len(events) == 2
        # All events share the same routing_group_id
        assert events[0].routing_group_id == events[1].routing_group_id
        assert events[0].ordinal == 0
        assert events[1].ordinal == 1

    def test_routing_event_stores_reason_payload_single_route(self) -> None:
        """Test that single routing event stores reason payload."""
        import json

        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.factory import RecorderFactory
        from elspeth.core.payload_store import FilesystemPayloadStore

        db = LandscapeDB.in_memory()
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload_store = FilesystemPayloadStore(Path(tmp_dir))
            factory = RecorderFactory(db, payload_store=payload_store)
            run = factory.run_lifecycle.begin_run(config={}, canonical_version="v1")

            source = factory.data_flow.register_node(
                run_id=run.run_id,
                plugin_name="source",
                node_type=NodeType.SOURCE,
                plugin_version="1.0",
                config={},
                schema_config=DYNAMIC_SCHEMA,
            )
            gate = factory.data_flow.register_node(
                run_id=run.run_id,
                plugin_name="gate",
                node_type=NodeType.GATE,
                plugin_version="1.0",
                config={},
                schema_config=DYNAMIC_SCHEMA,
            )
            sink = factory.data_flow.register_node(
                run_id=run.run_id,
                plugin_name="sink",
                node_type=NodeType.SINK,
                plugin_version="1.0",
                config={},
                schema_config=DYNAMIC_SCHEMA,
            )
            edge = factory.data_flow.register_edge(
                run_id=run.run_id,
                from_node_id=gate.node_id,
                to_node_id=sink.node_id,
                label="high_value",
                mode=RoutingMode.MOVE,
            )

            row = factory.data_flow.create_row(
                run_id=run.run_id,
                source_node_id=source.node_id,
                row_index=0,
                data={},
            )
            token = factory.data_flow.create_token(row_id=row.row_id)
            state = factory.execution.begin_node_state(
                token_id=token.token_id,
                node_id=gate.node_id,
                run_id=run.run_id,
                step_index=0,
                input_data={},
            )

            reason: ConfigGateReason = {"condition": "value > 1000", "result": "true"}
            event = factory.execution.record_routing_event(
                state_id=state.state_id,
                edge_id=edge.edge_id,
                mode=RoutingMode.MOVE,
                reason=reason,
            )

            # Verify reason payload was stored
            assert event.reason_ref is not None, "reason_ref should be set when reason is provided"
            assert event.reason_hash is not None, "reason_hash should be computed from reason"

            # Verify we can retrieve the payload
            retrieved = payload_store.retrieve(event.reason_ref)
            retrieved_reason = json.loads(retrieved.decode("utf-8"))
            assert retrieved_reason == reason

    def test_routing_events_stores_reason_payload_multi_route(self) -> None:
        """Test that multi-route events store shared reason payload."""
        import json

        from elspeth.core.landscape.database import LandscapeDB
        from elspeth.core.landscape.factory import RecorderFactory
        from elspeth.core.payload_store import FilesystemPayloadStore

        db = LandscapeDB.in_memory()
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload_store = FilesystemPayloadStore(Path(tmp_dir))
            factory = RecorderFactory(db, payload_store=payload_store)
            run = factory.run_lifecycle.begin_run(config={}, canonical_version="v1")

            gate = factory.data_flow.register_node(
                run_id=run.run_id,
                plugin_name="gate",
                node_type=NodeType.GATE,
                plugin_version="1.0",
                config={},
                schema_config=DYNAMIC_SCHEMA,
            )
            sink_a = factory.data_flow.register_node(
                run_id=run.run_id,
                plugin_name="sink_a",
                node_type=NodeType.SINK,
                plugin_version="1.0",
                config={},
                schema_config=DYNAMIC_SCHEMA,
            )
            sink_b = factory.data_flow.register_node(
                run_id=run.run_id,
                plugin_name="sink_b",
                node_type=NodeType.SINK,
                plugin_version="1.0",
                config={},
                schema_config=DYNAMIC_SCHEMA,
            )
            edge_a = factory.data_flow.register_edge(
                run_id=run.run_id,
                from_node_id=gate.node_id,
                to_node_id=sink_a.node_id,
                label="path_a",
                mode=RoutingMode.COPY,
            )
            edge_b = factory.data_flow.register_edge(
                run_id=run.run_id,
                from_node_id=gate.node_id,
                to_node_id=sink_b.node_id,
                label="path_b",
                mode=RoutingMode.COPY,
            )

            row = factory.data_flow.create_row(
                run_id=run.run_id,
                source_node_id=gate.node_id,
                row_index=0,
                data={},
            )
            token = factory.data_flow.create_token(row_id=row.row_id)
            state = factory.execution.begin_node_state(
                token_id=token.token_id,
                node_id=gate.node_id,
                run_id=run.run_id,
                step_index=0,
                input_data={},
            )

            reason: ConfigGateReason = {"condition": "fork_to_paths", "result": "path_a,path_b"}
            events = factory.execution.record_routing_events(
                state_id=state.state_id,
                routes=[
                    RoutingSpec(edge_id=edge_a.edge_id, mode=RoutingMode.COPY),
                    RoutingSpec(edge_id=edge_b.edge_id, mode=RoutingMode.COPY),
                ],
                reason=reason,
            )

            # Both events should reference the same payload
            assert len(events) == 2
            assert events[0].reason_ref is not None, "reason_ref should be set when reason is provided"
            assert events[1].reason_ref is not None, "reason_ref should be set when reason is provided"
            assert events[0].reason_ref == events[1].reason_ref, "All events should share same reason payload"
            assert events[0].reason_hash == events[1].reason_hash, "All events should share same reason hash"

            # Verify we can retrieve the shared payload
            retrieved = payload_store.retrieve(events[0].reason_ref)
            retrieved_reason = json.loads(retrieved.decode("utf-8"))
            assert retrieved_reason == reason
