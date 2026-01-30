"""Tests for error/reason schema contracts.

Tests for:
- ExecutionError TypedDict (exception, type, traceback fields)
- RoutingReason TypedDict (rule, matched_value, threshold fields)
- TransformReason TypedDict (action, fields_modified fields)
"""


class TestExecutionErrorSchema:
    """Tests for ExecutionError TypedDict schema introspection."""

    def test_execution_error_required_keys(self) -> None:
        """ExecutionError has exactly exception and type as required keys."""
        from elspeth.contracts import ExecutionError

        assert ExecutionError.__required_keys__ == frozenset({"exception", "type"})

    def test_execution_error_optional_keys(self) -> None:
        """ExecutionError has traceback as optional key."""
        from elspeth.contracts import ExecutionError

        assert ExecutionError.__optional_keys__ == frozenset({"traceback"})

    def test_execution_error_all_keys(self) -> None:
        """ExecutionError total keys match required + optional."""
        from elspeth.contracts import ExecutionError

        all_keys = ExecutionError.__required_keys__ | ExecutionError.__optional_keys__
        assert all_keys == frozenset({"exception", "type", "traceback"})


class TestRoutingReasonSchema:
    """Tests for RoutingReason union type schema introspection."""

    def test_routing_reason_is_union_type(self) -> None:
        """RoutingReason is a union of ConfigGateReason and PluginGateReason."""
        import types

        from elspeth.contracts import (
            ConfigGateReason,
            PluginGateReason,
            RoutingReason,
        )

        assert isinstance(RoutingReason, types.UnionType)
        # Union contains both variant types
        assert ConfigGateReason in RoutingReason.__args__
        assert PluginGateReason in RoutingReason.__args__

    def test_routing_reason_variants_are_typed_dicts(self) -> None:
        """Both RoutingReason variants are TypedDicts."""
        from typing import is_typeddict

        from elspeth.contracts import ConfigGateReason, PluginGateReason

        assert is_typeddict(ConfigGateReason)
        assert is_typeddict(PluginGateReason)


class TestTransformReasonSchema:
    """Tests for TransformReason TypedDict schema introspection."""

    def test_transform_reason_required_keys(self) -> None:
        """TransformReason has action as required key."""
        from elspeth.contracts import TransformReason

        assert TransformReason.__required_keys__ == frozenset({"action"})

    def test_transform_reason_optional_keys(self) -> None:
        """TransformReason has fields_modified and validation_errors as optional keys."""
        from elspeth.contracts import TransformReason

        assert TransformReason.__optional_keys__ == frozenset({"fields_modified", "validation_errors"})


class TestExecutionError:
    """Tests for ExecutionError TypedDict."""

    def test_execution_error_has_required_fields(self) -> None:
        """ExecutionError defines exception and type fields."""
        from elspeth.contracts import ExecutionError

        error: ExecutionError = {
            "exception": "ValueError: invalid input",
            "type": "ValueError",
        }

        assert error["exception"] == "ValueError: invalid input"
        assert error["type"] == "ValueError"

    def test_execution_error_accepts_optional_traceback(self) -> None:
        """ExecutionError can include traceback."""
        from elspeth.contracts import ExecutionError

        error: ExecutionError = {
            "exception": "KeyError: 'foo'",
            "type": "KeyError",
            "traceback": "Traceback (most recent call last):\n...",
        }

        assert "traceback" in error


class TestRoutingReason:
    """Tests for RoutingReason union type usage."""

    def test_routing_reason_accepts_plugin_gate_reason(self) -> None:
        """RoutingReason union accepts PluginGateReason variant."""
        from elspeth.contracts import PluginGateReason, RoutingReason

        reason: RoutingReason = {
            "rule": "value > threshold",
            "matched_value": 42,
        }

        # At runtime, it's just a dict - cast to access variant-specific fields
        plugin_reason: PluginGateReason = reason  # type: ignore[assignment]
        assert plugin_reason["rule"] == "value > threshold"

    def test_routing_reason_accepts_config_gate_reason(self) -> None:
        """RoutingReason union accepts ConfigGateReason variant."""
        from elspeth.contracts import ConfigGateReason, RoutingReason

        reason: RoutingReason = {
            "condition": "row['score'] > 100",
            "result": "true",
        }

        # At runtime, it's just a dict - cast to access variant-specific fields
        config_reason: ConfigGateReason = reason  # type: ignore[assignment]
        assert config_reason["condition"] == "row['score'] > 100"


class TestTransformReason:
    """Tests for TransformReason TypedDict."""

    def test_transform_reason_has_action_field(self) -> None:
        """TransformReason defines action field."""
        from elspeth.contracts import TransformReason

        reason: TransformReason = {
            "action": "normalized_field",
        }

        assert reason["action"] == "normalized_field"

    def test_transform_reason_accepts_optional_fields(self) -> None:
        """TransformReason can include optional fields_modified and validation_errors."""
        from elspeth.contracts import TransformReason

        reason: TransformReason = {
            "action": "validated_and_normalized",
            "fields_modified": ["name", "email"],
            "validation_errors": ["missing_phone"],
        }

        assert reason["fields_modified"] == ["name", "email"]
        assert reason["validation_errors"] == ["missing_phone"]


class TestRoutingReasonVariants:
    """Tests for RoutingReason 2-variant discriminated union."""

    def test_config_gate_reason_required_keys(self) -> None:
        """ConfigGateReason has condition and result as required."""
        from elspeth.contracts import ConfigGateReason

        assert ConfigGateReason.__required_keys__ == frozenset({"condition", "result"})

    def test_plugin_gate_reason_required_keys(self) -> None:
        """PluginGateReason has rule and matched_value as required."""
        from elspeth.contracts import PluginGateReason

        assert PluginGateReason.__required_keys__ == frozenset({"rule", "matched_value"})

    def test_plugin_gate_reason_optional_keys(self) -> None:
        """PluginGateReason has threshold, field, comparison as optional."""
        from elspeth.contracts import PluginGateReason

        assert PluginGateReason.__optional_keys__ == frozenset({"threshold", "field", "comparison"})


class TestRoutingReasonUsage:
    """Tests for constructing valid RoutingReason variants."""

    def test_config_gate_reason_construction(self) -> None:
        """ConfigGateReason can be constructed with required fields."""
        from elspeth.contracts import ConfigGateReason

        reason: ConfigGateReason = {
            "condition": "row['score'] > 100",
            "result": "true",
        }
        assert reason["condition"] == "row['score'] > 100"
        assert reason["result"] == "true"

    def test_plugin_gate_reason_minimal(self) -> None:
        """PluginGateReason works with only required fields."""
        from elspeth.contracts import PluginGateReason

        reason: PluginGateReason = {
            "rule": "threshold_exceeded",
            "matched_value": 150,
        }
        assert reason["rule"] == "threshold_exceeded"
        assert reason["matched_value"] == 150

    def test_plugin_gate_reason_with_optional_fields(self) -> None:
        """PluginGateReason accepts optional threshold fields."""
        from elspeth.contracts import PluginGateReason

        reason: PluginGateReason = {
            "rule": "value exceeds threshold",
            "matched_value": 150,
            "threshold": 100.0,
            "field": "score",
            "comparison": ">",
        }
        assert reason["threshold"] == 100.0
        assert reason["field"] == "score"
        assert reason["comparison"] == ">"
