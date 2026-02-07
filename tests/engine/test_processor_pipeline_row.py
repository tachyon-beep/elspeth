"""Tests for RowProcessor with PipelineRow support (Task 6)."""

from unittest.mock import MagicMock, Mock

import pytest

from elspeth.contracts import SourceRow
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.contracts.types import NodeID


def _make_contract() -> SchemaContract:
    """Create a minimal schema contract for testing."""
    return SchemaContract(
        mode="OBSERVED",
        fields=(
            FieldContract(
                normalized_name="amount",
                original_name="'Amount'",
                python_type=int,
                required=True,
                source="declared",
            ),
        ),
        locked=True,
    )


def _make_mock_recorder() -> MagicMock:
    """Create a mock LandscapeRecorder."""
    recorder = MagicMock()
    recorder.create_row.return_value = Mock(row_id="row_001")
    recorder.create_token.return_value = Mock(token_id="token_001")
    return recorder


def _make_mock_span_factory() -> MagicMock:
    """Create a mock SpanFactory."""
    span_factory = MagicMock()
    span_factory.row_span.return_value.__enter__ = Mock()
    span_factory.row_span.return_value.__exit__ = Mock()
    return span_factory


class TestRowProcessorPipelineRow:
    """Tests for RowProcessor.process_row() with SourceRow."""

    def test_process_row_accepts_source_row(self) -> None:
        """process_row should accept SourceRow and pass it to create_initial_token."""
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.engine.processor import RowProcessor

        contract = _make_contract()
        recorder = _make_mock_recorder()
        span_factory = _make_mock_span_factory()

        processor = RowProcessor(
            recorder=recorder,
            span_factory=span_factory,
            run_id="run_001",
            source_node_id=NodeID("source_001"),
        )

        source_row = SourceRow.valid({"amount": 100}, contract=contract)
        ctx = PluginContext(run_id="run_001", config={})

        # No transforms - token should be created and completed immediately
        processor.process_row(
            row_index=0,
            source_row=source_row,
            transforms=[],
            ctx=ctx,
        )

        # Should have created a row and token via recorder
        recorder.create_row.assert_called_once()
        recorder.create_token.assert_called_once()

    def test_process_row_creates_pipeline_row(self) -> None:
        """process_row should create token with PipelineRow containing contract."""
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.engine.processor import RowProcessor

        contract = _make_contract()
        recorder = _make_mock_recorder()
        span_factory = _make_mock_span_factory()

        processor = RowProcessor(
            recorder=recorder,
            span_factory=span_factory,
            run_id="run_001",
            source_node_id=NodeID("source_001"),
        )

        source_row = SourceRow.valid({"amount": 100}, contract=contract)
        ctx = PluginContext(run_id="run_001", config={})

        results = processor.process_row(
            row_index=0,
            source_row=source_row,
            transforms=[],
            ctx=ctx,
        )

        # Result should have token with PipelineRow
        assert len(results) >= 1
        result = results[0]
        assert isinstance(result.token.row_data, PipelineRow)
        assert result.token.row_data["amount"] == 100
        assert result.token.row_data.contract is contract

    def test_process_row_requires_contract_on_source_row(self) -> None:
        """process_row should raise if SourceRow has no contract.

        The error propagates from TokenManager.create_initial_token(),
        which enforces this requirement.
        """
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.engine.processor import RowProcessor

        recorder = _make_mock_recorder()
        span_factory = _make_mock_span_factory()

        processor = RowProcessor(
            recorder=recorder,
            span_factory=span_factory,
            run_id="run_001",
            source_node_id=NodeID("source_001"),
        )

        # SourceRow without contract
        source_row = SourceRow.valid({"amount": 100}, contract=None)
        ctx = PluginContext(run_id="run_001", config={})

        with pytest.raises(ValueError, match="must have contract"):
            processor.process_row(
                row_index=0,
                source_row=source_row,
                transforms=[],
                ctx=ctx,
            )


class TestRowProcessorExistingRow:
    """Tests for RowProcessor.process_existing_row() with PipelineRow."""

    def test_process_existing_row_accepts_pipeline_row(self) -> None:
        """process_existing_row should accept PipelineRow for resume scenarios."""
        from elspeth.contracts.plugin_context import PluginContext
        from elspeth.engine.processor import RowProcessor

        contract = _make_contract()
        recorder = _make_mock_recorder()
        span_factory = _make_mock_span_factory()

        processor = RowProcessor(
            recorder=recorder,
            span_factory=span_factory,
            run_id="run_001",
            source_node_id=NodeID("source_001"),
        )

        # PipelineRow for resume (row already exists in database)
        row_data = PipelineRow({"amount": 100}, contract)
        ctx = PluginContext(run_id="run_001", config={})

        results = processor.process_existing_row(
            row_id="existing_row_001",
            row_data=row_data,
            transforms=[],
            ctx=ctx,
        )

        # Should create token for existing row (NOT create_row)
        recorder.create_token.assert_called_once()
        recorder.create_row.assert_not_called()

        # Result should have token with PipelineRow
        assert len(results) >= 1
        result = results[0]
        assert isinstance(result.token.row_data, PipelineRow)
        assert result.token.row_data.contract is contract
