# tests/property/contracts/test_routing_properties.py
"""Property-based tests for routing action contracts.

These tests verify the invariants of RoutingAction - the contract
that controls token flow through the DAG:

Kind-Mode Invariants:
- CONTINUE must have empty destinations and uses MOVE mode
- ROUTE must have exactly one destination and MOVE mode only
- FORK_TO_PATHS must use COPY mode and have unique, non-empty paths

Factory Method Properties:
- continue_() produces valid CONTINUE action
- route() produces valid ROUTE action
- fork_to_paths() produces valid FORK_TO_PATHS action

Validation Properties:
- Empty paths rejected by fork_to_paths
- Duplicate paths rejected by fork_to_paths
- COPY mode rejected by route (architectural constraint)
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.contracts.enums import RoutingKind, RoutingMode
from elspeth.contracts.routing import RoutingAction

# =============================================================================
# Strategies for generating routing data
# =============================================================================

# Valid path/label names
path_names = st.text(
    min_size=1,
    max_size=30,
    alphabet="abcdefghijklmnopqrstuvwxyz_0123456789",
).filter(lambda s: s[0].isalpha())

# Non-empty unique path lists
unique_path_lists = st.lists(path_names, min_size=1, max_size=5, unique=True)

# Reason dictionaries
reason_dicts = st.one_of(
    st.none(),
    st.dictionaries(
        keys=st.sampled_from(["condition", "threshold", "rule", "match"]),
        values=st.one_of(st.text(max_size=50), st.integers(), st.booleans()),
        min_size=0,
        max_size=3,
    ),
)


# =============================================================================
# continue_() Factory Property Tests
# =============================================================================


class TestContinueFactoryProperties:
    """Property tests for RoutingAction.continue_() factory."""

    @given(reason=reason_dicts)
    @settings(max_examples=100)
    def test_continue_sets_kind(self, reason: dict[str, Any] | None) -> None:
        """Property: continue_() sets kind to CONTINUE."""
        action = RoutingAction.continue_(reason=reason)
        assert action.kind == RoutingKind.CONTINUE

    @given(reason=reason_dicts)
    @settings(max_examples=100)
    def test_continue_has_empty_destinations(self, reason: dict[str, Any] | None) -> None:
        """Property: continue_() sets destinations to empty tuple."""
        action = RoutingAction.continue_(reason=reason)
        assert action.destinations == ()

    @given(reason=reason_dicts)
    @settings(max_examples=100)
    def test_continue_uses_move_mode(self, reason: dict[str, Any] | None) -> None:
        """Property: continue_() uses MOVE mode."""
        action = RoutingAction.continue_(reason=reason)
        assert action.mode == RoutingMode.MOVE

    def test_continue_without_reason(self) -> None:
        """Property: continue_() works without reason."""
        action = RoutingAction.continue_()
        assert action.kind == RoutingKind.CONTINUE
        assert len(action.reason) == 0


# =============================================================================
# route() Factory Property Tests
# =============================================================================


class TestRouteFactoryProperties:
    """Property tests for RoutingAction.route() factory."""

    @given(label=path_names, reason=reason_dicts)
    @settings(max_examples=100)
    def test_route_sets_kind(self, label: str, reason: dict[str, Any] | None) -> None:
        """Property: route() sets kind to ROUTE."""
        action = RoutingAction.route(label, reason=reason)
        assert action.kind == RoutingKind.ROUTE

    @given(label=path_names, reason=reason_dicts)
    @settings(max_examples=100)
    def test_route_sets_single_destination(self, label: str, reason: dict[str, Any] | None) -> None:
        """Property: route() sets destinations to single-element tuple."""
        action = RoutingAction.route(label, reason=reason)
        assert action.destinations == (label,)
        assert len(action.destinations) == 1

    @given(label=path_names, reason=reason_dicts)
    @settings(max_examples=100)
    def test_route_defaults_to_move_mode(self, label: str, reason: dict[str, Any] | None) -> None:
        """Property: route() defaults to MOVE mode."""
        action = RoutingAction.route(label, reason=reason)
        assert action.mode == RoutingMode.MOVE

    @given(label=path_names)
    @settings(max_examples=50)
    def test_route_rejects_copy_mode(self, label: str) -> None:
        """Property: route() rejects COPY mode (architectural constraint).

        ELSPETH enforces single terminal state per token. COPY mode would
        require dual terminal states (ROUTED + COMPLETED), breaking the
        audit model. Use fork_to_paths() instead.
        """
        with pytest.raises(ValueError, match="COPY mode not supported for ROUTE"):
            RoutingAction.route(label, mode=RoutingMode.COPY)


# =============================================================================
# fork_to_paths() Factory Property Tests
# =============================================================================


class TestForkToPathsFactoryProperties:
    """Property tests for RoutingAction.fork_to_paths() factory."""

    @given(paths=unique_path_lists, reason=reason_dicts)
    @settings(max_examples=100)
    def test_fork_sets_kind(self, paths: list[str], reason: dict[str, Any] | None) -> None:
        """Property: fork_to_paths() sets kind to FORK_TO_PATHS."""
        action = RoutingAction.fork_to_paths(paths, reason=reason)
        assert action.kind == RoutingKind.FORK_TO_PATHS

    @given(paths=unique_path_lists, reason=reason_dicts)
    @settings(max_examples=100)
    def test_fork_sets_destinations(self, paths: list[str], reason: dict[str, Any] | None) -> None:
        """Property: fork_to_paths() sets destinations to tuple of paths."""
        action = RoutingAction.fork_to_paths(paths, reason=reason)
        assert action.destinations == tuple(paths)

    @given(paths=unique_path_lists, reason=reason_dicts)
    @settings(max_examples=100)
    def test_fork_always_uses_copy_mode(self, paths: list[str], reason: dict[str, Any] | None) -> None:
        """Property: fork_to_paths() always uses COPY mode.

        Forks create child tokens - the parent token's data is copied
        to each path. This is enforced, not configurable.
        """
        action = RoutingAction.fork_to_paths(paths, reason=reason)
        assert action.mode == RoutingMode.COPY

    def test_fork_rejects_empty_paths(self) -> None:
        """Property: fork_to_paths() rejects empty paths list."""
        with pytest.raises(ValueError, match="at least one destination"):
            RoutingAction.fork_to_paths([])

    @given(path=path_names)
    @settings(max_examples=50)
    def test_fork_rejects_duplicate_paths(self, path: str) -> None:
        """Property: fork_to_paths() rejects duplicate paths."""
        with pytest.raises(ValueError, match="unique path names"):
            RoutingAction.fork_to_paths([path, path])

    @given(
        paths=st.lists(path_names, min_size=3, max_size=6),
    )
    @settings(max_examples=50)
    def test_fork_rejects_any_duplicates(self, paths: list[str]) -> None:
        """Property: fork_to_paths() rejects lists with any duplicates."""
        # Only test if there are duplicates
        if len(paths) == len(set(paths)):
            return  # No duplicates, skip

        with pytest.raises(ValueError, match="unique path names"):
            RoutingAction.fork_to_paths(paths)


# =============================================================================
# Invariant Validation Property Tests (Direct Construction)
# =============================================================================


class TestRoutingActionInvariantProperties:
    """Property tests for __post_init__ invariant validation."""

    @given(label=path_names)
    @settings(max_examples=50)
    def test_continue_with_destinations_rejected(self, label: str) -> None:
        """Property: CONTINUE kind with non-empty destinations is rejected."""
        with pytest.raises(ValueError, match="CONTINUE must have empty destinations"):
            RoutingAction(
                kind=RoutingKind.CONTINUE,
                destinations=(label,),
                mode=RoutingMode.MOVE,
            )

    @given(paths=unique_path_lists)
    @settings(max_examples=50)
    def test_fork_without_copy_mode_rejected(self, paths: list[str]) -> None:
        """Property: FORK_TO_PATHS with MOVE mode is rejected."""
        with pytest.raises(ValueError, match="FORK_TO_PATHS must use COPY mode"):
            RoutingAction(
                kind=RoutingKind.FORK_TO_PATHS,
                destinations=tuple(paths),
                mode=RoutingMode.MOVE,
            )

    def test_route_with_empty_destinations_rejected(self) -> None:
        """Property: ROUTE with empty destinations is rejected."""
        with pytest.raises(ValueError, match="ROUTE must have exactly one destination"):
            RoutingAction(
                kind=RoutingKind.ROUTE,
                destinations=(),
                mode=RoutingMode.MOVE,
            )

    @given(paths=st.lists(path_names, min_size=2, max_size=5, unique=True))
    @settings(max_examples=50)
    def test_route_with_multiple_destinations_rejected(self, paths: list[str]) -> None:
        """Property: ROUTE with multiple destinations is rejected."""
        with pytest.raises(ValueError, match="ROUTE must have exactly one destination"):
            RoutingAction(
                kind=RoutingKind.ROUTE,
                destinations=tuple(paths),
                mode=RoutingMode.MOVE,
            )

    @given(label=path_names)
    @settings(max_examples=50)
    def test_route_with_copy_mode_rejected(self, label: str) -> None:
        """Property: ROUTE with COPY mode is rejected (architectural constraint)."""
        with pytest.raises(ValueError, match="COPY mode not supported for ROUTE"):
            RoutingAction(
                kind=RoutingKind.ROUTE,
                destinations=(label,),
                mode=RoutingMode.COPY,
            )


# =============================================================================
# Immutability Property Tests
# =============================================================================


class TestRoutingActionImmutabilityProperties:
    """Property tests for frozen dataclass behavior."""

    @given(reason=reason_dicts)
    @settings(max_examples=50)
    def test_continue_action_is_immutable(self, reason: dict[str, Any] | None) -> None:
        """Property: CONTINUE action cannot be mutated."""
        action = RoutingAction.continue_(reason=reason)

        with pytest.raises(AttributeError):
            action.kind = RoutingKind.ROUTE  # type: ignore[misc]

        with pytest.raises(AttributeError):
            action.destinations = ("new",)  # type: ignore[misc]

    @given(label=path_names)
    @settings(max_examples=50)
    def test_route_action_is_immutable(self, label: str) -> None:
        """Property: ROUTE action cannot be mutated."""
        action = RoutingAction.route(label)

        with pytest.raises(AttributeError):
            action.kind = RoutingKind.CONTINUE  # type: ignore[misc]

        with pytest.raises(AttributeError):
            action.mode = RoutingMode.COPY  # type: ignore[misc]

    @given(paths=unique_path_lists)
    @settings(max_examples=50)
    def test_fork_action_is_immutable(self, paths: list[str]) -> None:
        """Property: FORK_TO_PATHS action cannot be mutated."""
        action = RoutingAction.fork_to_paths(paths)

        with pytest.raises(AttributeError):
            action.kind = RoutingKind.ROUTE  # type: ignore[misc]

        with pytest.raises(AttributeError):
            action.destinations = ()  # type: ignore[misc]


# =============================================================================
# Reason Immutability Property Tests
# =============================================================================


class TestRoutingReasonImmutabilityProperties:
    """Property tests for reason field immutability."""

    def test_reason_is_immutable_view(self) -> None:
        """Property: reason field is an immutable mapping view."""
        original = {"key": "value", "nested": {"inner": 1}}
        action = RoutingAction.continue_(reason=original)

        # Cannot modify via the action
        with pytest.raises(TypeError):
            action.reason["key"] = "modified"  # type: ignore[index]

        with pytest.raises(TypeError):
            action.reason["new_key"] = "new"  # type: ignore[index]

    def test_reason_is_defensive_copy(self) -> None:
        """Property: Modifying original dict doesn't affect action.

        RoutingAction makes a deep copy of reason to prevent mutation
        via retained references to the original dict.
        """
        original = {"key": "value"}
        action = RoutingAction.continue_(reason=original)

        # Modify original
        original["key"] = "modified"
        original["new_key"] = "new"

        # Action's reason should be unchanged
        assert action.reason["key"] == "value"
        assert "new_key" not in action.reason


# =============================================================================
# Enum Coverage Property Tests
# =============================================================================


class TestRoutingEnumProperties:
    """Property tests for routing enum handling."""

    def test_all_routing_kinds_have_factory(self) -> None:
        """Property: Every RoutingKind has a corresponding factory method.

        Canary test - adding a new kind requires adding a factory.
        """
        # Map kinds to their factory methods
        kind_factories = {
            RoutingKind.CONTINUE: RoutingAction.continue_,
            RoutingKind.ROUTE: RoutingAction.route,
            RoutingKind.FORK_TO_PATHS: RoutingAction.fork_to_paths,
        }

        # All kinds should be covered
        assert set(kind_factories.keys()) == set(RoutingKind)

    def test_all_routing_modes_are_used(self) -> None:
        """Property: Both routing modes are used in valid combinations.

        MOVE: Used by CONTINUE and ROUTE
        COPY: Used by FORK_TO_PATHS (only)
        """
        continue_action = RoutingAction.continue_()
        route_action = RoutingAction.route("sink")
        fork_action = RoutingAction.fork_to_paths(["a", "b"])

        # MOVE is used by continue and route
        assert continue_action.mode == RoutingMode.MOVE
        assert route_action.mode == RoutingMode.MOVE

        # COPY is used by fork (only)
        assert fork_action.mode == RoutingMode.COPY
