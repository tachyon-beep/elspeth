"""Tests for TokenInfo with PipelineRow."""

from elspeth.contracts.identity import TokenInfo
from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.testing import make_field


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


class TestTokenInfoPipelineRow:
    """Tests for TokenInfo with PipelineRow row_data."""

    def test_token_info_accepts_pipeline_row(self) -> None:
        """TokenInfo should accept PipelineRow for row_data."""
        contract = _make_contract()
        pipeline_row = PipelineRow({"amount": 100}, contract)

        token = TokenInfo(
            row_id="row_001",
            token_id="token_001",
            row_data=pipeline_row,
        )

        assert token.row_data is pipeline_row
        assert token.row_data["amount"] == 100

    def test_with_updated_data_returns_new_token(self) -> None:
        """with_updated_data() should return new TokenInfo with new PipelineRow."""
        contract = _make_contract()
        original_row = PipelineRow({"amount": 100}, contract)
        updated_row = PipelineRow({"amount": 200}, contract)

        original_token = TokenInfo(
            row_id="row_001",
            token_id="token_001",
            row_data=original_row,
        )

        updated_token = original_token.with_updated_data(updated_row)

        # Original unchanged
        assert original_token.row_data["amount"] == 100
        # New token has new data
        assert updated_token.row_data["amount"] == 200
        # Identity preserved
        assert updated_token.row_id == original_token.row_id
        assert updated_token.token_id == original_token.token_id

    def test_row_data_contract_accessible(self) -> None:
        """Should be able to access contract from row_data."""
        contract = _make_contract()
        pipeline_row = PipelineRow({"amount": 100}, contract)

        token = TokenInfo(
            row_id="row_001",
            token_id="token_001",
            row_data=pipeline_row,
        )

        assert token.row_data.contract is contract
        assert token.row_data.contract.mode == "FIXED"

    def test_pipeline_row_to_dict_includes_extra_fields(self) -> None:
        """to_dict() should return ALL fields, not just contract fields."""
        contract = _make_contract()  # Only has "amount"
        data_with_extras = {"amount": 100, "computed_field": "extra", "nested": {"a": 1}}
        pipeline_row = PipelineRow(data_with_extras, contract)

        result = pipeline_row.to_dict()

        # All fields preserved, not just contract fields
        assert result["amount"] == 100
        assert result["computed_field"] == "extra"
        assert result["nested"] == {"a": 1}
