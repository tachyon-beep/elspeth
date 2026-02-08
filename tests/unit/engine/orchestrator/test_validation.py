# tests/unit/engine/orchestrator/test_validation.py
"""Tests for pipeline configuration validation functions.

These functions run at pipeline initialization (before any rows process)
to catch config errors early. The tests verify that invalid route
destinations, transform on_error sinks, and source quarantine destinations
are rejected with clear error messages.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from elspeth.contracts.types import GateName, NodeID
from elspeth.engine.orchestrator.types import RouteValidationError
from elspeth.engine.orchestrator.validation import (
    validate_route_destinations,
    validate_source_quarantine_destination,
    validate_transform_error_sinks,
)
from elspeth.plugins.protocols import GateProtocol, TransformProtocol

# =============================================================================
# Helpers
# =============================================================================


def _make_gate_transform(*, node_id: str, name: str) -> GateProtocol:
    """Create a mock gate that satisfies isinstance(t, GateProtocol)."""
    gate = Mock(spec=GateProtocol)
    gate.node_id = node_id
    gate.name = name
    return gate


def _make_transform(*, node_id: str, name: str, on_error: str | None = None) -> TransformProtocol:
    """Create a mock transform with on_error setting."""
    transform = Mock(spec=TransformProtocol)
    transform.node_id = node_id
    transform.name = name
    transform._on_error = on_error
    return transform


def _make_source(*, name: str = "csv-source", on_validation_failure: str = "discard") -> Mock:
    """Create a mock source with quarantine settings."""
    source = Mock()
    source.name = name
    source._on_validation_failure = on_validation_failure
    return source


# =============================================================================
# validate_route_destinations
# =============================================================================


class TestValidateRouteDestinations:
    """Tests for validate_route_destinations()."""

    def test_valid_routes_pass(self) -> None:
        """Routes to existing sinks pass without error."""
        gate = _make_gate_transform(node_id="gate-1", name="risk_gate")
        route_map = {("gate-1", "high"): "high_risk_sink", ("gate-1", "low"): "low_risk_sink"}
        sinks = {"high_risk_sink", "low_risk_sink"}
        transform_id_map = {0: NodeID("gate-1")}

        validate_route_destinations(
            route_resolution_map=route_map,
            available_sinks=sinks,
            transform_id_map=transform_id_map,
            transforms=[gate],
        )

    def test_continue_routes_always_pass(self) -> None:
        """'continue' is a special value, not a sink name."""
        route_map = {("gate-1", "default"): "continue"}
        gate = _make_gate_transform(node_id="gate-1", name="pass_gate")
        transform_id_map = {0: NodeID("gate-1")}

        validate_route_destinations(
            route_resolution_map=route_map,
            available_sinks=set(),
            transform_id_map=transform_id_map,
            transforms=[gate],
        )

    def test_fork_routes_always_pass(self) -> None:
        """'fork' is a special value, not a sink name."""
        route_map = {("gate-1", "split"): "fork"}
        gate = _make_gate_transform(node_id="gate-1", name="fork_gate")
        transform_id_map = {0: NodeID("gate-1")}

        validate_route_destinations(
            route_resolution_map=route_map,
            available_sinks=set(),
            transform_id_map=transform_id_map,
            transforms=[gate],
        )

    def test_invalid_route_raises_with_gate_name(self) -> None:
        """Route to non-existent sink raises with gate name in message."""
        gate = _make_gate_transform(node_id="gate-1", name="risk_gate")
        route_map = {("gate-1", "high"): "nonexistent_sink"}
        sinks = {"output"}
        transform_id_map = {0: NodeID("gate-1")}

        with pytest.raises(RouteValidationError, match=r"risk_gate.*nonexistent_sink"):
            validate_route_destinations(
                route_resolution_map=route_map,
                available_sinks=sinks,
                transform_id_map=transform_id_map,
                transforms=[gate],
            )

    def test_error_lists_available_sinks(self) -> None:
        """Error message includes available sinks for user debugging."""
        gate = _make_gate_transform(node_id="gate-1", name="g")
        route_map = {("gate-1", "x"): "bad"}
        sinks = {"alpha", "beta"}
        transform_id_map = {0: NodeID("gate-1")}

        with pytest.raises(RouteValidationError, match=r"alpha.*beta"):
            validate_route_destinations(
                route_resolution_map=route_map,
                available_sinks=sinks,
                transform_id_map=transform_id_map,
                transforms=[gate],
            )

    def test_config_gates_validated(self) -> None:
        """Config-driven gates are also validated via config_gate_id_map."""
        config_gate = Mock()
        config_gate.name = "config_gate"
        gate_id_map = {GateName("config_gate"): NodeID("cfg-gate-1")}
        route_map = {("cfg-gate-1", "route_a"): "missing_sink"}
        sinks = {"output"}

        with pytest.raises(RouteValidationError, match=r"config_gate.*missing_sink"):
            validate_route_destinations(
                route_resolution_map=route_map,
                available_sinks=sinks,
                transform_id_map={},
                transforms=[],
                config_gate_id_map=gate_id_map,
                config_gates=[config_gate],
            )

    def test_empty_route_map_passes(self) -> None:
        """No routes to validate means no errors."""
        validate_route_destinations(
            route_resolution_map={},
            available_sinks=set(),
            transform_id_map={},
            transforms=[],
        )

    def test_non_gate_transforms_skipped_in_lookup(self) -> None:
        """Non-gate transforms in the transforms list don't interfere."""
        transform = _make_transform(node_id="t-1", name="mapper")
        gate = _make_gate_transform(node_id="gate-1", name="g")
        route_map = {("gate-1", "x"): "output"}
        sinks = {"output"}
        transform_id_map = {0: NodeID("t-1"), 1: NodeID("gate-1")}

        validate_route_destinations(
            route_resolution_map=route_map,
            available_sinks=sinks,
            transform_id_map=transform_id_map,
            transforms=[transform, gate],
        )


# =============================================================================
# validate_transform_error_sinks
# =============================================================================


class TestValidateTransformErrorSinks:
    """Tests for validate_transform_error_sinks()."""

    def test_no_on_error_passes(self) -> None:
        """Transform with on_error=None is fine (no error routing)."""
        transform = _make_transform(node_id="t-1", name="mapper", on_error=None)
        validate_transform_error_sinks([transform], {"output"})

    def test_discard_passes(self) -> None:
        """on_error='discard' is a special value, not a sink."""
        transform = _make_transform(node_id="t-1", name="mapper", on_error="discard")
        validate_transform_error_sinks([transform], set())

    def test_valid_error_sink_passes(self) -> None:
        """on_error referencing existing sink passes."""
        transform = _make_transform(node_id="t-1", name="mapper", on_error="error_sink")
        validate_transform_error_sinks([transform], {"output", "error_sink"})

    def test_invalid_error_sink_raises(self) -> None:
        """on_error referencing non-existent sink raises."""
        transform = _make_transform(node_id="t-1", name="classifier", on_error="missing")
        with pytest.raises(RouteValidationError, match=r"classifier.*missing"):
            validate_transform_error_sinks([transform], {"output"})

    def test_error_message_includes_available_sinks(self) -> None:
        """Error message lists available sinks."""
        transform = _make_transform(node_id="t-1", name="t", on_error="bad")
        with pytest.raises(RouteValidationError, match="output"):
            validate_transform_error_sinks([transform], {"output"})

    def test_gate_transforms_skipped(self) -> None:
        """Gates use routing, not on_error — should be skipped."""
        gate = _make_gate_transform(node_id="g-1", name="risk_gate")
        validate_transform_error_sinks([gate], set())

    def test_multiple_transforms_all_validated(self) -> None:
        """All transforms are checked, not just the first."""
        t1 = _make_transform(node_id="t-1", name="first", on_error="output")
        t2 = _make_transform(node_id="t-2", name="second", on_error="missing")

        with pytest.raises(RouteValidationError, match=r"second.*missing"):
            validate_transform_error_sinks([t1, t2], {"output"})

    def test_empty_transforms_passes(self) -> None:
        """Empty transform list means nothing to validate."""
        validate_transform_error_sinks([], {"output"})


# =============================================================================
# validate_source_quarantine_destination
# =============================================================================


class TestValidateSourceQuarantineDestination:
    """Tests for validate_source_quarantine_destination()."""

    def test_discard_passes(self) -> None:
        """on_validation_failure='discard' is always valid."""
        source = _make_source(on_validation_failure="discard")
        validate_source_quarantine_destination(source, {"output"})

    def test_valid_quarantine_sink_passes(self) -> None:
        """on_validation_failure referencing existing sink passes."""
        source = _make_source(on_validation_failure="quarantine_sink")
        validate_source_quarantine_destination(source, {"output", "quarantine_sink"})

    def test_invalid_quarantine_sink_raises(self) -> None:
        """on_validation_failure referencing non-existent sink raises."""
        source = _make_source(name="csv-source", on_validation_failure="missing")
        with pytest.raises(RouteValidationError, match=r"csv-source.*missing"):
            validate_source_quarantine_destination(source, {"output"})

    def test_error_message_includes_available_sinks(self) -> None:
        """Error message lists available sinks for debugging."""
        source = _make_source(on_validation_failure="bad")
        with pytest.raises(RouteValidationError, match="output"):
            validate_source_quarantine_destination(source, {"output"})

    def test_error_message_suggests_discard(self) -> None:
        """Error message suggests 'discard' as alternative."""
        source = _make_source(on_validation_failure="bad")
        with pytest.raises(RouteValidationError, match="discard"):
            validate_source_quarantine_destination(source, {"output"})
