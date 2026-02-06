# tests/mcp/test_mcp_divert.py
"""Tests for DIVERT edge rendering in MCP get_dag_structure()."""

from __future__ import annotations

from elspeth.contracts import NodeType, RoutingMode
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
