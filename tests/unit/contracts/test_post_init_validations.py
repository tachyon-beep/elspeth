"""Tests for __post_init__ validations added to contracts types.

Covers: RuntimeTelemetryConfig, OutputValidationResult, RoutingSpec, EdgeInfo,
and RoutingAction reason copy.
"""

import pytest

from elspeth.contracts.config.runtime import RuntimeTelemetryConfig
from elspeth.contracts.enums import BackpressureMode, RoutingKind, RoutingMode, TelemetryGranularity
from elspeth.contracts.routing import EdgeInfo, RoutingAction, RoutingSpec
from elspeth.contracts.sink import OutputValidationResult


class TestRuntimeTelemetryConfigPostInit:
    def test_rejects_zero_max_consecutive_failures(self) -> None:
        with pytest.raises(ValueError, match="max_consecutive_failures must be >= 1"):
            RuntimeTelemetryConfig(
                enabled=True,
                granularity=TelemetryGranularity.LIFECYCLE,
                backpressure_mode=BackpressureMode.BLOCK,
                fail_on_total_exporter_failure=True,
                max_consecutive_failures=0,
                exporter_configs=(),
            )

    def test_rejects_negative_max_consecutive_failures(self) -> None:
        with pytest.raises(ValueError, match="max_consecutive_failures must be >= 1"):
            RuntimeTelemetryConfig(
                enabled=True,
                granularity=TelemetryGranularity.LIFECYCLE,
                backpressure_mode=BackpressureMode.BLOCK,
                fail_on_total_exporter_failure=True,
                max_consecutive_failures=-3,
                exporter_configs=(),
            )

    def test_default_factory_passes_validation(self) -> None:
        config = RuntimeTelemetryConfig.default()
        assert config.max_consecutive_failures == 10


class TestOutputValidationResultPostInit:
    def test_failure_requires_error_message(self) -> None:
        with pytest.raises(ValueError, match="valid=False must have error_message"):
            OutputValidationResult(valid=False)

    def test_success_without_message_accepted(self) -> None:
        result = OutputValidationResult(valid=True)
        assert result.error_message is None

    def test_failure_factory_works(self) -> None:
        result = OutputValidationResult.failure("fields don't match")
        assert not result.valid
        assert result.error_message == "fields don't match"


class TestRoutingSpecPostInit:
    def test_rejects_empty_edge_id(self) -> None:
        with pytest.raises(ValueError, match="edge_id must not be empty"):
            RoutingSpec(edge_id="", mode=RoutingMode.MOVE)

    def test_accepts_valid(self) -> None:
        spec = RoutingSpec(edge_id="edge-1", mode=RoutingMode.MOVE)
        assert spec.edge_id == "edge-1"


class TestEdgeInfoPostInit:
    def test_rejects_empty_from_node(self) -> None:
        with pytest.raises(ValueError, match="from_node must not be empty"):
            EdgeInfo(from_node="", to_node="b", label="x", mode=RoutingMode.MOVE)

    def test_rejects_empty_to_node(self) -> None:
        with pytest.raises(ValueError, match="to_node must not be empty"):
            EdgeInfo(from_node="a", to_node="", label="x", mode=RoutingMode.MOVE)

    def test_accepts_valid(self) -> None:
        edge = EdgeInfo(from_node="a", to_node="b", label="continue", mode=RoutingMode.MOVE)
        assert edge.from_node == "a"


class TestRoutingActionReasonCopy:
    """Verify that __post_init__ defensive-copies reason dicts."""

    def test_direct_construction_copies_reason(self) -> None:
        """Direct construction should deep-copy reason to prevent mutation."""
        reason = {"condition": "x > 1", "result": "true"}
        action = RoutingAction(
            kind=RoutingKind.CONTINUE,
            destinations=(),
            mode=RoutingMode.MOVE,
            reason=reason,
        )
        # Mutating the original dict should NOT affect the action
        reason["condition"] = "MUTATED"
        assert action.reason["condition"] == "x > 1"  # type: ignore[index]

    def test_factory_also_protects(self) -> None:
        """Factory methods also protect via __post_init__ copy."""
        reason = {"condition": "x > 1", "result": "true"}
        action = RoutingAction.continue_(reason=reason)
        reason["condition"] = "MUTATED"
        assert action.reason["condition"] == "x > 1"  # type: ignore[index]

    def test_none_reason_accepted(self) -> None:
        action = RoutingAction.continue_()
        assert action.reason is None
