# tests/mcp/test_mcp_divert.py
"""Tests for DIVERT edge rendering in MCP tools (DAG structure + explain_token)."""

from __future__ import annotations

from elspeth.contracts import NodeStateStatus, NodeType, RoutingMode, RowOutcome
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.mcp.server import LandscapeAnalyzer

DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _make_analyzer_with_divert_edge() -> tuple[LandscapeAnalyzer, str]:
    """Create analyzer with a DAG containing one normal edge and one DIVERT edge."""
    db = LandscapeDB.in_memory()
    analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
    analyzer._db = db
    analyzer._recorder = LandscapeRecorder(db)

    run = analyzer._recorder.begin_run(config={}, canonical_version="v1")

    source = analyzer._recorder.register_node(
        run_id=run.run_id,
        plugin_name="csv_source",
        node_type=NodeType.SOURCE,
        plugin_version="1.0",
        config={},
        schema_config=DYNAMIC_SCHEMA,
    )
    transform = analyzer._recorder.register_node(
        run_id=run.run_id,
        plugin_name="llm_transform",
        node_type=NodeType.TRANSFORM,
        plugin_version="1.0",
        config={},
        schema_config=DYNAMIC_SCHEMA,
    )
    sink = analyzer._recorder.register_node(
        run_id=run.run_id,
        plugin_name="csv_sink",
        node_type=NodeType.SINK,
        plugin_version="1.0",
        config={},
        schema_config=DYNAMIC_SCHEMA,
    )
    error_sink = analyzer._recorder.register_node(
        run_id=run.run_id,
        plugin_name="error_sink",
        node_type=NodeType.SINK,
        plugin_version="1.0",
        config={},
        schema_config=DYNAMIC_SCHEMA,
    )

    # Normal edge: source -> transform
    analyzer._recorder.register_edge(
        run_id=run.run_id,
        from_node_id=source.node_id,
        to_node_id=transform.node_id,
        label="continue",
        mode=RoutingMode.MOVE,
    )
    # Normal edge: transform -> sink
    analyzer._recorder.register_edge(
        run_id=run.run_id,
        from_node_id=transform.node_id,
        to_node_id=sink.node_id,
        label="continue",
        mode=RoutingMode.MOVE,
    )
    # DIVERT edge: transform -> error_sink
    analyzer._recorder.register_edge(
        run_id=run.run_id,
        from_node_id=transform.node_id,
        to_node_id=error_sink.node_id,
        label="__error_1__",
        mode=RoutingMode.DIVERT,
    )

    return analyzer, run.run_id


class TestDivertMermaidRendering:
    """Tests for DIVERT edge rendering in Mermaid diagrams."""

    def test_divert_edge_uses_dashed_arrow(self) -> None:
        """DIVERT edges render with -.-> syntax in Mermaid output."""
        analyzer, run_id = _make_analyzer_with_divert_edge()
        result = analyzer.get_dag_structure(run_id)

        mermaid = result["mermaid"]
        assert "-.->" in mermaid, f"Expected dashed arrow in mermaid:\n{mermaid}"

    def test_normal_edges_use_solid_arrow(self) -> None:
        """Normal continue edges still use --> syntax."""
        analyzer, run_id = _make_analyzer_with_divert_edge()
        result = analyzer.get_dag_structure(run_id)

        mermaid = result["mermaid"]
        assert "-->" in mermaid, f"Expected solid arrow in mermaid:\n{mermaid}"

    def test_divert_edge_includes_label(self) -> None:
        """DIVERT dashed arrow includes the edge label."""
        analyzer, run_id = _make_analyzer_with_divert_edge()
        result = analyzer.get_dag_structure(run_id)

        mermaid = result["mermaid"]
        assert "-.->|__error_1__|" in mermaid, f"Expected labeled dashed arrow:\n{mermaid}"


class TestDivertEdgeListFlowType:
    """Tests for flow_type field in edge list."""

    def test_divert_edge_has_divert_flow_type(self) -> None:
        """DIVERT edge includes flow_type='divert' in edge list."""
        analyzer, run_id = _make_analyzer_with_divert_edge()
        result = analyzer.get_dag_structure(run_id)

        divert_edges = [e for e in result["edges"] if e["flow_type"] == "divert"]
        assert len(divert_edges) == 1
        assert divert_edges[0]["label"] == "__error_1__"
        assert divert_edges[0]["mode"] == "divert"

    def test_normal_edge_has_normal_flow_type(self) -> None:
        """Normal edges include flow_type='normal' in edge list."""
        analyzer, run_id = _make_analyzer_with_divert_edge()
        result = analyzer.get_dag_structure(run_id)

        normal_edges = [e for e in result["edges"] if e["flow_type"] == "normal"]
        assert len(normal_edges) == 2  # source->transform + transform->sink

    def test_mode_field_still_present(self) -> None:
        """Edge list entries still include the mode field."""
        analyzer, run_id = _make_analyzer_with_divert_edge()
        result = analyzer.get_dag_structure(run_id)

        for edge in result["edges"]:
            assert "mode" in edge, f"Missing mode field in edge: {edge}"


def _make_analyzer_with_token_lineage(*, diverted: bool, quarantine: bool = False) -> tuple[LandscapeAnalyzer, str, str]:
    """Create analyzer with a complete token lineage (row → token → states → outcome).

    Args:
        diverted: If True, create a DIVERT routing event to error/quarantine sink.
        quarantine: If True and diverted, use __quarantine__ label instead of __error_1__.

    Returns:
        (analyzer, run_id, token_id) tuple.
    """
    db = LandscapeDB.in_memory()
    analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
    analyzer._db = db
    analyzer._recorder = LandscapeRecorder(db)
    rec = analyzer._recorder

    run = rec.begin_run(config={}, canonical_version="v1")

    source = rec.register_node(
        run_id=run.run_id,
        plugin_name="csv_source",
        node_type=NodeType.SOURCE,
        plugin_version="1.0",
        config={},
        schema_config=DYNAMIC_SCHEMA,
    )
    transform = rec.register_node(
        run_id=run.run_id,
        plugin_name="llm_transform",
        node_type=NodeType.TRANSFORM,
        plugin_version="1.0",
        config={},
        schema_config=DYNAMIC_SCHEMA,
    )
    output_sink = rec.register_node(
        run_id=run.run_id,
        plugin_name="csv_sink",
        node_type=NodeType.SINK,
        plugin_version="1.0",
        config={},
        schema_config=DYNAMIC_SCHEMA,
    )
    error_sink = rec.register_node(
        run_id=run.run_id,
        plugin_name="error_sink",
        node_type=NodeType.SINK,
        plugin_version="1.0",
        config={},
        schema_config=DYNAMIC_SCHEMA,
    )

    # Register edges
    normal_edge = rec.register_edge(
        run_id=run.run_id,
        from_node_id=source.node_id,
        to_node_id=transform.node_id,
        label="continue",
        mode=RoutingMode.MOVE,
    )
    rec.register_edge(
        run_id=run.run_id,
        from_node_id=transform.node_id,
        to_node_id=output_sink.node_id,
        label="continue",
        mode=RoutingMode.MOVE,
    )
    divert_label = "__quarantine__" if quarantine else "__error_1__"
    divert_edge = rec.register_edge(
        run_id=run.run_id,
        from_node_id=transform.node_id,
        to_node_id=error_sink.node_id,
        label=divert_label,
        mode=RoutingMode.DIVERT,
    )

    # Create row and token
    row = rec.create_row(
        run_id=run.run_id,
        source_node_id=source.node_id,
        row_index=0,
        data={"input": "test"},
    )
    token = rec.create_token(row_id=row.row_id)

    # Record source node state (normal continue routing)
    source_state = rec.begin_node_state(
        token_id=token.token_id,
        node_id=source.node_id,
        run_id=run.run_id,
        step_index=0,
        input_data={"input": "test"},
    )
    rec.record_routing_event(
        state_id=source_state.state_id,
        edge_id=normal_edge.edge_id,
        mode=RoutingMode.MOVE,
    )
    rec.complete_node_state(
        state_id=source_state.state_id,
        status=NodeStateStatus.COMPLETED,
        output_data={"input": "test"},
        duration_ms=1.0,
    )

    # Record transform node state
    transform_state = rec.begin_node_state(
        token_id=token.token_id,
        node_id=transform.node_id,
        run_id=run.run_id,
        step_index=1,
        input_data={"input": "test"},
    )

    if diverted:
        # Token diverted to error/quarantine sink
        rec.record_routing_event(
            state_id=transform_state.state_id,
            edge_id=divert_edge.edge_id,
            mode=RoutingMode.DIVERT,
            reason={"error": "transform_failed", "detail": "timeout"},
        )
        rec.complete_node_state(
            state_id=transform_state.state_id,
            status=NodeStateStatus.FAILED,
            output_data={},
            duration_ms=5000.0,
        )
        rec.record_token_outcome(
            token_id=token.token_id,
            run_id=run.run_id,
            outcome=RowOutcome.QUARANTINED if quarantine else RowOutcome.ROUTED,
            sink_name="error_sink",
            error_hash="abc123" if quarantine else None,
        )
    else:
        # Normal completion
        rec.complete_node_state(
            state_id=transform_state.state_id,
            status=NodeStateStatus.COMPLETED,
            output_data={"output": "classified"},
            duration_ms=50.0,
        )
        rec.record_token_outcome(
            token_id=token.token_id,
            run_id=run.run_id,
            outcome=RowOutcome.COMPLETED,
            sink_name="output",
        )

    return analyzer, run.run_id, token.token_id


class TestExplainTokenDivertAnnotation:
    """Tests for DIVERT annotations in explain_token() MCP response."""

    def test_diverted_token_has_divert_summary(self) -> None:
        """Diverted token lineage includes divert_summary with diverted=True."""
        analyzer, run_id, token_id = _make_analyzer_with_token_lineage(diverted=True)
        result = analyzer.explain_token(run_id, token_id=token_id)

        assert "divert_summary" in result
        assert result["divert_summary"] is not None
        assert result["divert_summary"]["diverted"] is True

    def test_normal_token_has_null_divert_summary(self) -> None:
        """Normal completed token has divert_summary=None."""
        analyzer, run_id, token_id = _make_analyzer_with_token_lineage(diverted=False)
        result = analyzer.explain_token(run_id, token_id=token_id)

        assert "divert_summary" in result
        assert result["divert_summary"] is None

    def test_error_divert_type(self) -> None:
        """Error-routed token has divert_type='error'."""
        analyzer, run_id, token_id = _make_analyzer_with_token_lineage(
            diverted=True,
            quarantine=False,
        )
        result = analyzer.explain_token(run_id, token_id=token_id)

        assert result["divert_summary"]["divert_type"] == "error"
        assert result["divert_summary"]["edge_label"] == "__error_1__"

    def test_quarantine_divert_type(self) -> None:
        """Quarantined token has divert_type='quarantine'."""
        analyzer, run_id, token_id = _make_analyzer_with_token_lineage(
            diverted=True,
            quarantine=True,
        )
        result = analyzer.explain_token(run_id, token_id=token_id)

        assert result["divert_summary"]["divert_type"] == "quarantine"
        assert result["divert_summary"]["edge_label"] == "__quarantine__"

    def test_divert_summary_has_from_node_and_to_sink(self) -> None:
        """divert_summary references correct node IDs."""
        analyzer, run_id, token_id = _make_analyzer_with_token_lineage(diverted=True)
        result = analyzer.explain_token(run_id, token_id=token_id)

        summary = result["divert_summary"]
        assert summary["from_node"] is not None
        assert summary["to_sink"] is not None
        # from_node should be the transform (where divert happens)
        # to_sink should be the error_sink
        assert summary["from_node"] != summary["to_sink"]

    def test_divert_summary_has_reason_hash(self) -> None:
        """divert_summary includes reason_hash from routing event."""
        analyzer, run_id, token_id = _make_analyzer_with_token_lineage(diverted=True)
        result = analyzer.explain_token(run_id, token_id=token_id)

        summary = result["divert_summary"]
        assert summary["reason_hash"] is not None
        assert isinstance(summary["reason_hash"], str)

    def test_routing_events_have_flow_type_annotation(self) -> None:
        """All routing_events in lineage include flow_type field."""
        analyzer, run_id, token_id = _make_analyzer_with_token_lineage(diverted=True)
        result = analyzer.explain_token(run_id, token_id=token_id)

        events = result["routing_events"]
        assert len(events) >= 2  # source continue + transform divert

        for event in events:
            assert "flow_type" in event, f"Missing flow_type in event: {event}"
            assert event["flow_type"] in ("normal", "divert")

    def test_divert_event_has_divert_flow_type(self) -> None:
        """DIVERT routing event has flow_type='divert'."""
        analyzer, run_id, token_id = _make_analyzer_with_token_lineage(diverted=True)
        result = analyzer.explain_token(run_id, token_id=token_id)

        divert_events = [e for e in result["routing_events"] if e["flow_type"] == "divert"]
        assert len(divert_events) == 1
        assert divert_events[0]["mode"] == "divert"

    def test_normal_event_has_normal_flow_type(self) -> None:
        """Normal MOVE routing event has flow_type='normal'."""
        analyzer, run_id, token_id = _make_analyzer_with_token_lineage(diverted=True)
        result = analyzer.explain_token(run_id, token_id=token_id)

        normal_events = [e for e in result["routing_events"] if e["flow_type"] == "normal"]
        assert len(normal_events) >= 1
        assert all(e["mode"] == "move" for e in normal_events)

    def test_normal_only_token_has_all_normal_flow_types(self) -> None:
        """Token with no divert has all routing_events with flow_type='normal'."""
        analyzer, run_id, token_id = _make_analyzer_with_token_lineage(diverted=False)
        result = analyzer.explain_token(run_id, token_id=token_id)

        for event in result["routing_events"]:
            assert event["flow_type"] == "normal"
