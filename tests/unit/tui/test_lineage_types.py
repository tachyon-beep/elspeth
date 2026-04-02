"""Tests for TUI type contracts."""

import pytest

from elspeth.tui.types import LineageData


class TestLineageDataWithLineageTree:
    """Integration tests for LineageData with LineageTree widget."""

    def test_lineage_tree_accepts_lineage_data(self) -> None:
        """LineageTree accepts properly formed LineageData."""
        from elspeth.tui.widgets.lineage_tree import LineageTree

        data: LineageData = {
            "run_id": "run-123",
            "source": {"name": "csv", "node_id": "node-1"},
            "transforms": [{"name": "mapper", "node_id": "node-2", "node_type": "transform"}],
            "sinks": [{"name": "output", "node_id": "node-3", "node_type": "sink"}],
            "tokens": [],
        }
        tree = LineageTree(data)
        nodes = tree.get_tree_nodes()
        assert len(nodes) > 0

    def test_lineage_tree_rejects_missing_run_id(self) -> None:
        """LineageTree raises KeyError for missing run_id."""
        from elspeth.tui.widgets.lineage_tree import LineageTree

        # Deliberately malformed data - missing run_id
        data = {
            "source": {"name": "csv", "node_id": "node-1"},
            "transforms": [],
            "sinks": [],
            "tokens": [],
        }
        with pytest.raises(KeyError, match="run_id"):
            LineageTree(data)  # type: ignore[arg-type]

    def test_lineage_tree_rejects_missing_source(self) -> None:
        """LineageTree raises KeyError for missing source."""
        from elspeth.tui.widgets.lineage_tree import LineageTree

        # Deliberately malformed data - missing source
        data = {
            "run_id": "run-123",
            "transforms": [],
            "sinks": [],
            "tokens": [],
        }
        with pytest.raises(KeyError, match="source"):
            LineageTree(data)  # type: ignore[arg-type]

    def test_lineage_tree_rejects_malformed_source(self) -> None:
        """LineageTree raises KeyError for malformed source."""
        from elspeth.tui.widgets.lineage_tree import LineageTree

        # Deliberately malformed data - source missing 'name'
        data = {
            "run_id": "run-123",
            "source": {"node_id": "node-1"},  # missing 'name'
            "transforms": [],
            "sinks": [],
            "tokens": [],
        }
        with pytest.raises(KeyError, match="name"):
            LineageTree(data)  # type: ignore[arg-type]
