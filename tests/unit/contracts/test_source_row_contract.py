"""Tests for SourceRow with SchemaContract integration."""

import pytest

from elspeth.contracts.results import SourceRow
from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.testing import make_field


class TestSourceRowWithContract:
    """Test SourceRow carrying contract reference."""

    @pytest.fixture
    def sample_contract(self) -> SchemaContract:
        """Sample locked contract."""
        return SchemaContract(
            mode="FIXED",
            fields=(
                make_field("id", int, original_name="ID", required=True, source="declared"),
                make_field("name", str, original_name="Name", required=True, source="declared"),
            ),
            locked=True,
        )

    def test_valid_with_contract(self, sample_contract: SchemaContract) -> None:
        """SourceRow.valid() can include contract."""
        row_data = {"id": 1, "name": "Alice"}
        source_row = SourceRow.valid(row_data, contract=sample_contract)

        assert source_row.is_quarantined is False
        assert source_row.contract is sample_contract

    def test_valid_without_contract(self) -> None:
        """SourceRow.valid() works without contract (backwards compatible)."""
        row_data = {"id": 1}
        source_row = SourceRow.valid(row_data)

        assert source_row.contract is None

    def test_quarantined_no_contract(self) -> None:
        """Quarantined rows don't carry contracts."""
        source_row = SourceRow.quarantined(
            row={"bad": "data"},
            error="validation failed",
            destination="quarantine",
        )

        assert source_row.contract is None

    def test_to_pipeline_row(self, sample_contract: SchemaContract) -> None:
        """SourceRow can convert to PipelineRow."""
        row_data = {"id": 1, "name": "Alice"}
        source_row = SourceRow.valid(row_data, contract=sample_contract)

        pipeline_row = source_row.to_pipeline_row()

        assert isinstance(pipeline_row, PipelineRow)
        assert pipeline_row["id"] == 1
        assert pipeline_row["name"] == "Alice"

    def test_to_pipeline_row_raises_without_contract(self) -> None:
        """to_pipeline_row() raises if no contract attached."""
        source_row = SourceRow.valid({"id": 1})

        with pytest.raises(ValueError, match="no contract"):
            source_row.to_pipeline_row()

    def test_to_pipeline_row_raises_if_quarantined(self, sample_contract: SchemaContract) -> None:
        """to_pipeline_row() raises for quarantined rows."""
        source_row = SourceRow.quarantined(
            row={"bad": "data"},
            error="failed",
            destination="quarantine",
        )

        with pytest.raises(ValueError, match="quarantined"):
            source_row.to_pipeline_row()
