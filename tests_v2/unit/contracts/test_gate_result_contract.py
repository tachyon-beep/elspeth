"""Tests for GateResult contract support."""

import pytest

from elspeth.contracts import GateResult, RoutingAction
from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from tests_v2.fixtures.factories import make_field


def _make_contract() -> SchemaContract:
    """Create a minimal schema contract for testing."""
    return SchemaContract(
        mode="FIXED",
        fields=(
            make_field(
                "amount",
                int,
                original_name="'Amount'",
                required=True,
                source="declared",
            ),
        ),
        locked=True,
    )


class TestGateResultContract:
    """Tests for GateResult contract field."""

    def test_gate_result_has_contract_field(self) -> None:
        """GateResult should have optional contract field."""
        contract = _make_contract()
        result = GateResult(
            row={"amount": 100},
            action=RoutingAction.continue_(),
            contract=contract,
        )
        assert result.contract is contract

    def test_gate_result_contract_defaults_to_none(self) -> None:
        """GateResult contract should default to None."""
        result = GateResult(
            row={"amount": 100},
            action=RoutingAction.continue_(),
        )
        assert result.contract is None

    def test_to_pipeline_row_with_contract(self) -> None:
        """to_pipeline_row() should work when contract is present."""
        contract = _make_contract()
        result = GateResult(
            row={"amount": 100},
            action=RoutingAction.continue_(),
            contract=contract,
        )
        pipeline_row = result.to_pipeline_row()
        assert isinstance(pipeline_row, PipelineRow)
        assert pipeline_row["amount"] == 100
        assert pipeline_row.contract is contract

    def test_to_pipeline_row_without_contract_raises(self) -> None:
        """to_pipeline_row() should raise when contract is None."""
        result = GateResult(
            row={"amount": 100},
            action=RoutingAction.continue_(),
        )
        with pytest.raises(ValueError, match="no contract"):
            result.to_pipeline_row()

    def test_contract_not_in_repr(self) -> None:
        """contract field should have repr=False for cleaner output."""
        contract = _make_contract()
        result = GateResult(
            row={"amount": 100},
            action=RoutingAction.continue_(),
            contract=contract,
        )
        repr_str = repr(result)
        assert "contract" not in repr_str
