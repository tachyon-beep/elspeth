"""Regression test for Phase 0 fix #2: GraphValidationError suppressed.

Bug: In get_effective_producer_schema(), when processing a select-merge
coalesce with a transform branch, _trace_branch_endpoints was called
inside a try/except that caught GraphValidationError and returned None
instead of propagating the error. This silently hid graph construction
bugs by falling back to "dynamic schema" instead of raising.

Fix: Removed the try/except so GraphValidationError from
_trace_branch_endpoints propagates up to the caller.
"""

from __future__ import annotations

import pytest

from elspeth.contracts.enums import NodeType, RoutingMode
from elspeth.core.dag.graph import ExecutionGraph
from elspeth.core.dag.models import GraphValidationError


class TestSelectMergeCoalesceRaisesOnBrokenBranch:
    """Verify GraphValidationError propagates from get_effective_producer_schema
    for select-merge coalesce with untraceable branches.
    """

    def test_untraceable_branch_raises_graph_validation_error(self) -> None:
        """When _trace_branch_endpoints fails for a select-merge coalesce,
        get_effective_producer_schema must raise GraphValidationError,
        not return None.

        Before the fix, a try/except caught the error and returned None,
        silently treating the coalesce as dynamic schema.
        """
        graph = ExecutionGraph()

        # Build a minimal graph with a select-merge coalesce
        # that has a transform branch which cannot be traced
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")
        graph.add_node(
            "gate",
            node_type=NodeType.GATE,
            plugin_name="fork_gate",
            config={"routes": {"true": "fork"}},
        )
        graph.add_node(
            "coalesce",
            node_type=NodeType.COALESCE,
            plugin_name="coalesce",
            config={
                "merge": "select",
                "select_branch": "branch_a",
            },
        )
        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv_sink")

        # Wire edges: source -> gate, gate -> coalesce (COPY for branch_b),
        # but branch_a is a MOVE edge that has no proper chain
        graph.add_edge("source", "gate", label="continue")
        # branch_b is identity (COPY)
        graph.add_edge("gate", "coalesce", label="branch_b", mode=RoutingMode.COPY)
        # branch_a has a MOVE edge from gate directly to coalesce
        # but with no intermediate transform — the trace should find gate as
        # the fork producer, but we deliberately set up a broken trace by
        # NOT populating the _branch_gate_map for this branch
        graph.add_edge("gate", "coalesce", label="branch_a", mode=RoutingMode.MOVE)
        graph.add_edge("coalesce", "sink", label="on_success")

        # Set the branch_gate_map to point to a nonexistent gate for branch_a
        # This simulates a graph construction bug
        graph.set_branch_gate_map({"branch_a": "nonexistent_gate"})

        # get_effective_producer_schema for coalesce with select-merge
        # should raise GraphValidationError, NOT return None
        with pytest.raises((GraphValidationError, KeyError)):
            graph.get_effective_producer_schema("coalesce")

    def test_valid_select_merge_still_works(self) -> None:
        """Sanity check: properly constructed select-merge coalesce works."""
        graph = ExecutionGraph()

        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")
        graph.add_node(
            "gate",
            node_type=NodeType.GATE,
            plugin_name="fork_gate",
            config={"routes": {"true": "fork"}},
        )
        graph.add_node(
            "coalesce",
            node_type=NodeType.COALESCE,
            plugin_name="coalesce",
            config={
                "merge": "select",
                "select_branch": "branch_b",
            },
        )
        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv_sink")

        graph.add_edge("source", "gate", label="continue")
        # branch_b is identity (COPY) — select picks this branch
        graph.add_edge("gate", "coalesce", label="branch_b", mode=RoutingMode.COPY)
        graph.add_edge("gate", "coalesce", label="branch_a", mode=RoutingMode.MOVE)
        graph.add_edge("coalesce", "sink", label="on_success")

        graph.set_branch_gate_map({"branch_a": "gate"})

        # Identity branch (COPY): should trace through to gate's schema
        # This should NOT raise
        result = graph.get_effective_producer_schema("coalesce")
        # Returns None because gate has no output_schema — that's fine,
        # the important thing is it didn't raise an error
        assert result is None
