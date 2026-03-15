"""Regression tests for MCP report analyzer functions.

Bug fixes covered:
- Phase 0 fix #10: MCP Mermaid non-unique IDs (node_id[:8] truncation)
- P1-2026-02-14: get_performance_report truncates node_id
- P1-2026-02-14: get_outcome_analysis returns is_terminal as DB integer
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

from elspeth.contracts.enums import NodeType, RoutingMode
from elspeth.mcp.analyzers.reports import (
    get_dag_structure,
    get_outcome_analysis,
    get_performance_report,
)


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


class TestPerformanceReportNodeId:
    """Verify get_performance_report returns full node_id.

    Regression: P1-2026-02-14 — node_id was truncated to 12 chars + "...",
    making node identity ambiguous and preventing exact cross-referencing.
    """

    def test_node_id_is_not_truncated(self) -> None:
        """Node IDs in performance report must be the full canonical ID."""
        full_node_id = "transform_llm_classifier_abc123def456"

        # Mock a stats row with full node_id
        stats_row = MagicMock()
        stats_row.node_id = full_node_id
        stats_row.plugin_name = "llm_classifier"
        stats_row.node_type = "transform"
        stats_row.executions = 10
        stats_row.avg_ms = 150.0
        stats_row.min_ms = 50.0
        stats_row.max_ms = 500.0
        stats_row.total_ms = 1500.0

        # Mock database connection and query results
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.side_effect = [
            [stats_row],  # stats_query
            [],  # failed_query
        ]

        db = MagicMock()
        db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        db.connection.return_value.__exit__ = MagicMock(return_value=False)

        recorder = MagicMock()
        recorder.get_run.return_value = MagicMock(
            started_at=None,
            completed_at=None,
            status=MagicMock(value="completed"),
        )

        result = get_performance_report(db, recorder, "run-123")

        assert "error" not in result
        node_perf = result["node_performance"]
        assert len(node_perf) == 1
        # The key assertion: full node_id, no truncation
        assert node_perf[0]["node_id"] == full_node_id
        assert "..." not in node_perf[0]["node_id"]


class TestOutcomeAnalysisIsTerminal:
    """Verify get_outcome_analysis returns is_terminal as bool.

    Regression: P1-2026-02-14 — is_terminal was returned as DB integer (0/1)
    instead of bool, violating the OutcomeDistributionEntry contract.
    """

    def test_is_terminal_is_bool_not_int(self) -> None:
        """is_terminal must be a Python bool, not an integer 0/1."""
        # Mock outcome rows with integer is_terminal (as from SQLite)
        outcome_row_terminal = MagicMock()
        outcome_row_terminal.outcome = "COMPLETED"
        outcome_row_terminal.is_terminal = 1  # DB integer
        outcome_row_terminal.count = 10

        outcome_row_non_terminal = MagicMock()
        outcome_row_non_terminal.outcome = "BUFFERED"
        outcome_row_non_terminal.is_terminal = 0  # DB integer
        outcome_row_non_terminal.count = 3

        # Mock sink rows (empty)
        # Mock fork/join counts
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.side_effect = [
            [outcome_row_terminal, outcome_row_non_terminal],  # outcome_dist
            [],  # sink_dist
        ]
        mock_conn.execute.return_value.scalar.side_effect = [0, 0]  # fork_count, join_count

        # Need to handle multiple calls to execute() returning different results
        call_count = 0

        def side_effect_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.fetchall.return_value = [outcome_row_terminal, outcome_row_non_terminal]
            elif call_count == 2:
                result.fetchall.return_value = []
            elif call_count in (3, 4):
                result.scalar.return_value = 0
            return result

        mock_conn.execute = side_effect_execute

        db = MagicMock()
        db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        db.connection.return_value.__exit__ = MagicMock(return_value=False)

        recorder = MagicMock()
        recorder.get_run.return_value = MagicMock(
            started_at=None,
            completed_at=None,
            status=MagicMock(value="completed"),
        )

        result = get_outcome_analysis(db, recorder, "run-123")

        assert "error" not in result
        outcomes = result["outcome_distribution"]
        assert len(outcomes) == 2

        for outcome in outcomes:
            assert isinstance(outcome["is_terminal"], bool), f"is_terminal must be bool, got {type(outcome['is_terminal']).__name__}"

        # Verify correct boolean values
        terminal = next(o for o in outcomes if o["outcome"] == "COMPLETED")
        non_terminal = next(o for o in outcomes if o["outcome"] == "BUFFERED")
        assert terminal["is_terminal"] is True
        assert non_terminal["is_terminal"] is False


class TestHighVarianceZeroDuration:
    """Verify high_variance filter includes nodes with zero avg_ms.

    Bug: T3 — `if n["avg_ms"] and n["max_ms"]` excluded nodes where
    avg_ms=0.0, because 0.0 is falsy in Python. A node with avg_ms=0.0
    and max_ms=100.0 (high variance!) was silently dropped.
    """

    def test_zero_avg_ms_included_in_high_variance(self) -> None:
        """Node with avg_ms=0.0 and high max_ms should appear in high_variance."""
        fast_node = MagicMock()
        fast_node.node_id = "transform_fast_abc123"
        fast_node.plugin_name = "fast_transform"
        fast_node.node_type = "transform"
        fast_node.executions = 100
        fast_node.avg_ms = 0.0  # Zero average — the key trigger
        fast_node.min_ms = 0.0
        fast_node.max_ms = 100.0  # But max is high — this IS high variance
        fast_node.total_ms = 5.0

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.side_effect = [
            [fast_node],  # stats_query
            [],  # failed_query
        ]

        db = MagicMock()
        db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        db.connection.return_value.__exit__ = MagicMock(return_value=False)

        recorder = MagicMock()
        recorder.get_run.return_value = MagicMock(
            started_at=None,
            completed_at=None,
            status=MagicMock(value="completed"),
        )

        result = get_performance_report(db, recorder, "run-123")

        assert "error" not in result
        # Before fix: high_variance was [] because `0.0 and 100.0` is falsy
        # After fix: node with avg_ms=0.0 but max_ms=100.0 IS high variance
        high_variance = result["high_variance_nodes"]
        assert len(high_variance) == 1
        assert high_variance[0]["node_id"] == "transform_fast_abc123"

    def test_none_avg_ms_excluded_from_high_variance(self) -> None:
        """Node with avg_ms=None (no timing data) should NOT appear in high_variance."""
        no_timing_node = MagicMock()
        no_timing_node.node_id = "transform_notimed_abc123"
        no_timing_node.plugin_name = "notimed_transform"
        no_timing_node.node_type = "transform"
        no_timing_node.executions = 1
        no_timing_node.avg_ms = None
        no_timing_node.min_ms = None
        no_timing_node.max_ms = None
        no_timing_node.total_ms = None

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.side_effect = [
            [no_timing_node],  # stats_query
            [],  # failed_query
        ]

        db = MagicMock()
        db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        db.connection.return_value.__exit__ = MagicMock(return_value=False)

        recorder = MagicMock()
        recorder.get_run.return_value = MagicMock(
            started_at=None,
            completed_at=None,
            status=MagicMock(value="completed"),
        )

        result = get_performance_report(db, recorder, "run-123")

        assert "error" not in result
        high_variance = result["high_variance_nodes"]
        assert len(high_variance) == 0
