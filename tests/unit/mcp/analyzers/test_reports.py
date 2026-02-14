"""Regression test for Phase 0 fix #10: MCP Mermaid non-unique IDs.

Bug: get_dag_structure() used node_id[:8] truncation for Mermaid node IDs.
When multiple nodes shared a prefix (e.g., "transform_classifier",
"transform_mapper"), the generated Mermaid had duplicate node IDs,
producing an invalid diagram.

Fix: Used sequential aliases (N0, N1, ...) instead of node_id[:8] truncation.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

from elspeth.contracts.enums import NodeType, RoutingMode
from elspeth.mcp.analyzers.reports import get_dag_structure


def _make_node(node_id: str, plugin_name: str, node_type: NodeType) -> MagicMock:
    """Create a mock node row."""
    node = MagicMock()
    node.node_id = node_id
    node.plugin_name = plugin_name
    node.node_type = node_type
    node.sequence_in_pipeline = 0
    return node


def _make_edge(from_id: str, to_id: str, label: str = "continue", mode: RoutingMode = RoutingMode.MOVE) -> MagicMock:
    """Create a mock edge row."""
    edge = MagicMock()
    edge.from_node_id = from_id
    edge.to_node_id = to_id
    edge.label = label
    edge.default_mode = mode
    return edge


class TestMermaidUniqueNodeIDs:
    """Verify Mermaid diagrams have unique node IDs even with similar prefixes."""

    def test_similar_prefixed_nodes_get_unique_mermaid_ids(self) -> None:
        """Nodes like "transform_classifier" and "transform_mapper" must
        produce different Mermaid node IDs. Before the fix, both would
        truncate to "transfor" and collide.
        """
        nodes = [
            _make_node("source_csv_abc123", "csv", NodeType.SOURCE),
            _make_node("transform_classifier_def456", "llm_classifier", NodeType.TRANSFORM),
            _make_node("transform_mapper_ghi789", "field_mapper", NodeType.TRANSFORM),
            _make_node("transform_truncate_jkl012", "truncate", NodeType.TRANSFORM),
            _make_node("sink_output_mno345", "csv_sink", NodeType.SINK),
        ]

        edges = [
            _make_edge("source_csv_abc123", "transform_classifier_def456"),
            _make_edge("transform_classifier_def456", "transform_mapper_ghi789"),
            _make_edge("transform_mapper_ghi789", "transform_truncate_jkl012"),
            _make_edge("transform_truncate_jkl012", "sink_output_mno345", "on_success"),
        ]

        db = MagicMock()
        recorder = MagicMock()
        recorder.get_nodes.return_value = nodes
        recorder.get_edges.return_value = edges
        recorder.get_run.return_value = MagicMock(
            started_at=None,
            completed_at=None,
            status=MagicMock(value="completed"),
        )

        result = get_dag_structure(db, recorder, "run-123")

        # Should not be an error
        assert "error" not in result

        mermaid = result["mermaid"]

        # Extract all node definition IDs (e.g., N0, N1, etc.)
        node_defs = re.findall(r'^\s+(\S+)\["', mermaid, re.MULTILINE)

        # All node IDs must be unique
        assert len(node_defs) == len(set(node_defs)), f"Mermaid diagram has duplicate node IDs: {node_defs}"

        # Verify we got sequential aliases (N0, N1, ...)
        for i, node_def in enumerate(node_defs):
            assert node_def == f"N{i}", f"Expected sequential alias N{i}, got {node_def}"
