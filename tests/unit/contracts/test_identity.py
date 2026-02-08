"""Tests for identity contracts."""

import pytest

from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from tests.fixtures.factories import make_field


def _make_contract() -> SchemaContract:
    """Create a minimal schema contract for testing."""
    return SchemaContract(
        mode="FLEXIBLE",
        fields=(make_field("field", str, original_name="field", source="declared"),),
        locked=True,
    )


class TestTokenInfo:
    """Tests for TokenInfo."""

    def test_create_token_info(self) -> None:
        """Can create TokenInfo with required fields."""
        from elspeth.contracts import TokenInfo

        contract = _make_contract()
        pipeline_row = PipelineRow({"field": "value"}, contract)

        token = TokenInfo(
            row_id="row-123",
            token_id="tok-456",
            row_data=pipeline_row,
        )

        assert token.row_id == "row-123"
        assert token.token_id == "tok-456"
        assert token.row_data["field"] == "value"
        assert token.branch_name is None

    def test_token_info_with_branch(self) -> None:
        """Can create TokenInfo with branch_name."""
        from elspeth.contracts import TokenInfo

        contract = _make_contract()
        pipeline_row = PipelineRow({}, contract)

        token = TokenInfo(
            row_id="row-123",
            token_id="tok-456",
            row_data=pipeline_row,
            branch_name="sentiment",
        )

        assert token.branch_name == "sentiment"

    def test_token_info_row_data_immutable(self) -> None:
        """TokenInfo.row_data (PipelineRow) is immutable for audit integrity."""
        from elspeth.contracts import TokenInfo

        contract = _make_contract()
        pipeline_row = PipelineRow({"field": "value"}, contract)

        token = TokenInfo(row_id="r", token_id="t", row_data=pipeline_row)

        # PipelineRow should raise TypeError on modification attempt
        with pytest.raises(TypeError, match="immutable"):
            token.row_data["field"] = "modified"

    def test_token_info_is_frozen(self) -> None:
        """TokenInfo is immutable — field assignment raises FrozenInstanceError."""
        from dataclasses import FrozenInstanceError

        from elspeth.contracts import TokenInfo

        contract = _make_contract()
        pipeline_row = PipelineRow({}, contract)

        token = TokenInfo(row_id="r", token_id="t", row_data=pipeline_row)
        with pytest.raises(FrozenInstanceError):
            token.branch_name = "sentiment"
        with pytest.raises(FrozenInstanceError):
            token.row_id = "new_row_id"

    def test_with_updated_data_preserves_lineage(self) -> None:
        """with_updated_data() preserves all lineage fields."""
        from elspeth.contracts import TokenInfo

        contract = _make_contract()
        original_row = PipelineRow({"field": "original"}, contract)
        updated_row = PipelineRow({"field": "updated"}, contract)

        original = TokenInfo(
            row_id="row-1",
            token_id="tok-1",
            row_data=original_row,
            branch_name="path_a",
            fork_group_id="fork-123",
            join_group_id="join-456",
            expand_group_id="expand-789",
        )

        updated = original.with_updated_data(updated_row)

        # Data changed
        assert updated.row_data["field"] == "updated"
        assert original.row_data["field"] == "original"

        # All lineage preserved
        assert updated.row_id == "row-1"
        assert updated.token_id == "tok-1"
        assert updated.branch_name == "path_a"
        assert updated.fork_group_id == "fork-123"
        assert updated.join_group_id == "join-456"
        assert updated.expand_group_id == "expand-789"
