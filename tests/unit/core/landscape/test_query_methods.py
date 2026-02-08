from __future__ import annotations

from elspeth.contracts import (
    CallStatus,
    CallType,
    NodeType,
    RoutingMode,
)
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
from elspeth.core.landscape.row_data import RowDataResult, RowDataState

_DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _setup(*, run_id: str = "run-1") -> tuple[LandscapeDB, LandscapeRecorder]:
    db = LandscapeDB.in_memory()
    recorder = LandscapeRecorder(db)
    recorder.begin_run(config={}, canonical_version="v1", run_id=run_id)
    recorder.register_node(
        run_id=run_id,
        plugin_name="csv",
        node_type=NodeType.SOURCE,
        plugin_version="1.0",
        config={},
        node_id="source-0",
        schema_config=_DYNAMIC_SCHEMA,
    )
    recorder.register_node(
        run_id=run_id,
        plugin_name="transform",
        node_type=NodeType.TRANSFORM,
        plugin_version="1.0",
        config={},
        node_id="transform-1",
        schema_config=_DYNAMIC_SCHEMA,
    )
    return db, recorder


def _setup_full(*, run_id: str = "run-1"):
    """Build a full environment with nodes, edge, row, token, state."""
    db, recorder = _setup(run_id=run_id)
    recorder.register_edge(run_id, "source-0", "transform-1", "continue", RoutingMode.MOVE, edge_id="edge-1")
    recorder.create_row(run_id, "source-0", 0, {"name": "test"}, row_id="row-1")
    recorder.create_token("row-1", token_id="tok-1")
    recorder.begin_node_state("tok-1", "transform-1", run_id, 0, {"name": "test"}, state_id="state-1")
    return db, recorder


class TestGetRows:
    """Tests for LandscapeRecorder.get_rows -- retrieves rows for a run ordered by row_index."""

    def test_returns_rows_ordered_by_index(self):
        _db, recorder = _setup()
        recorder.create_row("run-1", "source-0", 2, {"c": 3}, row_id="row-c")
        recorder.create_row("run-1", "source-0", 0, {"a": 1}, row_id="row-a")
        recorder.create_row("run-1", "source-0", 1, {"b": 2}, row_id="row-b")

        rows = recorder.get_rows("run-1")

        assert len(rows) == 3
        assert [r.row_id for r in rows] == ["row-a", "row-b", "row-c"]
        assert [r.row_index for r in rows] == [0, 1, 2]

    def test_empty_for_unknown_run(self):
        _, recorder = _setup()

        rows = recorder.get_rows("nonexistent-run")

        assert rows == []

    def test_single_row(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")

        rows = recorder.get_rows("run-1")

        assert len(rows) == 1
        assert rows[0].row_id == "row-1"
        assert rows[0].row_index == 0

    def test_rows_scoped_to_run(self):
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-a")
        recorder.register_node(
            run_id="run-a",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="src-a",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-b")
        recorder.register_node(
            run_id="run-b",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="src-b",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_row("run-a", "src-a", 0, {"v": 1}, row_id="row-a1")
        recorder.create_row("run-b", "src-b", 0, {"v": 2}, row_id="row-b1")

        rows_a = recorder.get_rows("run-a")
        rows_b = recorder.get_rows("run-b")

        assert len(rows_a) == 1
        assert rows_a[0].row_id == "row-a1"
        assert len(rows_b) == 1
        assert rows_b[0].row_id == "row-b1"


class TestGetTokens:
    """Tests for LandscapeRecorder.get_tokens -- retrieves tokens for a row."""

    def test_returns_tokens_for_row(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")
        recorder.create_token("row-1", token_id="tok-1")
        recorder.create_token("row-1", token_id="tok-2")

        tokens = recorder.get_tokens("row-1")

        assert len(tokens) == 2
        token_ids = {t.token_id for t in tokens}
        assert token_ids == {"tok-1", "tok-2"}

    def test_empty_for_unknown_row(self):
        _, recorder = _setup()

        tokens = recorder.get_tokens("nonexistent-row")

        assert tokens == []

    def test_single_token(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")
        recorder.create_token("row-1", token_id="tok-1")

        tokens = recorder.get_tokens("row-1")

        assert len(tokens) == 1
        assert tokens[0].token_id == "tok-1"
        assert tokens[0].row_id == "row-1"

    def test_tokens_scoped_to_row(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"a": 1}, row_id="row-a")
        recorder.create_row("run-1", "source-0", 1, {"b": 2}, row_id="row-b")
        recorder.create_token("row-a", token_id="tok-a")
        recorder.create_token("row-b", token_id="tok-b")

        tokens_a = recorder.get_tokens("row-a")
        tokens_b = recorder.get_tokens("row-b")

        assert len(tokens_a) == 1
        assert tokens_a[0].token_id == "tok-a"
        assert len(tokens_b) == 1
        assert tokens_b[0].token_id == "tok-b"


class TestGetNodeStatesForToken:
    """Tests for LandscapeRecorder.get_node_states_for_token -- states ordered by (step_index, attempt)."""

    def test_returns_states_ordered_by_step_index(self):
        _, recorder = _setup_full()
        # state-1 already exists at step_index=0
        recorder.register_node(
            run_id="run-1",
            plugin_name="transform2",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="transform-2",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.begin_node_state("tok-1", "transform-2", "run-1", 1, {"name": "test"}, state_id="state-2")

        states = recorder.get_node_states_for_token("tok-1")

        assert len(states) == 2
        assert states[0].state_id == "state-1"
        assert states[0].step_index == 0
        assert states[1].state_id == "state-2"
        assert states[1].step_index == 1

    def test_orders_by_attempt_within_step(self):
        _, recorder = _setup_full()
        # state-1 is step_index=0, attempt=0
        # Add a retry at the same step
        recorder.begin_node_state(
            "tok-1",
            "transform-1",
            "run-1",
            0,
            {"name": "test"},
            state_id="state-retry",
            attempt=1,
        )

        states = recorder.get_node_states_for_token("tok-1")

        assert len(states) == 2
        assert states[0].state_id == "state-1"
        assert states[0].attempt == 0
        assert states[1].state_id == "state-retry"
        assert states[1].attempt == 1

    def test_empty_for_unknown_token(self):
        _, recorder = _setup()

        states = recorder.get_node_states_for_token("nonexistent-tok")

        assert states == []

    def test_single_state(self):
        _, recorder = _setup_full()

        states = recorder.get_node_states_for_token("tok-1")

        assert len(states) == 1
        assert states[0].state_id == "state-1"
        assert states[0].token_id == "tok-1"
        assert states[0].node_id == "transform-1"


class TestGetRow:
    """Tests for LandscapeRecorder.get_row -- retrieves a single row by ID."""

    def test_roundtrip(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"field": "value"}, row_id="row-1")

        row = recorder.get_row("row-1")

        assert row is not None
        assert row.row_id == "row-1"
        assert row.run_id == "run-1"
        assert row.source_node_id == "source-0"
        assert row.row_index == 0

    def test_none_for_unknown(self):
        _, recorder = _setup()

        row = recorder.get_row("nonexistent-row")

        assert row is None


class TestGetRowData:
    """Tests for LandscapeRecorder.get_row_data -- retrieves payload data with state information."""

    def test_row_not_found(self):
        _, recorder = _setup()

        result = recorder.get_row_data("nonexistent-row")

        assert isinstance(result, RowDataResult)
        assert result.state == RowDataState.ROW_NOT_FOUND
        assert result.data is None

    def test_never_stored_or_store_not_configured(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")

        result = recorder.get_row_data("row-1")

        # Default setup has no payload store; the row may or may not have a
        # source_data_ref depending on how create_row stores data.
        # Either NEVER_STORED (no ref on row) or STORE_NOT_CONFIGURED (ref but no store)
        # is valid.
        assert result.state in (RowDataState.NEVER_STORED, RowDataState.STORE_NOT_CONFIGURED)
        assert result.data is None


class TestGetToken:
    """Tests for LandscapeRecorder.get_token -- retrieves a single token by ID."""

    def test_roundtrip(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")
        recorder.create_token("row-1", token_id="tok-1")

        token = recorder.get_token("tok-1")

        assert token is not None
        assert token.token_id == "tok-1"
        assert token.row_id == "row-1"

    def test_none_for_unknown(self):
        _, recorder = _setup()

        token = recorder.get_token("nonexistent-tok")

        assert token is None


class TestGetTokenParents:
    """Tests for LandscapeRecorder.get_token_parents -- parent relationships ordered by ordinal."""

    def test_empty_when_no_parents(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")
        recorder.create_token("row-1", token_id="tok-1")

        parents = recorder.get_token_parents("tok-1")

        assert parents == []

    def test_returns_parents_after_fork(self):
        _, recorder = _setup_full()
        # fork_token creates children with parent relationships
        children, _fork_group_id = recorder.fork_token(
            parent_token_id="tok-1",
            row_id="row-1",
            branches=["path-a", "path-b"],
            run_id="run-1",
        )

        # Each child should have tok-1 as parent
        for child in children:
            parents = recorder.get_token_parents(child.token_id)
            assert len(parents) == 1
            assert parents[0].parent_token_id == "tok-1"

    def test_returns_parents_after_coalesce(self):
        _, recorder = _setup_full()
        # Create a second token to coalesce with
        recorder.create_token("row-1", token_id="tok-2")

        merged = recorder.coalesce_tokens(
            parent_token_ids=["tok-1", "tok-2"],
            row_id="row-1",
        )

        parents = recorder.get_token_parents(merged.token_id)

        assert len(parents) == 2
        parent_ids = [p.parent_token_id for p in parents]
        assert "tok-1" in parent_ids
        assert "tok-2" in parent_ids
        # Ordered by ordinal
        assert parents[0].ordinal == 0
        assert parents[1].ordinal == 1

    def test_empty_for_unknown_token(self):
        _, recorder = _setup()

        parents = recorder.get_token_parents("nonexistent-tok")

        assert parents == []


class TestGetRoutingEvents:
    """Tests for LandscapeRecorder.get_routing_events -- events for a state."""

    def test_returns_events_for_state(self):
        _, recorder = _setup_full()
        recorder.record_routing_event(
            state_id="state-1",
            edge_id="edge-1",
            mode=RoutingMode.MOVE,
        )

        events = recorder.get_routing_events("state-1")

        assert len(events) == 1
        assert events[0].state_id == "state-1"
        assert events[0].edge_id == "edge-1"

    def test_events_ordered_by_ordinal(self):
        _, recorder = _setup_full()
        # Register additional infrastructure for second event
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0",
            config={},
            node_id="sink-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_edge("run-1", "transform-1", "sink-0", "route_to_sink", RoutingMode.MOVE, edge_id="edge-2")
        recorder.record_routing_event(
            state_id="state-1",
            edge_id="edge-1",
            mode=RoutingMode.MOVE,
            ordinal=1,
        )
        recorder.record_routing_event(
            state_id="state-1",
            edge_id="edge-2",
            mode=RoutingMode.MOVE,
            ordinal=0,
        )

        events = recorder.get_routing_events("state-1")

        assert len(events) == 2
        assert events[0].ordinal == 0
        assert events[1].ordinal == 1

    def test_empty_for_unknown_state(self):
        _, recorder = _setup()

        events = recorder.get_routing_events("nonexistent-state")

        assert events == []


class TestGetCalls:
    """Tests for LandscapeRecorder.get_calls -- calls for a state ordered by call_index."""

    def test_returns_calls_for_state(self):
        _, recorder = _setup_full()
        recorder.record_call(
            state_id="state-1",
            call_index=0,
            call_type=CallType.LLM,
            status=CallStatus.SUCCESS,
            request_data={"model": "gpt-4", "prompt": "Hello"},
            response_data={"completion": "Hi"},
            latency_ms=100.0,
        )

        calls = recorder.get_calls("state-1")

        assert len(calls) == 1
        assert calls[0].state_id == "state-1"
        assert calls[0].call_index == 0
        assert calls[0].status == CallStatus.SUCCESS

    def test_calls_ordered_by_call_index(self):
        _, recorder = _setup_full()
        recorder.record_call(
            state_id="state-1",
            call_index=1,
            call_type=CallType.LLM,
            status=CallStatus.SUCCESS,
            request_data={"prompt": "second"},
            response_data={"out": "b"},
            latency_ms=50.0,
        )
        recorder.record_call(
            state_id="state-1",
            call_index=0,
            call_type=CallType.HTTP,
            status=CallStatus.SUCCESS,
            request_data={"url": "https://example.com"},
            response_data={"body": "ok"},
            latency_ms=75.0,
        )

        calls = recorder.get_calls("state-1")

        assert len(calls) == 2
        assert calls[0].call_index == 0
        assert calls[1].call_index == 1

    def test_empty_for_unknown_state(self):
        _, recorder = _setup()

        calls = recorder.get_calls("nonexistent-state")

        assert calls == []


class TestGetRoutingEventsForStates:
    """Tests for LandscapeRecorder.get_routing_events_for_states -- batch query for multiple state IDs."""

    def test_batch_query_returns_events(self):
        _, recorder = _setup_full()
        # Create a second state
        recorder.create_row("run-1", "source-0", 1, {"name": "test2"}, row_id="row-2")
        recorder.create_token("row-2", token_id="tok-2")
        recorder.begin_node_state("tok-2", "transform-1", "run-1", 0, {"name": "test2"}, state_id="state-2")
        recorder.record_routing_event(
            state_id="state-1",
            edge_id="edge-1",
            mode=RoutingMode.MOVE,
        )
        recorder.record_routing_event(
            state_id="state-2",
            edge_id="edge-1",
            mode=RoutingMode.MOVE,
        )

        events = recorder.get_routing_events_for_states(["state-1", "state-2"])

        assert len(events) == 2
        state_ids = {e.state_id for e in events}
        assert state_ids == {"state-1", "state-2"}

    def test_empty_input_returns_empty(self):
        _, recorder = _setup()

        events = recorder.get_routing_events_for_states([])

        assert events == []

    def test_single_state_id(self):
        _, recorder = _setup_full()
        recorder.record_routing_event(
            state_id="state-1",
            edge_id="edge-1",
            mode=RoutingMode.MOVE,
        )

        events = recorder.get_routing_events_for_states(["state-1"])

        assert len(events) == 1
        assert events[0].state_id == "state-1"


class TestGetCallsForStates:
    """Tests for LandscapeRecorder.get_calls_for_states -- batch query for multiple state IDs."""

    def test_batch_query_returns_calls(self):
        _, recorder = _setup_full()
        recorder.create_row("run-1", "source-0", 1, {"name": "test2"}, row_id="row-2")
        recorder.create_token("row-2", token_id="tok-2")
        recorder.begin_node_state("tok-2", "transform-1", "run-1", 0, {"name": "test2"}, state_id="state-2")
        recorder.record_call(
            state_id="state-1",
            call_index=0,
            call_type=CallType.LLM,
            status=CallStatus.SUCCESS,
            request_data={"prompt": "a"},
            response_data={"out": "x"},
            latency_ms=50.0,
        )
        recorder.record_call(
            state_id="state-2",
            call_index=0,
            call_type=CallType.HTTP,
            status=CallStatus.SUCCESS,
            request_data={"url": "https://example.com"},
            response_data={"body": "ok"},
            latency_ms=75.0,
        )

        calls = recorder.get_calls_for_states(["state-1", "state-2"])

        assert len(calls) == 2
        state_ids = {c.state_id for c in calls}
        assert state_ids == {"state-1", "state-2"}

    def test_empty_input_returns_empty(self):
        _, recorder = _setup()

        calls = recorder.get_calls_for_states([])

        assert calls == []

    def test_single_state_id(self):
        _, recorder = _setup_full()
        recorder.record_call(
            state_id="state-1",
            call_index=0,
            call_type=CallType.LLM,
            status=CallStatus.SUCCESS,
            request_data={"prompt": "test"},
            response_data={"out": "ok"},
            latency_ms=100.0,
        )

        calls = recorder.get_calls_for_states(["state-1"])

        assert len(calls) == 1
        assert calls[0].state_id == "state-1"


class TestGetAllTokensForRun:
    """Tests for LandscapeRecorder.get_all_tokens_for_run -- all tokens across rows via JOIN."""

    def test_returns_all_tokens_across_rows(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"a": 1}, row_id="row-1")
        recorder.create_row("run-1", "source-0", 1, {"b": 2}, row_id="row-2")
        recorder.create_token("row-1", token_id="tok-1")
        recorder.create_token("row-1", token_id="tok-2")
        recorder.create_token("row-2", token_id="tok-3")

        tokens = recorder.get_all_tokens_for_run("run-1")

        assert len(tokens) == 3
        token_ids = {t.token_id for t in tokens}
        assert token_ids == {"tok-1", "tok-2", "tok-3"}

    def test_empty_for_unknown_run(self):
        _, recorder = _setup()

        tokens = recorder.get_all_tokens_for_run("nonexistent-run")

        assert tokens == []

    def test_scoped_to_run(self):
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-a")
        recorder.register_node(
            run_id="run-a",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="src-a",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-b")
        recorder.register_node(
            run_id="run-b",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="src-b",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_row("run-a", "src-a", 0, {"v": 1}, row_id="row-a1")
        recorder.create_token("row-a1", token_id="tok-a1")
        recorder.create_row("run-b", "src-b", 0, {"v": 2}, row_id="row-b1")
        recorder.create_token("row-b1", token_id="tok-b1")

        tokens_a = recorder.get_all_tokens_for_run("run-a")
        tokens_b = recorder.get_all_tokens_for_run("run-b")

        assert len(tokens_a) == 1
        assert tokens_a[0].token_id == "tok-a1"
        assert len(tokens_b) == 1
        assert tokens_b[0].token_id == "tok-b1"


class TestGetAllNodeStatesForRun:
    """Tests for LandscapeRecorder.get_all_node_states_for_run -- uses denormalized run_id."""

    def test_returns_all_states(self):
        _, recorder = _setup_full()
        # state-1 already exists
        recorder.create_row("run-1", "source-0", 1, {"b": 2}, row_id="row-2")
        recorder.create_token("row-2", token_id="tok-2")
        recorder.begin_node_state("tok-2", "transform-1", "run-1", 0, {"b": 2}, state_id="state-2")

        states = recorder.get_all_node_states_for_run("run-1")

        assert len(states) == 2
        state_ids = {s.state_id for s in states}
        assert state_ids == {"state-1", "state-2"}

    def test_empty_for_unknown_run(self):
        _, recorder = _setup()

        states = recorder.get_all_node_states_for_run("nonexistent-run")

        assert states == []

    def test_scoped_to_run(self):
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        recorder.begin_run(config={}, canonical_version="v1", run_id="run-a")
        recorder.register_node(
            run_id="run-a",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="src-a",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-a",
            plugin_name="tx",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="tx-a",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_row("run-a", "src-a", 0, {"v": 1}, row_id="row-a1")
        recorder.create_token("row-a1", token_id="tok-a1")
        recorder.begin_node_state("tok-a1", "tx-a", "run-a", 0, {"v": 1}, state_id="state-a1")

        recorder.begin_run(config={}, canonical_version="v1", run_id="run-b")
        recorder.register_node(
            run_id="run-b",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="src-b",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-b",
            plugin_name="tx",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="tx-b",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.create_row("run-b", "src-b", 0, {"v": 2}, row_id="row-b1")
        recorder.create_token("row-b1", token_id="tok-b1")
        recorder.begin_node_state("tok-b1", "tx-b", "run-b", 0, {"v": 2}, state_id="state-b1")

        states_a = recorder.get_all_node_states_for_run("run-a")
        states_b = recorder.get_all_node_states_for_run("run-b")

        assert len(states_a) == 1
        assert states_a[0].state_id == "state-a1"
        assert len(states_b) == 1
        assert states_b[0].state_id == "state-b1"


class TestGetAllRoutingEventsForRun:
    """Tests for LandscapeRecorder.get_all_routing_events_for_run -- batch via JOIN through node_states."""

    def test_returns_all_events(self):
        _, recorder = _setup_full()
        recorder.create_row("run-1", "source-0", 1, {"b": 2}, row_id="row-2")
        recorder.create_token("row-2", token_id="tok-2")
        recorder.begin_node_state("tok-2", "transform-1", "run-1", 0, {"b": 2}, state_id="state-2")
        recorder.record_routing_event(
            state_id="state-1",
            edge_id="edge-1",
            mode=RoutingMode.MOVE,
        )
        recorder.record_routing_event(
            state_id="state-2",
            edge_id="edge-1",
            mode=RoutingMode.MOVE,
        )

        events = recorder.get_all_routing_events_for_run("run-1")

        assert len(events) == 2
        state_ids = {e.state_id for e in events}
        assert state_ids == {"state-1", "state-2"}

    def test_empty_for_unknown_run(self):
        _, recorder = _setup()

        events = recorder.get_all_routing_events_for_run("nonexistent-run")

        assert events == []

    def test_empty_when_no_events_recorded(self):
        _, recorder = _setup_full()

        events = recorder.get_all_routing_events_for_run("run-1")

        assert events == []


class TestGetAllCallsForRun:
    """Tests for LandscapeRecorder.get_all_calls_for_run -- state-parented calls via JOIN."""

    def test_returns_all_calls(self):
        _, recorder = _setup_full()
        recorder.create_row("run-1", "source-0", 1, {"b": 2}, row_id="row-2")
        recorder.create_token("row-2", token_id="tok-2")
        recorder.begin_node_state("tok-2", "transform-1", "run-1", 0, {"b": 2}, state_id="state-2")
        recorder.record_call(
            state_id="state-1",
            call_index=0,
            call_type=CallType.LLM,
            status=CallStatus.SUCCESS,
            request_data={"prompt": "a"},
            response_data={"out": "x"},
            latency_ms=50.0,
        )
        recorder.record_call(
            state_id="state-2",
            call_index=0,
            call_type=CallType.HTTP,
            status=CallStatus.SUCCESS,
            request_data={"url": "https://example.com"},
            response_data={"body": "ok"},
            latency_ms=75.0,
        )

        calls = recorder.get_all_calls_for_run("run-1")

        assert len(calls) == 2
        state_ids = {c.state_id for c in calls}
        assert state_ids == {"state-1", "state-2"}

    def test_empty_for_unknown_run(self):
        _, recorder = _setup()

        calls = recorder.get_all_calls_for_run("nonexistent-run")

        assert calls == []

    def test_empty_when_no_calls_recorded(self):
        _, recorder = _setup_full()

        calls = recorder.get_all_calls_for_run("run-1")

        assert calls == []


class TestGetAllTokenParentsForRun:
    """Tests for LandscapeRecorder.get_all_token_parents_for_run -- batch via JOIN through tokens and rows."""

    def test_returns_all_parent_relationships_from_fork(self):
        _, recorder = _setup_full()
        children, _ = recorder.fork_token(
            parent_token_id="tok-1",
            row_id="row-1",
            branches=["path-a", "path-b"],
            run_id="run-1",
        )

        parents = recorder.get_all_token_parents_for_run("run-1")

        assert len(parents) == 2
        child_ids = {p.token_id for p in parents}
        assert child_ids == {children[0].token_id, children[1].token_id}
        for p in parents:
            assert p.parent_token_id == "tok-1"

    def test_empty_for_unknown_run(self):
        _, recorder = _setup()

        parents = recorder.get_all_token_parents_for_run("nonexistent-run")

        assert parents == []

    def test_empty_when_no_forks(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")
        recorder.create_token("row-1", token_id="tok-1")

        parents = recorder.get_all_token_parents_for_run("run-1")

        assert parents == []

    def test_returns_parents_from_coalesce(self):
        _, recorder = _setup_full()
        recorder.create_token("row-1", token_id="tok-2")

        merged = recorder.coalesce_tokens(
            parent_token_ids=["tok-1", "tok-2"],
            row_id="row-1",
        )

        parents = recorder.get_all_token_parents_for_run("run-1")

        assert len(parents) == 2
        parent_token_ids = {p.parent_token_id for p in parents}
        assert parent_token_ids == {"tok-1", "tok-2"}
        for p in parents:
            assert p.token_id == merged.token_id


class TestExplainRow:
    """Tests for LandscapeRecorder.explain_row -- RowLineage with graceful payload degradation."""

    def test_returns_row_lineage(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"field": "value"}, row_id="row-1")

        lineage = recorder.explain_row("run-1", "row-1")

        assert lineage is not None
        assert lineage.row_id == "row-1"
        assert lineage.run_id == "run-1"
        assert lineage.source_node_id == "source-0"
        assert lineage.row_index == 0

    def test_none_for_unknown_row(self):
        _, recorder = _setup()

        lineage = recorder.explain_row("run-1", "nonexistent-row")

        assert lineage is None

    def test_none_for_wrong_run_id(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")

        lineage = recorder.explain_row("wrong-run", "row-1")

        assert lineage is None

    def test_payload_available_false_when_no_payload_store(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")

        lineage = recorder.explain_row("run-1", "row-1")

        assert lineage is not None
        assert lineage.payload_available is False

    def test_source_data_hash_present(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"key": "val"}, row_id="row-1")

        lineage = recorder.explain_row("run-1", "row-1")

        assert lineage is not None
        assert lineage.source_data_hash is not None
        assert isinstance(lineage.source_data_hash, str)
        assert len(lineage.source_data_hash) > 0

    def test_created_at_present(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")

        lineage = recorder.explain_row("run-1", "row-1")

        assert lineage is not None
        assert lineage.created_at is not None

    def test_source_data_none_without_payload_store(self):
        _, recorder = _setup()
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")

        lineage = recorder.explain_row("run-1", "row-1")

        assert lineage is not None
        assert lineage.source_data is None


class TestRoutingEventsOrderedByExecution:
    """Verify batch routing event queries return execution order, not state_id order.

    Regression test for elspeth-rapid-11eh: the N+1 query refactor (ech8)
    introduced ordering by state_id (UUID4 hex — random) instead of
    execution order (step_index, attempt).
    """

    def _setup_three_states(self):
        """Create 3 node states with state_ids that sort opposite to execution order.

        State IDs are chosen so that lexicographic sort (zzz > bbb > aaa)
        is the *reverse* of execution order (step=0/att=0, step=0/att=1, step=1/att=0).
        If the query still sorts by state_id, the test will fail.
        """
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-1")
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="t1",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="transform-1",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="t2",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="transform-2",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_edge("run-1", "source-0", "transform-1", "continue", RoutingMode.MOVE, edge_id="edge-1")
        recorder.register_edge("run-1", "transform-1", "transform-2", "continue", RoutingMode.MOVE, edge_id="edge-2")
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")
        recorder.create_token("row-1", token_id="tok-1")

        # State IDs chosen to sort OPPOSITE to execution order:
        # zzz > bbb > aaa lexicographically, but execution order is aaa, bbb, zzz
        # step=0, attempt=0 → state_id="zzz..." (sorts LAST lexicographically)
        recorder.begin_node_state("tok-1", "transform-1", "run-1", 0, {"x": 1}, state_id="zzz-state-first-exec")
        # step=0, attempt=1 (retry) → state_id="bbb..." (sorts MIDDLE)
        recorder.begin_node_state("tok-1", "transform-1", "run-1", 0, {"x": 1}, state_id="bbb-state-retry", attempt=1)
        # step=1, attempt=0 → state_id="aaa..." (sorts FIRST lexicographically)
        recorder.begin_node_state("tok-1", "transform-2", "run-1", 1, {"x": 1}, state_id="aaa-state-second-step")

        return recorder

    def test_routing_events_for_states_ordered_by_step_index_and_attempt(self):
        recorder = self._setup_three_states()
        state_ids = ["zzz-state-first-exec", "bbb-state-retry", "aaa-state-second-step"]
        for sid in state_ids:
            recorder.record_routing_event(state_id=sid, edge_id="edge-1", mode=RoutingMode.MOVE)

        events = recorder.get_routing_events_for_states(state_ids)

        assert len(events) == 3
        # Execution order: step=0/att=0, step=0/att=1, step=1/att=0
        assert events[0].state_id == "zzz-state-first-exec"
        assert events[1].state_id == "bbb-state-retry"
        assert events[2].state_id == "aaa-state-second-step"

    def test_all_routing_events_for_run_ordered_by_step_index_and_attempt(self):
        recorder = self._setup_three_states()
        state_ids = ["zzz-state-first-exec", "bbb-state-retry", "aaa-state-second-step"]
        for sid in state_ids:
            recorder.record_routing_event(state_id=sid, edge_id="edge-1", mode=RoutingMode.MOVE)

        events = recorder.get_all_routing_events_for_run("run-1")

        assert len(events) == 3
        assert events[0].state_id == "zzz-state-first-exec"
        assert events[1].state_id == "bbb-state-retry"
        assert events[2].state_id == "aaa-state-second-step"


class TestCallsOrderedByExecution:
    """Verify batch call queries return execution order, not state_id order.

    Regression test for elspeth-rapid-11eh: same root cause as above.
    """

    def _setup_three_states(self):
        """Create 3 node states with state_ids that sort opposite to execution order."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-1")
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            node_id="source-0",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="t1",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="transform-1",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="t2",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            node_id="transform-2",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_edge("run-1", "source-0", "transform-1", "continue", RoutingMode.MOVE, edge_id="edge-1")
        recorder.register_edge("run-1", "transform-1", "transform-2", "continue", RoutingMode.MOVE, edge_id="edge-2")
        recorder.create_row("run-1", "source-0", 0, {"x": 1}, row_id="row-1")
        recorder.create_token("row-1", token_id="tok-1")

        # Same strategy: state_ids sort opposite to execution order
        recorder.begin_node_state("tok-1", "transform-1", "run-1", 0, {"x": 1}, state_id="zzz-state-first-exec")
        recorder.begin_node_state("tok-1", "transform-1", "run-1", 0, {"x": 1}, state_id="bbb-state-retry", attempt=1)
        recorder.begin_node_state("tok-1", "transform-2", "run-1", 1, {"x": 1}, state_id="aaa-state-second-step")

        return recorder

    def test_calls_for_states_ordered_by_step_index_and_attempt(self):
        recorder = self._setup_three_states()
        state_ids = ["zzz-state-first-exec", "bbb-state-retry", "aaa-state-second-step"]
        for i, sid in enumerate(state_ids):
            recorder.record_call(
                state_id=sid,
                call_index=0,
                call_type=CallType.LLM,
                status=CallStatus.SUCCESS,
                request_data={"prompt": f"call-{i}"},
                response_data={"out": f"resp-{i}"},
                latency_ms=50.0,
            )

        calls = recorder.get_calls_for_states(state_ids)

        assert len(calls) == 3
        # Execution order: step=0/att=0, step=0/att=1, step=1/att=0
        assert calls[0].state_id == "zzz-state-first-exec"
        assert calls[1].state_id == "bbb-state-retry"
        assert calls[2].state_id == "aaa-state-second-step"

    def test_all_calls_for_run_ordered_by_step_index_and_attempt(self):
        recorder = self._setup_three_states()
        state_ids = ["zzz-state-first-exec", "bbb-state-retry", "aaa-state-second-step"]
        for i, sid in enumerate(state_ids):
            recorder.record_call(
                state_id=sid,
                call_index=0,
                call_type=CallType.LLM,
                status=CallStatus.SUCCESS,
                request_data={"prompt": f"call-{i}"},
                response_data={"out": f"resp-{i}"},
                latency_ms=50.0,
            )

        calls = recorder.get_all_calls_for_run("run-1")

        assert len(calls) == 3
        assert calls[0].state_id == "zzz-state-first-exec"
        assert calls[1].state_id == "bbb-state-retry"
        assert calls[2].state_id == "aaa-state-second-step"
