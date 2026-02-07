"""Tests for TransformResult with PipelineRow.

Verifies that TransformResult correctly accepts and carries PipelineRow
objects, which bundle row data with their schema contract.
"""

import pytest

from elspeth.contracts.results import TransformResult
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


class TestTransformResultWithPipelineRow:
    """Test TransformResult carrying PipelineRow with embedded contract."""

    @pytest.fixture
    def sample_contract(self) -> SchemaContract:
        """Sample output contract."""
        return SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract(
                    normalized_name="id",
                    original_name="id",
                    python_type=int,
                    required=True,
                    source="declared",
                ),
                FieldContract(
                    normalized_name="result",
                    original_name="result",
                    python_type=str,
                    required=True,
                    source="declared",
                ),
            ),
            locked=True,
        )

    def test_success_with_pipeline_row(self, sample_contract: SchemaContract) -> None:
        """TransformResult.success() accepts PipelineRow carrying contract."""
        pipeline_row = PipelineRow({"id": 1, "result": "ok"}, sample_contract)
        result = TransformResult.success(
            row=pipeline_row,
            success_reason={"action": "processed"},
        )

        assert isinstance(result.row, PipelineRow)
        assert result.row.contract is sample_contract
        assert result.row["id"] == 1
        assert result.row["result"] == "ok"

    def test_success_with_dict(self) -> None:
        """TransformResult.success() still accepts plain dicts (internal use)."""
        result = TransformResult.success(
            row={"id": 1},
            success_reason={"action": "processed"},
        )

        assert result.row == {"id": 1}

    def test_success_multi_with_pipeline_rows(self, sample_contract: SchemaContract) -> None:
        """success_multi() accepts list of PipelineRow objects."""
        rows = [
            PipelineRow({"id": 1, "result": "a"}, sample_contract),
            PipelineRow({"id": 2, "result": "b"}, sample_contract),
        ]
        result = TransformResult.success_multi(
            rows=rows,
            success_reason={"action": "split"},
        )

        assert result.rows is not None
        assert len(result.rows) == 2
        assert all(isinstance(r, PipelineRow) for r in result.rows)
        assert result.rows[0]["id"] == 1
        assert result.rows[1]["id"] == 2

    def test_error_has_no_row(self) -> None:
        """Error results have no row data."""
        result = TransformResult.error(
            reason={"reason": "test_error"},
            retryable=False,
        )

        assert result.row is None
        assert result.rows is None

    def test_pipeline_row_contract_accessible(self, sample_contract: SchemaContract) -> None:
        """Contract is accessible through PipelineRow in result.row."""
        pipeline_row = PipelineRow({"id": 1, "result": "ok"}, sample_contract)
        result = TransformResult.success(
            row=pipeline_row,
            success_reason={"action": "processed"},
        )

        assert result.row.contract.mode == "FIXED"
        assert len(result.row.contract.fields) == 2

    def test_multi_row_contract_accessible(self, sample_contract: SchemaContract) -> None:
        """Contract is accessible through each PipelineRow in result.rows."""
        rows = [
            PipelineRow({"id": 1, "result": "a"}, sample_contract),
            PipelineRow({"id": 2, "result": "b"}, sample_contract),
        ]
        result = TransformResult.success_multi(
            rows=rows,
            success_reason={"action": "split"},
        )

        for row in result.rows:
            assert row.contract is sample_contract
