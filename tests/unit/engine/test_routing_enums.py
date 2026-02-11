"""Tests for engine routing behavior with RoutingKind enum.

This module tests how RoutingAction correctly uses RoutingKind values.
Contract tests for RoutingKind itself are in tests/contracts/test_routing.py
and tests/contracts/test_enums.py.
"""

from elspeth.contracts import RoutingAction, RoutingKind


class TestRoutingActionKindEnum:
    """Verify RoutingAction correctly uses RoutingKind enum."""

    def test_continue_action_has_continue_kind(self) -> None:
        """RoutingAction.continue_() returns action with CONTINUE kind."""
        action = RoutingAction.continue_()
        assert action.kind is RoutingKind.CONTINUE

    def test_route_action_has_route_kind(self) -> None:
        """RoutingAction.route() returns action with ROUTE kind."""
        action = RoutingAction.route("sink_name")
        assert action.kind is RoutingKind.ROUTE

    def test_fork_action_has_fork_kind(self) -> None:
        """RoutingAction.fork_to_paths() returns action with FORK_TO_PATHS kind."""
        action = RoutingAction.fork_to_paths(["path_a", "path_b"])
        assert action.kind is RoutingKind.FORK_TO_PATHS

    def test_routing_kind_is_str_enum(self) -> None:
        """RoutingKind is (str, Enum) for serialization."""
        # This enables database storage without explicit .value calls
        # Using .value for explicit string comparison instead of relying on implicit coercion
        assert RoutingKind.CONTINUE.value == "continue"
        assert RoutingKind.ROUTE.value == "route"
        assert RoutingKind.FORK_TO_PATHS.value == "fork_to_paths"

    def test_routing_kind_used_for_dispatch(self) -> None:
        """Verify RoutingKind values can be used in if/elif dispatch.

        This tests that the actual dispatch pattern used in GateExecutor works
        correctly with the enum values.
        """
        actions = [
            RoutingAction.continue_(),
            RoutingAction.route("sink"),
            RoutingAction.fork_to_paths(["a", "b"]),
        ]

        expected_kinds = [
            RoutingKind.CONTINUE,
            RoutingKind.ROUTE,
            RoutingKind.FORK_TO_PATHS,
        ]

        for action, expected_kind in zip(actions, expected_kinds, strict=True):
            # Test the dispatch pattern used in engine
            if action.kind == RoutingKind.CONTINUE:
                matched_kind: RoutingKind | None = RoutingKind.CONTINUE
            elif action.kind == RoutingKind.ROUTE:
                matched_kind = RoutingKind.ROUTE
            elif action.kind == RoutingKind.FORK_TO_PATHS:
                matched_kind = RoutingKind.FORK_TO_PATHS
            else:
                # Exhaustive match - unreachable if all cases handled
                matched_kind = None  # type: ignore[unreachable]

            assert matched_kind is expected_kind
