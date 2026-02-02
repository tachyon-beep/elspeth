"""Tests for TransformResult with SchemaContract.

Tests for Task 3 of Phase 3: TransformResult carrying contract reference
to enable conversion to PipelineRow for downstream processing.
"""

import pytest

from elspeth.contracts.results import TransformResult
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


class TestTransformResultWithContract:
    """Test TransformResult carrying contract reference."""

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

    def test_success_with_contract(self, sample_contract: SchemaContract) -> None:
        """TransformResult.success() can include contract."""
        result = TransformResult.success(
            row={"id": 1, "result": "ok"},
            success_reason={"action": "processed"},
            contract=sample_contract,
        )

        assert result.contract is sample_contract

    def test_success_without_contract(self) -> None:
        """TransformResult.success() works without contract (backwards compatible)."""
        result = TransformResult.success(
            row={"id": 1},
            success_reason={"action": "processed"},
        )

        assert result.contract is None

    def test_error_has_no_contract(self) -> None:
        """Error results don't carry contracts."""
        result = TransformResult.error(
            reason={"reason": "test_error"},
            retryable=False,
        )

        assert result.contract is None

    def test_success_multi_with_contract(self, sample_contract: SchemaContract) -> None:
        """success_multi() can include contract."""
        result = TransformResult.success_multi(
            rows=[{"id": 1, "result": "a"}, {"id": 2, "result": "b"}],
            success_reason={"action": "split"},
            contract=sample_contract,
        )

        assert result.contract is sample_contract

    def test_success_multi_without_contract(self) -> None:
        """success_multi() works without contract (backwards compatible)."""
        result = TransformResult.success_multi(
            rows=[{"id": 1}, {"id": 2}],
            success_reason={"action": "split"},
        )

        assert result.contract is None

    def test_to_pipeline_row(self, sample_contract: SchemaContract) -> None:
        """TransformResult can convert to PipelineRow."""
        result = TransformResult.success(
            row={"id": 1, "result": "ok"},
            success_reason={"action": "processed"},
            contract=sample_contract,
        )

        pipeline_row = result.to_pipeline_row()

        assert isinstance(pipeline_row, PipelineRow)
        assert pipeline_row["id"] == 1
        assert pipeline_row["result"] == "ok"

    def test_to_pipeline_row_raises_on_error(self) -> None:
        """to_pipeline_row() raises for error results."""
        result = TransformResult.error(
            reason={"reason": "test_error"},
            retryable=False,
        )

        with pytest.raises(ValueError, match="error"):
            result.to_pipeline_row()

    def test_to_pipeline_row_raises_on_multi(self, sample_contract: SchemaContract) -> None:
        """to_pipeline_row() raises for multi-row results."""
        result = TransformResult.success_multi(
            rows=[{"id": 1, "result": "a"}],
            success_reason={"action": "split"},
            contract=sample_contract,
        )

        with pytest.raises(ValueError, match="multi"):
            result.to_pipeline_row()

    def test_to_pipeline_row_raises_without_contract(self) -> None:
        """to_pipeline_row() raises if no contract."""
        result = TransformResult.success(
            row={"id": 1},
            success_reason={"action": "processed"},
        )

        with pytest.raises(ValueError, match="contract"):
            result.to_pipeline_row()

    def test_to_pipeline_rows_multi(self, sample_contract: SchemaContract) -> None:
        """to_pipeline_rows() returns list for multi-row results."""
        result = TransformResult.success_multi(
            rows=[{"id": 1, "result": "a"}, {"id": 2, "result": "b"}],
            success_reason={"action": "split"},
            contract=sample_contract,
        )

        pipeline_rows = result.to_pipeline_rows()

        assert len(pipeline_rows) == 2
        assert all(isinstance(r, PipelineRow) for r in pipeline_rows)
        assert pipeline_rows[0]["id"] == 1
        assert pipeline_rows[1]["id"] == 2

    def test_to_pipeline_rows_raises_on_single(self, sample_contract: SchemaContract) -> None:
        """to_pipeline_rows() raises for single-row results."""
        result = TransformResult.success(
            row={"id": 1, "result": "ok"},
            success_reason={"action": "processed"},
            contract=sample_contract,
        )

        with pytest.raises(ValueError, match="single"):
            result.to_pipeline_rows()

    def test_to_pipeline_rows_raises_on_error(self) -> None:
        """to_pipeline_rows() raises for error results."""
        result = TransformResult.error(
            reason={"reason": "test_error"},
            retryable=False,
        )

        with pytest.raises(ValueError, match="error"):
            result.to_pipeline_rows()

    def test_to_pipeline_rows_raises_without_contract(self, sample_contract: SchemaContract) -> None:
        """to_pipeline_rows() raises if no contract."""
        result = TransformResult.success_multi(
            rows=[{"id": 1}, {"id": 2}],
            success_reason={"action": "split"},
            # No contract provided
        )

        with pytest.raises(ValueError, match="contract"):
            result.to_pipeline_rows()

    def test_contract_not_in_repr(self, sample_contract: SchemaContract) -> None:
        """contract field should have repr=False for cleaner output."""
        result = TransformResult.success(
            row={"id": 1, "result": "ok"},
            success_reason={"action": "processed"},
            contract=sample_contract,
        )

        repr_str = repr(result)
        assert "contract" not in repr_str
