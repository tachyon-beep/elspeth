# tests/property/contracts/test_routing_properties.py
"""Property-based tests for RoutingAction algebraic invariants.

RoutingAction encodes the kind-mode-destinations triple that gates produce.
The __post_init__ enforces strict invariants:
- CONTINUE: empty destinations, MOVE mode
- ROUTE: exactly one destination, MOVE mode (no COPY)
- FORK_TO_PATHS: always COPY mode, non-empty unique destinations

These invariants are critical for the engine to correctly record routing
events and determine token flow (move vs copy semantics).

Properties tested:
- Factory methods always produce valid actions (invariants hold)
- Invalid kind-mode-destination combinations always raise ValueError
- Reason deep copy (mutation isolation)
- FORK_TO_PATHS rejects duplicates and empty paths
- Destination tuple immutability
- All RoutingKind values are covered by factory methods
"""

from __future__ import annotations

from typing import cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.contracts.enums import RoutingKind, RoutingMode
from elspeth.contracts.errors import ConfigGateReason, PluginGateReason, RoutingReason
from elspeth.contracts.routing import RoutingAction

# =============================================================================
# Strategies
# =============================================================================

# Route labels (non-empty strings for sink/path names)
route_labels = st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz_0123456789")

# Path lists for fork (unique, non-empty)
fork_paths = st.lists(
    route_labels,
    min_size=1,
    max_size=10,
    unique=True,
)

# Routing reasons (TypedDict instances matching RoutingReason union)
routing_reasons: st.SearchStrategy[RoutingReason | None] = st.one_of(
    st.none(),
    st.builds(
        lambda condition, result: cast(RoutingReason, {"condition": condition, "result": result}),
        condition=st.text(max_size=50),
        result=st.text(max_size=20),
    ),
    st.builds(
        lambda rule, matched_value: cast(RoutingReason, {"rule": rule, "matched_value": matched_value}),
        rule=st.text(max_size=20),
        matched_value=st.text(max_size=20),
    ),
)


# =============================================================================
# Factory Method Invariants
# =============================================================================


class TestContinueFactoryProperties:
    """RoutingAction.continue_() must always produce valid CONTINUE actions."""

    @given(reason=routing_reasons)
    @settings(max_examples=100)
    def test_continue_has_correct_kind(self, reason: RoutingReason | None) -> None:
        """Property: continue_() always produces CONTINUE kind."""
        action = RoutingAction.continue_(reason=reason)
        assert action.kind == RoutingKind.CONTINUE

    @given(reason=routing_reasons)
    @settings(max_examples=100)
    def test_continue_has_empty_destinations(self, reason: RoutingReason | None) -> None:
        """Property: continue_() always has empty destinations."""
        action = RoutingAction.continue_(reason=reason)
        assert action.destinations == ()

    @given(reason=routing_reasons)
    @settings(max_examples=100)
    def test_continue_has_move_mode(self, reason: RoutingReason | None) -> None:
        """Property: continue_() always uses MOVE mode."""
        action = RoutingAction.continue_(reason=reason)
        assert action.mode == RoutingMode.MOVE


class TestRouteFactoryProperties:
    """RoutingAction.route() must always produce valid ROUTE actions."""

    @given(label=route_labels, reason=routing_reasons)
    @settings(max_examples=100)
    def test_route_has_correct_kind(self, label: str, reason: RoutingReason | None) -> None:
        """Property: route() always produces ROUTE kind."""
        action = RoutingAction.route(label, reason=reason)
        assert action.kind == RoutingKind.ROUTE

    @given(label=route_labels)
    @settings(max_examples=100)
    def test_route_has_single_destination(self, label: str) -> None:
        """Property: route() always has exactly one destination."""
        action = RoutingAction.route(label)
        assert len(action.destinations) == 1
        assert action.destinations[0] == label

    @given(label=route_labels)
    @settings(max_examples=100)
    def test_route_has_move_mode(self, label: str) -> None:
        """Property: route() defaults to MOVE mode."""
        action = RoutingAction.route(label)
        assert action.mode == RoutingMode.MOVE

    @given(label=route_labels)
    @settings(max_examples=50)
    def test_route_rejects_copy_mode(self, label: str) -> None:
        """Property: route(mode=COPY) always raises ValueError."""
        with pytest.raises(ValueError, match="COPY mode not supported"):
            RoutingAction.route(label, mode=RoutingMode.COPY)


class TestForkFactoryProperties:
    """RoutingAction.fork_to_paths() must always produce valid FORK_TO_PATHS actions."""

    @given(paths=fork_paths, reason=routing_reasons)
    @settings(max_examples=100)
    def test_fork_has_correct_kind(self, paths: list[str], reason: RoutingReason | None) -> None:
        """Property: fork_to_paths() always produces FORK_TO_PATHS kind."""
        action = RoutingAction.fork_to_paths(paths, reason=reason)
        assert action.kind == RoutingKind.FORK_TO_PATHS

    @given(paths=fork_paths)
    @settings(max_examples=100)
    def test_fork_has_copy_mode(self, paths: list[str]) -> None:
        """Property: fork_to_paths() always uses COPY mode."""
        action = RoutingAction.fork_to_paths(paths)
        assert action.mode == RoutingMode.COPY

    @given(paths=fork_paths)
    @settings(max_examples=100)
    def test_fork_preserves_destinations(self, paths: list[str]) -> None:
        """Property: fork destinations match input paths."""
        action = RoutingAction.fork_to_paths(paths)
        assert list(action.destinations) == paths

    def test_fork_rejects_empty_paths(self) -> None:
        """Property: Empty path list always raises ValueError."""
        with pytest.raises(ValueError, match="at least one"):
            RoutingAction.fork_to_paths([])

    @given(
        path=route_labels,
        n_copies=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_fork_rejects_duplicate_paths(self, path: str, n_copies: int) -> None:
        """Property: Duplicate paths always raise ValueError."""
        with pytest.raises(ValueError, match="duplicates"):
            RoutingAction.fork_to_paths([path] * n_copies)


# =============================================================================
# Invalid Combination Properties
# =============================================================================


class TestInvalidCombinationProperties:
    """Invalid kind-mode-destination combinations must always raise."""

    @given(dest=route_labels)
    @settings(max_examples=50)
    def test_continue_with_destinations_raises(self, dest: str) -> None:
        """Property: CONTINUE with non-empty destinations raises."""
        with pytest.raises(ValueError, match="CONTINUE must have empty"):
            RoutingAction(
                kind=RoutingKind.CONTINUE,
                destinations=(dest,),
                mode=RoutingMode.MOVE,
            )

    def test_continue_with_copy_mode_raises(self) -> None:
        """Property: CONTINUE with COPY mode raises."""
        with pytest.raises(ValueError, match="CONTINUE must use MOVE"):
            RoutingAction(
                kind=RoutingKind.CONTINUE,
                destinations=(),
                mode=RoutingMode.COPY,
            )

    def test_route_with_zero_destinations_raises(self) -> None:
        """Property: ROUTE with zero destinations raises."""
        with pytest.raises(ValueError, match="exactly one destination"):
            RoutingAction(
                kind=RoutingKind.ROUTE,
                destinations=(),
                mode=RoutingMode.MOVE,
            )

    @given(dests=st.lists(route_labels, min_size=2, max_size=5, unique=True))
    @settings(max_examples=50)
    def test_route_with_multiple_destinations_raises(self, dests: list[str]) -> None:
        """Property: ROUTE with >1 destination raises."""
        with pytest.raises(ValueError, match="exactly one destination"):
            RoutingAction(
                kind=RoutingKind.ROUTE,
                destinations=tuple(dests),
                mode=RoutingMode.MOVE,
            )

    @given(paths=fork_paths)
    @settings(max_examples=50)
    def test_fork_with_move_mode_raises(self, paths: list[str]) -> None:
        """Property: FORK_TO_PATHS with MOVE mode raises."""
        with pytest.raises(ValueError, match="COPY mode"):
            RoutingAction(
                kind=RoutingKind.FORK_TO_PATHS,
                destinations=tuple(paths),
                mode=RoutingMode.MOVE,
            )


# =============================================================================
# Reason Deep Copy Properties
# =============================================================================


class TestReasonDeepCopyProperties:
    """Reason must be deep copied to prevent mutation via retained references."""

    def test_continue_reason_is_isolated(self) -> None:
        """Property: Mutating original reason dict does not affect action."""
        reason: ConfigGateReason = {"condition": "x > 10", "result": "high"}
        action = RoutingAction.continue_(reason=reason)

        reason["condition"] = "MUTATED"
        assert action.reason is not None
        assert cast(ConfigGateReason, action.reason)["condition"] == "x > 10"

    def test_route_reason_is_isolated(self) -> None:
        """Property: Mutating original reason dict does not affect action."""
        reason: PluginGateReason = {"rule": "route", "matched_value": "high"}
        action = RoutingAction.route("above", reason=reason)

        reason["matched_value"] = "MUTATED"
        assert action.reason is not None
        assert cast(PluginGateReason, action.reason)["matched_value"] == "high"

    def test_fork_reason_is_isolated(self) -> None:
        """Property: Mutating original reason dict does not affect action."""
        reason: PluginGateReason = {"rule": "fork", "matched_value": "3"}
        action = RoutingAction.fork_to_paths(["a", "b"], reason=reason)

        reason["matched_value"] = "MUTATED"
        assert action.reason is not None
        assert cast(PluginGateReason, action.reason)["matched_value"] == "3"

    def test_none_reason_is_preserved(self) -> None:
        """Property: None reason stays None."""
        action = RoutingAction.continue_(reason=None)
        assert action.reason is None


# =============================================================================
# Frozen Dataclass Properties
# =============================================================================


class TestFrozenProperties:
    """RoutingAction is frozen — no mutation after construction."""

    @given(label=route_labels)
    @settings(max_examples=50)
    def test_destinations_are_tuple(self, label: str) -> None:
        """Property: destinations is always a tuple (immutable sequence)."""
        action = RoutingAction.route(label)
        assert isinstance(action.destinations, tuple)

    def test_fork_destinations_are_tuple(self) -> None:
        """Property: fork destinations are tuple, not list."""
        action = RoutingAction.fork_to_paths(["a", "b", "c"])
        assert isinstance(action.destinations, tuple)

    def test_frozen_prevents_mutation(self) -> None:
        """Property: Cannot set attributes on frozen dataclass."""
        action = RoutingAction.continue_()
        with pytest.raises(AttributeError):
            action.kind = RoutingKind.ROUTE  # type: ignore[misc]
