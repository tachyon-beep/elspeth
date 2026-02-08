# tests_v2/unit/mcp/test_mcp_divert.py
"""Tests for DIVERT edge routing mode constants and enum membership.

Migrated from tests/mcp/test_mcp_divert.py.
Tests that require LandscapeDB (full DAG rendering, token lineage) are
deferred to integration tier. This file covers the unit-testable
RoutingMode contract aspects.
"""

from elspeth.contracts import RoutingMode


class TestRoutingModeDivert:
    """Verify RoutingMode.DIVERT is a valid enum member and has expected value."""

    def test_divert_is_routing_mode_member(self) -> None:
        """RoutingMode.DIVERT exists as a valid enum member."""
        assert hasattr(RoutingMode, "DIVERT")
        assert RoutingMode.DIVERT in RoutingMode

    def test_divert_value_is_divert_string(self) -> None:
        """RoutingMode.DIVERT has the string value 'divert'."""
        assert RoutingMode.DIVERT.value == "divert"

    def test_move_is_routing_mode_member(self) -> None:
        """RoutingMode.MOVE exists as a valid enum member."""
        assert hasattr(RoutingMode, "MOVE")
        assert RoutingMode.MOVE in RoutingMode

    def test_move_value_is_move_string(self) -> None:
        """RoutingMode.MOVE has the string value 'move'."""
        assert RoutingMode.MOVE.value == "move"

    def test_routing_mode_lookup_by_value(self) -> None:
        """RoutingMode can be constructed from string value."""
        assert RoutingMode("divert") is RoutingMode.DIVERT
        assert RoutingMode("move") is RoutingMode.MOVE
